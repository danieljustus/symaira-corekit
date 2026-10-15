import SwiftUI
import XCTest

@testable import SymairaTheme

final class ThemeTests: XCTestCase {
    func testHexShortAndLongFormsAreEquivalent() {
        XCTAssertEqual(Color(hex: "FFF"), Color(hex: "FFFFFF"))
        XCTAssertEqual(Color(hex: "000"), Color(hex: "000000"))
    }

    func testHexIgnoresHashPrefix() {
        XCTAssertEqual(Color(hex: "#E5C397"), Color(hex: "E5C397"))
    }

    func testBrandGoldMatchesSpec() {
        XCTAssertEqual(SymairaTheme.goldPrimary, Color(hex: "#E5C397"))
    }

    func testLegacyColorAliasesPointToCanonicalTokens() {
        XCTAssertEqual(Color.symairaGold, SymairaTheme.goldPrimary)
        XCTAssertEqual(Color.symairaBg, SymairaTheme.bgDark)
        XCTAssertEqual(Color.symairaText, SymairaTheme.textPrimary)
        XCTAssertEqual(Color.symairaCard, SymairaTheme.bgCard)
    }

    func testMutedTextMeetsUpdatedBrandSpec() {
        XCTAssertEqual(SymairaTheme.textMuted, Color(hex: "837D74"))
    }

    func testAdaptivePaletteFollowsApprovedPilot() {
        XCTAssertEqual(SymairaTheme.backgroundPrimary(for: .dark), Color(hex: "1C1C1B"))
        XCTAssertEqual(SymairaTheme.foregroundPrimary(for: .dark), Color(hex: "EEEDEA"))
        XCTAssertEqual(SymairaTheme.surfaceOpaque(for: .dark), Color(hex: "141413"))
        XCTAssertEqual(SymairaTheme.backgroundPrimary(for: .light), Color(hex: "EEEDEA"))
        XCTAssertEqual(SymairaTheme.foregroundPrimary(for: .light), Color(hex: "141413"))
        XCTAssertEqual(SymairaTheme.foregroundMuted(for: .light), Color(hex: "62615D"))
        XCTAssertEqual(SymairaTheme.accent(for: .dark), Color(hex: "E0D2BA"))
        XCTAssertEqual(SymairaTheme.accent(for: .light), SymairaTheme.accent(for: .dark))
    }

    /// Decision A: light-mode selection is ink, never pale champagne (about 1.2:1).
    func testSelectionUsesInkInLightAndChampagneInDark() {
        XCTAssertEqual(SymairaTheme.selected(for: .light), Color(hex: "141413"))
        XCTAssertEqual(SymairaTheme.selected(for: .dark), Color(hex: "E0D2BA"))
        XCTAssertEqual(SymairaTheme.onSelected(for: .light), Color(hex: "E1E0DA"))
        XCTAssertEqual(SymairaTheme.focus(for: .light), SymairaTheme.selected(for: .light))
    }

    /// The shared helpers must mirror the generated design-kit tokens; this pins both sides.
    func testContrastOfApprovedRoles() {
        func luminance(_ hex: String) -> Double {
            let value = Int(hex, radix: 16)!
            return [16, 8, 0].map { Double((value >> $0) & 0xFF) / 255 }
                .map { $0 <= 0.04045 ? $0 / 12.92 : pow(($0 + 0.055) / 1.055, 2.4) }
                .enumerated().map { [0.2126, 0.7152, 0.0722][$0.offset] * $0.element }.reduce(0, +)
        }
        func ratio(_ a: String, _ b: String) -> Double {
            let (x, y) = (luminance(a), luminance(b))
            return (max(x, y) + 0.05) / (min(x, y) + 0.05)
        }
        XCTAssertGreaterThanOrEqual(ratio("141413", "EEEDEA"), 3, "light selected vs rail")
        XCTAssertGreaterThanOrEqual(ratio("E1E0DA", "141413"), 4.5, "light on-selected text")
        XCTAssertGreaterThanOrEqual(ratio("62615D", "E1E0DA"), 4.5, "light muted text on surface")
        XCTAssertGreaterThanOrEqual(ratio("34694A", "E1E0DA"), 4.5, "light positive on surface")
        XCTAssertGreaterThanOrEqual(ratio("7E5310", "E1E0DA"), 4.5, "light warning on surface")
        XCTAssertGreaterThanOrEqual(ratio("9A4634", "E1E0DA"), 4.5, "light critical on surface")
        XCTAssertGreaterThanOrEqual(ratio("E0D2BA", "2B2B2A"), 3, "dark selected vs rail")
        XCTAssertGreaterThanOrEqual(ratio("1A1814", "E0D2BA"), 4.5, "dark on-selected text")
        XCTAssertGreaterThanOrEqual(ratio("97958F", "141413"), 4.5, "dark muted text on surface")
    }

    func testSemanticTonesAdaptForLightAppearance() {
        XCTAssertEqual(SymairaTone.critical.foreground, SymairaTheme.critical)
        XCTAssertEqual(SymairaTone.critical.foreground(for: .light), Color(hex: "9A4634"))
        XCTAssertEqual(SymairaTone.positive.foreground(for: .light), Color(hex: "34694A"))
        XCTAssertEqual(SymairaTone.positive.systemImage, "checkmark.circle.fill")
    }

    @MainActor
    func testFoundationComponentsCanBeConstructed() {
        _ = SymairaBackdrop(gridStyle: .dots)
        _ = SymairaBadge("Ready", tone: .positive)
        _ = SymairaNotice(title: "Connected", message: "The local core is ready.", tone: .positive)
        _ = SymairaEmptyState(systemImage: "tray", title: "No items", message: "Add your first item.")
        _ = SymairaLoadingState("Loading")
        _ = SymairaGlassEffectContainer {
            Button("Refresh") {}
                .symairaButtonStyle(.toolbar)
        }
    }
}
