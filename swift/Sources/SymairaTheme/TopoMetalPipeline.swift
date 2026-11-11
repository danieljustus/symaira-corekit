#if os(macOS) || canImport(UIKit)
import Metal
import Observation
import QuartzCore
import SwiftUI

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

/// Platform-neutral core of the native topography surfaces: input state, the
/// observation subscription, pause decision, frame integration and the draw
/// call. The AppKit and UIKit views own only their native frame loop (timer or
/// display link) and view lifecycle. No SwiftUI state participates in a frame.
@MainActor
final class TopoMetalDriver {
    private(set) var model: SymairaTopoModel?
    private(set) var origin = CGPoint.zero
    private(set) var scheme = ColorScheme.light
    private(set) var still = false
    private(set) var visible = true
    private(set) var stopped = false
    private(set) var framesDrawn = 0
    /// Re-evaluates the frame loop and redraws; set by the owning view.
    var onRefresh: (() -> Void)?
    private let integrator = TopoFrameIntegrator()
    private var renderer: TopoMetalPipeline?
    private var observing = false
    private var powerObserver: NSObjectProtocol?

    init() {
        if let device = MTLCreateSystemDefaultDevice() { renderer = try? TopoMetalPipeline(device: device) }
        powerObserver = NotificationCenter.default.addObserver(
            forName: .NSProcessInfoPowerStateDidChange, object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.onRefresh?() }
        }
    }

    var lowPower: Bool { ProcessInfo.processInfo.isLowPowerModeEnabled }
    var paused: Bool { TopoFramePacing.isPaused(still: still, visible: visible, lowPower: lowPower) }
    var interactive: Bool { model?.interactive == true }

    /// The layer declares sRGB separately from the non-sRGB attachment format
    /// (see `TopoMetalPipeline`) so SwiftUI's encoded-sRGB interpolation holds.
    func attach(_ layer: CAMetalLayer) {
        layer.device = renderer?.device
        layer.pixelFormat = .bgra8Unorm
        layer.colorspace = CGColorSpace(name: CGColorSpace.sRGB)
        layer.isOpaque = false
        layer.backgroundColor = CGColor(gray: 0, alpha: 0)
        layer.framebufferOnly = true
    }

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
        onRefresh?()
    }

    func resetClock() { integrator.reset() }

    /// One subscription, rearmed only after an input changes; never one per frame.
    /// Geometry (`rects`) changes redraw natively without invalidating SwiftUI.
    func observeInputs() {
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
                self.onRefresh?()
            }
        }
    }

    /// `size` is in points, `scale` the point-to-pixel factor of the screen.
    func draw(on layer: CAMetalLayer, size: CGSize, scale: CGFloat) {
        guard !stopped, let model, let renderer, size.width > 0, size.height > 0 else { return }
        let pixels = CGSize(width: size.width * scale, height: size.height * scale)
        if layer.drawableSize != pixels {
            layer.contentsScale = scale
            layer.drawableSize = pixels
        }
        guard let drawable = layer.nextDrawable() else { return }
        let frame = integrator.frame(
            model: model, size: size, origin: origin, now: .now,
            scheme: scheme, displayScale: scale,
            still: TopoFramePacing.isStill(still: still, lowPower: lowPower), paused: paused)
        if renderer.render(frame, into: drawable.texture, drawable: drawable) != nil { framesDrawn += 1 }
    }

    func stop(layer: CAMetalLayer) {
        stopped = true
        if let powerObserver { NotificationCenter.default.removeObserver(powerObserver) }
        powerObserver = nil
        onRefresh = nil
        model = nil
        renderer = nil
        layer.device = nil
    }
}
#endif
