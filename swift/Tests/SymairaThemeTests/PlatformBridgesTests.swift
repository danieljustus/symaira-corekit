import SwiftUI
import XCTest

@testable import SymairaTheme

@MainActor
final class PlatformBridgesTests: XCTestCase {
    /// Tab bars render only `Image`; every icon must produce a non-empty still frame.
    func testEveryIconRendersAStillImageWithInk() throws {
        for icon in SymairaIcon.allCases {
            let renderer = ImageRenderer(content: SymairaIconStill(icon: icon, size: 24))
            renderer.scale = 2
            let image = try XCTUnwrap(renderer.cgImage, "\(icon) produced no image")
            XCTAssertEqual(image.width, 48)
            XCTAssertTrue(hasOpaquePixel(image), "\(icon) rendered blank")
            _ = Image(symairaIcon: icon)
        }
    }

    private func hasOpaquePixel(_ image: CGImage) -> Bool {
        let w = image.width
        let h = image.height
        var data = [UInt8](repeating: 0, count: w * h * 4)
        guard
            let ctx = CGContext(
                data: &data, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
        else { return false }
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
        return stride(from: 3, to: data.count, by: 4).contains { data[$0] > 128 }
    }
}
