#if os(macOS)
import AppKit
import Metal
import SwiftUI
import XCTest

@testable import SymairaTheme

@MainActor
final class TopoMetalTests: XCTestCase {
    func testMetalMatchesStitchableShader() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { throw XCTSkip("No Metal device") }
        let previous = SymairaTopoView.startPhase
        SymairaTopoView.startPhase = { 0 }
        defer { SymairaTopoView.startPhase = previous }
        let model = SymairaTopoModel()
        model.rects["protected"] = (CGRect(x: 100, y: 60, width: 80, height: 60), true)
        let pipeline = try TopoMetalPipeline(device: device)
        // Check both appearances and Retina point-to-pixel conversion.
        for scheme in [ColorScheme.dark, .light] {
            for scale in [CGFloat(1), 2] {
                let frame = TopoFrameIntegrator().frame(
                    model: model, size: CGSize(width: 300, height: 200), origin: .zero,
                    now: Date(timeIntervalSinceReferenceDate: 100), scheme: scheme,
                    displayScale: scale, still: true, paused: true)
                let descriptor = MTLTextureDescriptor.texture2DDescriptor(
                    pixelFormat: .bgra8Unorm, width: Int(300 * scale), height: Int(200 * scale), mipmapped: false)
                descriptor.usage = [.renderTarget]
                descriptor.storageMode = .shared
                let texture = try XCTUnwrap(device.makeTexture(descriptor: descriptor))
                let command = try XCTUnwrap(pipeline.render(frame, into: texture))
                command.waitUntilCompleted()
                XCTAssertEqual(command.status, .completed)
                var actual = [UInt8](repeating: 0, count: texture.width * texture.height * 4)
                texture.getBytes(
                    &actual, bytesPerRow: texture.width * 4,
                    from: MTLRegionMake2D(0, 0, texture.width, texture.height), mipmapLevel: 0)
                let view = Rectangle().fill(SymairaTokens.canvas).colorEffect(frame.shader)
                    .frame(width: 300, height: 200).environment(\.colorScheme, scheme)
                let renderer = ImageRenderer(content: view)
                renderer.scale = scale
                let image = try XCTUnwrap(renderer.cgImage)
                var expected = [UInt8](repeating: 0, count: actual.count)
                let context = try XCTUnwrap(
                    CGContext(
                        data: &expected, width: image.width, height: image.height, bitsPerComponent: 8,
                        bytesPerRow: image.width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
                context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
                var maximum = 0
                var total = 0
                for i in stride(from: 0, to: actual.count, by: 4) {
                    for channel in 0..<3 {
                        let difference = abs(Int(actual[i + 2 - channel]) - Int(expected[i + channel]))
                        maximum = max(maximum, difference)
                        total += difference
                    }
                }
                let mean = Double(total) / Double(texture.width * texture.height * 3)
                print("Metal parity scheme=\(scheme) scale=\(scale) max=\(maximum) mean=\(mean)")

                // Two 8-bit levels allow half-float rounding and sRGB conversion;
                // the mean bound prevents a systematic color-space mismatch.
                XCTAssertLessThanOrEqual(maximum, 2)
                XCTAssertLessThanOrEqual(mean, 0.25)
            }
        }
    }

    func testAnimationDoesNotLayoutOuterHost() throws {
        let model = SymairaTopoModel()
        let view = SymairaTopoView(model: model).frame(width: 480, height: 320)
            .coordinateSpace(name: SymairaTopo.space)
        let host = CountingHost(rootView: view)
        let window = NSWindow(
            contentRect: CGRect(x: -2000, y: -2000, width: 480, height: 320),
            styleMask: .borderless, backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = host
        window.orderFront(nil)
        defer { window.close() }
        pump(0.3)
        let native = try XCTUnwrap(findMetal(in: host))
        // An offscreen window is occluded; configure visibility directly for this
        // harness only, leaving the real view's independent frame loop unchanged.
        native.configure(model: model, origin: .zero, scheme: .dark, still: false, visible: true)
        pump(0.2)
        host.layouts = 0
        let initial = native.framesDrawn
        pump(1.1)
        let frames = native.framesDrawn - initial
        guard frames > 0 else { throw XCTSkip("Window server cannot produce Metal frames") }
        print("Metal layout regression frames=\(frames) outerLayouts=\(host.layouts)")
        XCTAssertGreaterThanOrEqual(frames, 5)
        // At most two deferred AppKit settling passes; never a pass per frame.
        XCTAssertLessThanOrEqual(host.layouts, 2)
        native.configure(model: model, origin: .zero, scheme: .dark, still: true, visible: true)
        let stoppedAt = native.framesDrawn
        pump(0.2)
        XCTAssertEqual(native.framesDrawn, stoppedAt, "Static mode must stop the frame timer")
        model.rects["new"] = (CGRect(x: 0, y: 0, width: 100, height: 100), false)
        pump(0.1)
        XCTAssertGreaterThan(native.framesDrawn, stoppedAt, "Static protection changes must redraw on demand")
        native.stop()
    }

    private func pump(_ seconds: TimeInterval) {
        let end = Date.now.addingTimeInterval(seconds)
        while Date.now < end { RunLoop.main.run(until: min(end, Date.now.addingTimeInterval(0.01))) }
    }
    private func findMetal(in view: NSView) -> TopoMetalView? {
        if let metal = view as? TopoMetalView { return metal }
        return view.subviews.lazy.compactMap { self.findMetal(in: $0) }.first
    }
}

@MainActor
private final class CountingHost<Content: View>: NSHostingView<Content> {
    var layouts = 0
    override func layout() {
        layouts += 1
        super.layout()
    }
}
#endif
