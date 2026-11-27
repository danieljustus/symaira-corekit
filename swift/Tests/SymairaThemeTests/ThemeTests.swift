import SwiftUI
import XCTest

@testable import SymairaTheme

final class ThemeTests: XCTestCase {
    func testFeedbackSpringsMatchApprovedParameters() {
        XCTAssertEqual(SymairaTheme.springPress, .spring(duration: 0.25, bounce: 0.45))
        XCTAssertEqual(SymairaTheme.springPop, .spring(duration: 0.5, bounce: 0.5))
        XCTAssertEqual(SymairaTheme.springFill, .spring(duration: 0.9, bounce: 0.15))
    }

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

    /// The generated palette must match DESIGN.md: CI does not run build.py, so an edited
    /// spec without regenerated tokens fails here instead of drifting silently.
    func testGeneratedPaletteMatchesTheTokenSpec() throws {
        let spec = try String(contentsOf: Self.tokenSpec, encoding: .utf8)
        let front = try XCTUnwrap(spec.components(separatedBy: "\n---\n").first)
        let colors = try XCTUnwrap(
            front.components(separatedBy: "\ncolors:\n").last?
                .components(separatedBy: "\ntypography:\n").first)
        var specColors: [String: Int] = [:]
        for line in colors.split(separator: "\n") {
            let parts = line.trimmingCharacters(in: .whitespaces).split(separator: ":", maxSplits: 1)
            guard parts.count == 2, !parts[0].hasPrefix("#") else { continue }
            let hex = parts[1].trimmingCharacters(in: CharacterSet(charactersIn: " \"#"))
            specColors[String(parts[0])] = Int(hex, radix: 16)
        }
        let roles = specColors.keys.filter { !$0.hasSuffix("-dark") }
        XCTAssertEqual(Set(roles), Set(SymairaTokens.Palette.byName.keys), "rerun design/liquid-topography/build.py")
        for role in roles {
            let pair = try XCTUnwrap(SymairaTokens.Palette.byName[role], role)
            XCTAssertEqual(pair.light, specColors[role], "\(role) light: rerun build.py")
            XCTAssertEqual(pair.dark, specColors[role + "-dark"] ?? specColors[role], "\(role) dark: rerun build.py")
        }
    }

    /// The `for:` helpers read the generated palette instead of keeping their own hex copies.
    func testAppearanceHelpersReadTheGeneratedPalette() {
        let helpers: [(String, (ColorScheme) -> Color, SymairaTokens.Pair)] = [
            ("canvas", SymairaTheme.backgroundPrimary, SymairaTokens.Palette.canvas),
            ("sidebar", SymairaTheme.backgroundSecondary, SymairaTokens.Palette.sidebar),
            ("surface", SymairaTheme.surfaceOpaque, SymairaTokens.Palette.surface),
            ("raised", SymairaTheme.surfaceRaised, SymairaTokens.Palette.raised),
            ("control-outline", SymairaTheme.controlOutline, SymairaTokens.Palette.controlOutline),
            ("control-outline", SymairaTheme.raisedOutline, SymairaTokens.Palette.controlOutline),
            ("line", SymairaTheme.line, SymairaTokens.Palette.line),
            ("selection", SymairaTheme.navigationSelection, SymairaTokens.Palette.selection),
            ("ink", SymairaTheme.foregroundPrimary, SymairaTokens.Palette.ink),
            ("ink-2", SymairaTheme.foregroundSecondary, SymairaTokens.Palette.ink2),
            ("ink-3", SymairaTheme.foregroundMuted, SymairaTokens.Palette.ink3),
            ("primary", SymairaTheme.accent, SymairaTokens.Palette.primary),
            ("selected", SymairaTheme.selected, SymairaTokens.Palette.selected),
            ("on-selected", SymairaTheme.onSelected, SymairaTokens.Palette.onSelected),
            ("focus", SymairaTheme.focus, SymairaTokens.Palette.focus),
        ]
        for (role, helper, pair) in helpers {
            for scheme in [ColorScheme.light, .dark] {
                XCTAssertEqual(helper(scheme), pair.color(for: scheme), "\(role) \(scheme)")
            }
        }
    }

    /// #515: control boundaries reach 3:1 on every surface they sit on; #513: the destructive
    /// label reaches 4.5:1 on its fill.
    func testControlOutlineAndDestructiveLabelMeetWCAG() {
        func luminance(_ hex: Int) -> Double {
            let c = SymairaTokens.Pair.components(hex)
            return zip([c.red, c.green, c.blue], [0.2126, 0.7152, 0.0722]).map { value, weight in
                weight * (value <= 0.04045 ? value / 12.92 : pow((value + 0.055) / 1.055, 2.4))
            }.reduce(0, +)
        }
        func ratio(_ a: Int, _ b: Int) -> Double {
            let (x, y) = (luminance(a), luminance(b))
            return (max(x, y) + 0.05) / (min(x, y) + 0.05)
        }
        let palette = SymairaTokens.Palette.self
        for background in [palette.raised, palette.surface, palette.canvas] {
            XCTAssertGreaterThanOrEqual(ratio(palette.controlOutline.light, background.light), 3)
            XCTAssertGreaterThanOrEqual(ratio(palette.controlOutline.dark, background.dark), 3)
        }
        XCTAssertGreaterThanOrEqual(ratio(palette.onCritical.light, palette.critical.light), 4.5)
        XCTAssertGreaterThanOrEqual(ratio(palette.onCritical.dark, palette.critical.dark), 4.5)
    }

    static let tokenSpec = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("design/liquid-topography/DESIGN.md")

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
