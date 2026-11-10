#if os(macOS)
import AppKit
import Metal
import Observation
import QuartzCore
import SwiftUI

/// No SwiftUI state or hosting view participates in the native frame loop.
struct TopoMetalSurface: NSViewRepresentable {
    let model: SymairaTopoModel
    let origin: CGPoint
    let scheme: ColorScheme
    let still: Bool
    let visible: Bool

    func makeNSView(context: Context) -> TopoMetalView { TopoMetalView() }
    func updateNSView(_ view: TopoMetalView, context: Context) {
        view.configure(model: model, origin: origin, scheme: scheme, still: still, visible: visible)
    }
    static func dismantleNSView(_ view: TopoMetalView, coordinator: ()) { view.stop() }
}

/// Also used by the parity test: the production encoder, not a duplicate shader.
@MainActor
final class TopoMetalPipeline {
    let device: any MTLDevice
    private let queue: any MTLCommandQueue
    private let pipeline: any MTLRenderPipelineState

    init(device: any MTLDevice) throws {
        self.device = device
        guard let queue = device.makeCommandQueue() else { throw CocoaError(.featureUnsupported) }
        self.queue = queue
        let library = try device.makeDefaultLibrary(bundle: SymairaThemeResources.bundle)
        let descriptor = MTLRenderPipelineDescriptor()
        descriptor.vertexFunction = library.makeFunction(name: "topoVertex")
        descriptor.fragmentFunction = library.makeFunction(name: "topoFragment")
        // SwiftUI's default colorEffect works in encoded sRGB. A non-sRGB
        // attachment preserves that interpolation; the layer declares its sRGB
        // colorspace separately. A *_srgb attachment would brighten the lines.
        descriptor.colorAttachments[0].pixelFormat = .bgra8Unorm
        pipeline = try device.makeRenderPipelineState(descriptor: descriptor)
    }

    @discardableResult
    func render(
        _ frame: TopoFrame, into texture: any MTLTexture,
        drawable: (any CAMetalDrawable)? = nil
    ) -> (any MTLCommandBuffer)? {
        guard let command = queue.makeCommandBuffer() else { return nil }
        let pass = MTLRenderPassDescriptor()
        pass.colorAttachments[0].texture = texture
        pass.colorAttachments[0].loadAction = .clear
        pass.colorAttachments[0].storeAction = .store
        pass.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 0, 0)
        guard let encoder = command.makeRenderCommandEncoder(descriptor: pass) else { return nil }
        encoder.setRenderPipelineState(pipeline)
        var uniforms = frame.vectors + [frame.canvas, frame.topo, frame.tint]
        // uint4 occupies the same 16-byte slot as float4, preserving Metal alignment.
        uniforms.append(
            SIMD4(
                Float(bitPattern: UInt32(frame.rects.count)),
                Float(bitPattern: UInt32(frame.ripples.count)), 0, 0))
        uniforms.withUnsafeBytes { encoder.setFragmentBytes($0.baseAddress!, length: $0.count, index: 0) }
        for (index, array) in [frame.rects, frame.ripples].enumerated() {
            let values = array.isEmpty ? [Float(0)] : array
            values.withUnsafeBytes { encoder.setFragmentBytes($0.baseAddress!, length: $0.count, index: index + 1) }
        }
        encoder.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
        encoder.endEncoding()
        if let drawable { command.present(drawable) }
        command.commit()
        return command
    }
}

