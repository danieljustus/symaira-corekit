#if os(macOS)
import ImageIO
import Metal
import SwiftUI
import XCTest

@testable import SymairaTheme

/// The two-pass surface against the single-pass reference: GPU cost at iPhone size and
/// rendered parity. Absolute times depend on this Mac's GPU; the ratio is what is checked.
@MainActor
final class TopoRenderCostTests: XCTestCase {
    /// A Learn-like page: six cards and two ripples on a surface of `size` points.
    static func pageFrame(
        model: SymairaTopoModel, size: CGSize, scale: CGFloat, at seconds: Double,
        scheme: ColorScheme = .dark
    ) -> TopoFrame {
        for (index, y) in [0.14, 0.34, 0.49, 0.64, 0.79, 0.92].enumerated() {
            model.rects["card\(index)"] = (
                CGRect(x: 24, y: size.height * y, width: size.width - 48, height: size.height * 0.11), true
            )
        }
        let now = Date(timeIntervalSinceReferenceDate: 1000 + seconds)
        model.ripples = [
            (CGPoint(x: size.width / 2, y: size.height * 0.45), now.addingTimeInterval(-0.4), 0.6),
            (CGPoint(x: 0, y: size.height / 2), now.addingTimeInterval(-1.1), 0.8),
        ]
        return TopoFrameIntegrator().frame(
            model: model, size: size, origin: .zero, now: now, scheme: scheme,
            displayScale: scale, still: false, paused: false)
    }

    /// BGRA bytes to a PNG, for looking at a parity run (`TOPO_PARITY_DUMP=<directory>`).
    private static func writePNG(_ bytes: [UInt8], width: Int, height: Int, to path: String) {
        var data = bytes
        guard
            let context = CGContext(
                data: &data, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
                space: CGColorSpace(name: CGColorSpace.sRGB)!,
                bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue),
            let image = context.makeImage(),
            let destination = CGImageDestinationCreateWithURL(
                URL(fileURLWithPath: path) as CFURL, "public.png" as CFString, 1, nil)
        else { return }
        CGImageDestinationAddImage(destination, image, nil)
        CGImageDestinationFinalize(destination)
    }

    private static func target(_ device: any MTLDevice, width: Int, height: Int, shared: Bool) throws -> any MTLTexture
    {
        let descriptor = MTLTextureDescriptor.texture2DDescriptor(
            pixelFormat: .bgra8Unorm, width: width, height: height, mipmapped: false)
        descriptor.usage = [.renderTarget]
        descriptor.storageMode = shared ? .shared : .private
        return try XCTUnwrap(device.makeTexture(descriptor: descriptor))
    }

    /// Median GPU time of one iPhone 17 frame (402 × 874 pt at 3x).
    static func medianGPUMilliseconds(_ pipeline: TopoMetalPipeline, frames: Int = 40) throws -> Double {
        let texture = try target(pipeline.device, width: 1206, height: 2622, shared: false)
        let model = SymairaTopoModel()
        var times: [Double] = []
        for index in 0..<(frames + 5) {
            let frame = pageFrame(model: model, size: CGSize(width: 402, height: 874), scale: 3, at: Double(index) / 20)
            let command = try XCTUnwrap(pipeline.render(frame, into: texture))
            command.waitUntilCompleted()
            XCTAssertEqual(command.status, .completed)
            if index >= 5 { times.append((command.gpuEndTime - command.gpuStartTime) * 1000) }
        }
        return times.sorted()[times.count / 2]
    }

    func testTwoPassCostsAFractionOfTheReference() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { throw XCTSkip("No Metal device") }
        let reference = try Self.medianGPUMilliseconds(TopoMetalPipeline(device: device, reference: true))
        let twoPass = try Self.medianGPUMilliseconds(TopoMetalPipeline(device: device))
        print(
            String(
                format: "Topography GPU per 1206x2622 frame on %@: reference %.3f ms, two-pass %.3f ms, ratio %.3f",
                device.name, reference, twoPass, twoPass / reference))
        XCTAssertLessThan(twoPass, reference / 3, "the height grid must remove most of the per-pixel noise work")
    }

    func testTwoPassMatchesReference() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { throw XCTSkip("No Metal device") }
        let previous = SymairaTopoView.startPhase
        SymairaTopoView.startPhase = { 0 }
        defer { SymairaTopoView.startPhase = previous }
        let reference = try TopoMetalPipeline(device: device, reference: true)
        let twoPass = try TopoMetalPipeline(device: device)
        for scheme in [ColorScheme.dark, .light] {
            for scale in [CGFloat(1), 2, 3] {
                let size = CGSize(width: 402, height: 874)
                let frame = Self.pageFrame(model: SymairaTopoModel(), size: size, scale: scale, at: 7, scheme: scheme)
                let width = Int(size.width * scale)
                let height = Int(size.height * scale)
                var images: [[UInt8]] = []
                for pipeline in [reference, twoPass] {
                    let texture = try Self.target(device, width: width, height: height, shared: true)
                    let command = try XCTUnwrap(pipeline.render(frame, into: texture))
                    command.waitUntilCompleted()
                    XCTAssertEqual(command.status, .completed)
                    var bytes = [UInt8](repeating: 0, count: width * height * 4)
                    texture.getBytes(
                        &bytes, bytesPerRow: width * 4, from: MTLRegionMake2D(0, 0, width, height), mipmapLevel: 0)
                    images.append(bytes)
                }
                var maximum = 0
                var total = 0
                var visible = 0
                for i in stride(from: 0, to: images[0].count, by: 4) {
                    var pixel = 0
                    for channel in 0..<3 {
                        let difference = abs(Int(images[0][i + channel]) - Int(images[1][i + channel]))
                        pixel = max(pixel, difference)
                        total += difference
                    }
                    maximum = max(maximum, pixel)
                    if pixel > 2 { visible += 1 }
                }
                if let directory = ProcessInfo.processInfo.environment["TOPO_PARITY_DUMP"] {
                    for (name, bytes) in zip(["reference", "twopass"], images) {
                        Self.writePNG(
                            bytes, width: width, height: height,
                            to: "\(directory)/\(name)-\(scheme)-\(Int(scale))x.png")
                    }
                    var diff = [UInt8](repeating: 255, count: images[0].count)
                    for i in stride(from: 0, to: diff.count, by: 4) {
                        let d = (0..<3).map { abs(Int(images[0][i + $0]) - Int(images[1][i + $0])) }.max()!
                        let v = UInt8(min(255, d * 10))
                        diff[i] = 0
                        diff[i + 1] = 0
                        diff[i + 2] = v
                    }
                    Self.writePNG(
                        diff, width: width, height: height, to: "\(directory)/diff-\(scheme)-\(Int(scale))x.png")
                }
                let mean = Double(total) / Double(width * height * 3)
                let share = Double(visible) / Double(width * height)
                print(
                    String(
                        format: "Two-pass parity scheme=%@ scale=%.0f max=%d mean=%.4f share>2=%.5f",
                        "\(scheme)", scale, maximum, mean, share))
                // The B-spline shifts a line by one or two device pixels where the field is flat
                // or bends tightly, so single pixels may differ by a full line; no bound on `max`.
                // Measured on an M4 Pro: mean <= 0.032 and share <= 0.004 across start phases.
                XCTAssertLessThanOrEqual(mean, 0.1, "systematic deviation from the per-pixel field")
                XCTAssertLessThanOrEqual(share, 0.01, "lines must stay where the per-pixel field draws them")
            }
        }
    }
}
#endif
