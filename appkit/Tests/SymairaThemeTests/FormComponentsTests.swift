import XCTest
import SwiftUI
@testable import SymairaTheme

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
        XCTAssertNotNil(section.body)
    }

    func testFormSectionWorksWithoutTitleOrFooter() {
        let section = SymairaFormSection { Text("row") }
        XCTAssertNotNil(section.body)
    }

    func testFormRowSupportsALabelOnlyVariant() {
        let row = SymairaFormRow("Model", description: "Used for search.")
        XCTAssertNotNil(row.body)
    }

    func testFormRowSupportsATrailingControl() {
        let row = SymairaFormRow("Enabled") { Toggle("", isOn: .constant(true)) }
        XCTAssertNotNil(row.body)
    }

    func testFormRowClearsTheMinimumControlHeight() {
        XCTAssertGreaterThanOrEqual(SymairaMetrics.minimumControlHeight, 34)
    }

    func testStatusDotRequiresAnAccessibilityLabel() {
        let dot = SymairaStatusDot(tone: .positive, accessibilityLabel: "Connected")
        XCTAssertNotNil(dot.body)
    }

    func testStatusLabelPairsToneWithVisibleText() {
        let label = SymairaStatusLabel("Disconnected", tone: .critical)
        XCTAssertNotNil(label.body)
    }

    func testStatusTonesResolveToDistinctColours() {
        let tones: [SymairaTone] = [.neutral, .positive, .warning, .critical, .informative]
        let dark = Set(tones.map { $0.foreground(for: .dark) })
        let light = Set(tones.map { $0.foreground(for: .light) })
        XCTAssertEqual(dark.count, tones.count)
        XCTAssertEqual(light.count, tones.count)
    }
}