@MainActor
final class TopoMetalView: NSView {
    private var renderer: TopoMetalPipeline?
    private let integrator = TopoFrameIntegrator()
    private var timer: Timer?
    private var model: SymairaTopoModel?
    private var origin = CGPoint.zero
    private var scheme = ColorScheme.light
    private var still = false
    private var visible = true
    private var observing = false
    private var stopped = false
    private var powerObserver: NSObjectProtocol?
    private(set) var framesDrawn = 0
    private var metalLayer: CAMetalLayer { layer as! CAMetalLayer }
    override var isFlipped: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
    override func makeBackingLayer() -> CALayer { CAMetalLayer() }

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        if let device = MTLCreateSystemDefaultDevice() {
            renderer = try? TopoMetalPipeline(device: device)
            metalLayer.device = device
        }
        metalLayer.pixelFormat = .bgra8Unorm
        metalLayer.colorspace = CGColorSpace(name: CGColorSpace.sRGB)
        metalLayer.isOpaque = false
        metalLayer.backgroundColor = CGColor.clear
        metalLayer.framebufferOnly = true
        powerObserver = NotificationCenter.default.addObserver(
            forName: .NSProcessInfoPowerStateDidChange, object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.refresh() }
        }
    }
    convenience init() { self.init(frame: .zero) }
    required init?(coder: NSCoder) { nil }

    private var paused: Bool { still || !visible || ProcessInfo.processInfo.isLowPowerModeEnabled }

    func configure(model: SymairaTopoModel, origin: CGPoint, scheme: ColorScheme, still: Bool, visible: Bool) {
        guard !stopped else { return }
        let wasPaused = paused
        if self.model !== model { observing = false }
        self.model = model
        self.origin = origin
        self.scheme = scheme
        self.still = still
        self.visible = visible
        if paused != wasPaused {
            integrator.reset()
            model.pressed = false
            model.pointer = nil
            model.interactive = false
            model.ripples.removeAll()
        }
        refresh()
    }

    /// One subscription, rearmed only after an input changes; never one per timer tick.
    private func observeInputs() {
        guard !observing, !stopped, let model else { return }
        observing = true
        withObservationTracking {
            _ = model.state
            _ = model.rects
            _ = model.askPoint
            _ = model.statusPoint
            _ = model.interactive
        } onChange: { [weak self, weak model] in
            Task { @MainActor [weak self, weak model] in
                guard let self, !self.stopped, let model, self.model === model else { return }
                self.observing = false
                self.refresh()
            }
        }
    }

    private func refresh() {
        guard !stopped else { return }
        observeInputs()
        timer?.invalidate()
        timer = nil
        if !paused, window != nil {
            let fps =
                model?.interactive == true
                ? Double(window?.screen?.maximumFramesPerSecond ?? 60) : SymairaTokens.Topo.fps
            let timer = Timer(timeInterval: 1 / fps, repeats: true) { [weak self] _ in
                MainActor.assumeIsolated { self?.drawFrame() }
            }
            RunLoop.main.add(timer, forMode: .common)
            self.timer = timer
        }
        drawFrame()
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        integrator.reset()
        refresh()
    }
    override func viewDidChangeBackingProperties() {
        super.viewDidChangeBackingProperties()
        drawFrame()
    }
    override func layout() {
        super.layout()
        drawFrame()
    }

    func drawFrame() {
        guard !stopped, let model, let renderer, bounds.width > 0, bounds.height > 0 else { return }
        let scale = window?.backingScaleFactor ?? 1
        let size = CGSize(width: bounds.width * scale, height: bounds.height * scale)
        if metalLayer.drawableSize != size {
            metalLayer.contentsScale = scale
            metalLayer.drawableSize = size
        }
        guard let drawable = metalLayer.nextDrawable() else { return }
        let frame = integrator.frame(
            model: model, size: bounds.size, origin: origin, now: .now,
            scheme: scheme, displayScale: scale,
            still: still || ProcessInfo.processInfo.isLowPowerModeEnabled, paused: paused)
        if renderer.render(frame, into: drawable.texture, drawable: drawable) != nil { framesDrawn += 1 }
    }

    func stop() {
        stopped = true
        timer?.invalidate()
        timer = nil
        if let powerObserver { NotificationCenter.default.removeObserver(powerObserver) }
        powerObserver = nil
        model = nil
        renderer = nil
        metalLayer.device = nil
    }
}
#endif
