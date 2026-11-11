import SwiftUI
import XCTest

@testable import SymairaTheme

/// Regression checks for the meter palette: an empty track must not read as a
/// filled bar (#476).
@MainActor
final class MeterTests: XCTestCase {
    func testTrackIsAQuietGrooveNotTheInk3TextRole() {
        XCTAssertNotEqual(SymairaBarColors.track, SymairaTokens.ink3)
        XCTAssertEqual(SymairaBarColors.track, SymairaTokens.raised)
        XCTAssertEqual(SymairaBarColors.trackOutline, SymairaTokens.line)
    }

    func testTrackFillAndOutlineAreDistinctRoles() {
        XCTAssertEqual(SymairaBarColors.fill, SymairaTokens.ink)
        XCTAssertNotEqual(SymairaBarColors.track, SymairaBarColors.fill)
        XCTAssertNotEqual(SymairaBarColors.trackOutline, SymairaBarColors.fill)
        XCTAssertNotEqual(SymairaBarColors.track, SymairaBarColors.trackOutline)
    }

    func testProgressStyleKeepsSourceCompatibleInitializers() {
        _ = SymairaProgressStyle()
        _ = SymairaProgressStyle(height: 12)
        _ = SymairaProgressStyle(height: 6, track: SymairaTokens.selection)
    }

    func testStatTileInitializersAreSourceStable() {
        _ = SymairaStatTile(value: "12", label: "Profiles")
        _ = SymairaStatTile(value: "3 of 5", label: "Folders Ready", detail: "2 missing")
        _ = SymairaStatTile(value: "7 days", label: "Streak", showsCard: false)
    }
}

#if os(macOS)
import AppKit

extension MeterTests {
    func testEmptyMeterDiffersFromFilledMeterInBothAppearances() throws {
        for scheme in [ColorScheme.light, .dark] {
            let empty = try pixel(fraction: 0, scheme: scheme, x: 0.5)
            let full = try pixel(fraction: 1, scheme: scheme, x: 0.5)
            XCTAssertNotEqual(empty, full, "0% and 100% must be visibly different in \(scheme)")

            let rightOfHalf = try pixel(fraction: 0.5, scheme: scheme, x: 0.85)
            XCTAssertEqual(rightOfHalf, empty, "the unfilled remainder shows the empty groove in \(scheme)")
            let leftOfHalf = try pixel(fraction: 0.5, scheme: scheme, x: 0.15)
            XCTAssertEqual(leftOfHalf, full, "the filled part shows the fill in \(scheme)")
        }
    }

    func testStatTileRendersWithAndWithoutCardAndDetail() {
        for scheme in [ColorScheme.light, .dark] {
            for tile in [
                SymairaStatTile(value: "12", label: "Profiles"),
                SymairaStatTile(value: "3 of 5", label: "Folders Ready", detail: "2 missing"),
                SymairaStatTile(value: "7 days", label: "Streak", showsCard: false),
            ] {
                ThemeRenderHost.render(tile.environment(\.colorScheme, scheme))
            }
        }
    }

    /// Color of the meter at the horizontal fraction `x`, vertically centred, on a `surface` card.
    private func pixel(fraction: Double, scheme: ColorScheme, x: Double) throws -> [UInt8] {
        let width: CGFloat = 200
        let renderer = ImageRenderer(
            content: ProgressView(value: fraction)
                .progressViewStyle(SymairaProgressStyle(height: 12))
                .frame(width: width)
                .padding(8)
                .background(SymairaTheme.surfaceOpaque(for: scheme))
                .environment(\.colorScheme, scheme))
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.cgImage)
        var bytes = [UInt8](repeating: 0, count: image.width * image.height * 4)
        let context = try XCTUnwrap(
            CGContext(
                data: &bytes, width: image.width, height: image.height, bitsPerComponent: 8,
                bytesPerRow: image.width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        let inset = 8.0 * 2
        let column = Int(inset + x * Double(width) * 2)
        let offset = ((image.height / 2) * image.width + column) * 4
        return Array(bytes[offset..<(offset + 3)])
    }
}
#endif
