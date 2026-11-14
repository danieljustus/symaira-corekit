#if os(macOS) || canImport(UIKit)
import Metal
import Observation
import QuartzCore
import SwiftUI

/// Also used by the parity test: the production encoder, not a duplicate shader.
///
/// Production draws two passes: the height field once per `cellPoints` grid cell into a small
/// float texture, then the contour lines per device pixel from a cubic B-spline through it.
/// `reference: true` draws the original single pass (the full height field three times per
/// pixel); tests compare both for parity and cost.
@MainActor
final class TopoMetalPipeline {
    /// Grid spacing of the height field in points. Its finest detail (third noise octave,
    /// ripple rings) spans more than 25 pt, so 4 pt keeps the B-spline within a hair of the
    /// per-pixel field at a few hundredths of its cost.
    static let cellPoints: Float = 4
    /// Grid samples before the surface edge, so the B-spline has support at x or y = 0.
    static let paddingCells: Float = 1

    let device: any MTLDevice
    private let queue: any MTLCommandQueue
    private let reference: (any MTLRenderPipelineState)?
    private let heightField: (any MTLRenderPipelineState)?
    private let contour: (any MTLRenderPipelineState)?
    private var heights: (any MTLTexture)?

    init(device: any MTLDevice, reference useReference: Bool = false) throws {
        self.device = device
        guard let queue = device.makeCommandQueue() else { throw CocoaError(.featureUnsupported) }
        self.queue = queue
        let library = try device.makeDefaultLibrary(bundle: SymairaThemeResources.bundle)
        func state(_ fragment: String, _ format: MTLPixelFormat) throws -> any MTLRenderPipelineState {
            let descriptor = MTLRenderPipelineDescriptor()
            descriptor.vertexFunction = library.makeFunction(name: "topoVertex")
            descriptor.fragmentFunction = library.makeFunction(name: fragment)
            descriptor.colorAttachments[0].pixelFormat = format
            return try device.makeRenderPipelineState(descriptor: descriptor)
        }
        // SwiftUI's default colorEffect works in encoded sRGB. A non-sRGB
        // attachment preserves that interpolation; the layer declares its sRGB
        // colorspace separately. A *_srgb attachment would brighten the lines.
        if useReference {
            reference = try state("topoFragment", .bgra8Unorm)
            heightField = nil
            contour = nil
        } else {
            reference = nil
            heightField = try state("topoHeightField", .r32Float)
            contour = try state("topoContour", .bgra8Unorm)
        }
    }

    /// Grid size in samples for a surface of `size` points: padding before, B-spline support after.
    static func gridSize(points size: SIMD2<Float>) -> (width: Int, height: Int) {
        let extra = Int(paddingCells) + 3
        return (
            Int((max(size.x, 1) / cellPoints).rounded(.up)) + extra,
            Int((max(size.y, 1) / cellPoints).rounded(.up)) + extra
        )
    }

