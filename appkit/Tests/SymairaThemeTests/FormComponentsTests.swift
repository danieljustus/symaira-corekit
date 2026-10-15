import SwiftUI
import XCTest

@testable import SymairaTheme

@MainActor
final class FormComponentsTests: XCTestCase {
    func testTextFieldStyleShorthandIsAvailable() {
        let plain: SymairaTextFieldStyle = .symaira
        let focused: SymairaTextFieldStyle = .symaira(isFocused: true)
        XCTAssertNotNil(plain)
        XCTAssertNotNil(focused)
    }

    func testFormSectionAcceptsTitleAndFooter() {
        let section = SymairaFormSection("Storage", footer: "Kept on this Mac.") {
            Text("row")
        }
        ThemeRenderHost.render(section)
    }

    func testFormSectionWorksWithoutTitleOrFooter() {
        let section = SymairaFormSection { Text("row") }
        ThemeRenderHost.render(section)
    }

    func testFormRowSupportsALabelOnlyVariant() {
        let row = SymairaFormRow("Model", description: "Used for search.")
        ThemeRenderHost.render(row)
    }

    func testFormRowSupportsATrailingControl() {
        let row = SymairaFormRow("Enabled") { Toggle("", isOn: .constant(true)) }
        ThemeRenderHost.render(row)
    }

    func testFormRowClearsTheMinimumControlHeight() {
        XCTAssertGreaterThanOrEqual(SymairaMetrics.minimumControlHeight, 34)
    }

    func testStatusDotRequiresAnAccessibilityLabel() {
        let dot = SymairaStatusDot(tone: .positive, accessibilityLabel: "Connected")
        ThemeRenderHost.render(dot)
    }

    func testStatusLabelPairsToneWithVisibleText() {
        let label = SymairaStatusLabel("Disconnected", tone: .critical)
        ThemeRenderHost.render(label)
    }

    func testStatusTonesResolveToDistinctColours() {
        let tones: [SymairaTone] = [.neutral, .positive, .warning, .critical, .informative]
        let dark = Set(tones.map { $0.foreground(for: .dark) })
        let light = Set(tones.map { $0.foreground(for: .light) })
        XCTAssertEqual(dark.count, tones.count)
        XCTAssertEqual(light.count, tones.count)
    }
}
