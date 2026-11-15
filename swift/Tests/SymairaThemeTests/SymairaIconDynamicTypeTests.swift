import SwiftUI
import XCTest

@testable import SymairaTheme

/// Symaira icons follow Dynamic Type like the label text next to them (#484).
@MainActor
final class SymairaIconDynamicTypeTests: XCTestCase {
    func testIconKeepsBaseSizeAtDefaultTextSize() throws {
        let width = try renderedWidth(SymairaIconView(.home, size: 20).environment(\.dynamicTypeSize, .large))
        XCTAssertEqual(width, 20, accuracy: 0.5)
    }

    func testIconGrowsAtAccessibilityTextSizes() throws {
        try skipWithoutDynamicType()
        let base = try renderedWidth(SymairaIconView(.home, size: 20).environment(\.dynamicTypeSize, .large))
        let large = try renderedWidth(
            SymairaIconView(.home, size: 20).environment(\.dynamicTypeSize, .accessibility3))
        XCTAssertGreaterThan(large, base * 1.5)
    }

    func testLabelIconGrowsWithItsText() throws {
        try skipWithoutDynamicType()
        // Icon-only style isolates the icon: the text would grow the label on its own.
        let label = Label("Sync", symairaIcon: .refresh).labelStyle(.iconOnly)
        let base = try renderedWidth(label.environment(\.dynamicTypeSize, .large))
        let large = try renderedWidth(label.environment(\.dynamicTypeSize, .accessibility3))
        XCTAssertGreaterThan(large, base * 1.5)
    }

    /// macOS has no Dynamic Type: neither text nor `@ScaledMetric` follows
    /// `dynamicTypeSize` there, so growth is asserted on iOS (CI runs this
    /// suite on an iOS Simulator).
    private func skipWithoutDynamicType() throws {
        #if os(macOS)
        throw XCTSkip("Dynamic Type scaling applies on iOS; macOS keeps the base size")
        #endif
    }

    private func renderedWidth(_ view: some View) throws -> CGFloat {
        let renderer = ImageRenderer(content: view)
        #if os(macOS)
        return try XCTUnwrap(renderer.nsImage).size.width
        #else
        return try XCTUnwrap(renderer.uiImage).size.width
        #endif
    }
}