    @discardableResult
    func render(
        _ frame: TopoFrame, into texture: any MTLTexture,
        drawable: (any CAMetalDrawable)? = nil,
        completed: MTLCommandBufferHandler? = nil
    ) -> (any MTLCommandBuffer)? {
        guard let command = queue.makeCommandBuffer() else { return nil }
        var uniforms = frame.vectors + [frame.canvas, frame.topo, frame.tint]
        // uint4 occupies the same 16-byte slot as float4, preserving Metal alignment.
        uniforms.append(
            SIMD4(
                Float(bitPattern: UInt32(frame.rects.count)),
                Float(bitPattern: UInt32(frame.ripples.count)), 0, 0))
        let rects = frame.rects.isEmpty ? [Float(0)] : frame.rects
        let ripples = frame.ripples.isEmpty ? [Float(0)] : frame.ripples
        // No closure may capture `encoder`: Xcode 26.6 Release builds treat a closure inside this
        // @MainActor method as main-actor isolated and reject sending the encoder into it (#486).
        func bind(_ encoder: any MTLRenderCommandEncoder, ripplesToo: Bool) {
            encoder.setFragmentBytes(uniforms, length: uniforms.count * MemoryLayout<SIMD4<Float>>.stride, index: 0)
            encoder.setFragmentBytes(rects, length: rects.count * MemoryLayout<Float>.stride, index: 1)
            if ripplesToo {
                encoder.setFragmentBytes(ripples, length: ripples.count * MemoryLayout<Float>.stride, index: 2)
            }
        }

        if let reference {
            guard let encoder = command.makeRenderCommandEncoder(descriptor: Self.pass(texture, load: .clear))
            else { return nil }
            encoder.setRenderPipelineState(reference)
            bind(encoder, ripplesToo: true)
            encoder.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
            encoder.endEncoding()
        } else if let heightField, let contour {
            let points = SIMD2(frame.vectors[0].x, frame.vectors[0].y)
            let size = Self.gridSize(points: points)
            guard let heights = heightTexture(width: size.width, height: size.height) else { return nil }
            var grid = SIMD4(Self.cellPoints, Self.paddingCells, Float(size.width), Float(size.height))

            guard let field = command.makeRenderCommandEncoder(descriptor: Self.pass(heights, load: .dontCare))
            else { return nil }
            field.setRenderPipelineState(heightField)
            bind(field, ripplesToo: true)
            field.setFragmentBytes(&grid, length: MemoryLayout<SIMD4<Float>>.stride, index: 3)
            field.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
            field.endEncoding()

            guard let lines = command.makeRenderCommandEncoder(descriptor: Self.pass(texture, load: .dontCare))
            else { return nil }
            lines.setRenderPipelineState(contour)
            bind(lines, ripplesToo: false)
            lines.setFragmentBytes(&grid, length: MemoryLayout<SIMD4<Float>>.stride, index: 3)
            lines.setFragmentTexture(heights, index: 0)
            lines.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
            lines.endEncoding()
        } else {
            return nil
        }
        if let drawable { command.present(drawable) }
        if let completed { command.addCompletedHandler(completed) }
        command.commit()
        return command
    }

    /// One attachment pass. The full-screen triangle writes every pixel, so nothing needs loading.
    private static func pass(_ texture: any MTLTexture, load: MTLLoadAction) -> MTLRenderPassDescriptor {
        let pass = MTLRenderPassDescriptor()
        pass.colorAttachments[0].texture = texture
        pass.colorAttachments[0].loadAction = load
        pass.colorAttachments[0].storeAction = .store
        pass.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 0, 0)
        return pass
    }

    /// Reused while the surface keeps its size; a new size allocates once.
    private func heightTexture(width: Int, height: Int) -> (any MTLTexture)? {
        if let heights, heights.width == width, heights.height == height { return heights }
        let descriptor = MTLTextureDescriptor.texture2DDescriptor(
            pixelFormat: .r32Float, width: width, height: height, mipmapped: false)
        descriptor.usage = [.renderTarget, .shaderRead]
        descriptor.storageMode = .private
        heights = device.makeTexture(descriptor: descriptor)
        return heights
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
    /// Draws one frame again; set by the owning view. Called when a frame was skipped
    /// because the GPU was still busy and the surface has no running frame loop to catch up.
    var onRedraw: (() -> Void)?
    /// Frames committed but not yet finished by the GPU. Drawing never waits for them:
    /// at the limit a frame is skipped and redrawn once the GPU frees up.
    private var inFlight = 0
    private var skipped = false
    static let maxFramesInFlight = 2
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
    /// Ripples travel 180 pt/s; at the 20 fps idle cap they would jump 9 pt per frame.
    var rippling: Bool { model?.ripples.isEmpty == false }

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
        guard inFlight < Self.maxFramesInFlight else {
            skipped = true
            return
        }
        guard let drawable = layer.nextDrawable() else { return }
        skipped = false
        let frame = integrator.frame(
            model: model, size: size, origin: origin, now: .now,
            scheme: scheme, displayScale: scale,
            still: TopoFramePacing.isStill(still: still, lowPower: lowPower), paused: paused)
        let completed: MTLCommandBufferHandler = { [weak self] _ in
            Task { @MainActor [weak self] in self?.frameFinished() }
        }
        guard renderer.render(frame, into: drawable.texture, drawable: drawable, completed: completed) != nil
        else { return }
        framesDrawn += 1
        inFlight += 1
    }

    private func frameFinished() {
        inFlight -= 1
        guard skipped, !stopped else { return }
        skipped = false
        onRedraw?()
    }

    func stop(layer: CAMetalLayer) {
        stopped = true
        if let powerObserver { NotificationCenter.default.removeObserver(powerObserver) }
        powerObserver = nil
        onRefresh = nil
        onRedraw = nil
        model = nil
        renderer = nil
        layer.device = nil
    }
}
#endif
