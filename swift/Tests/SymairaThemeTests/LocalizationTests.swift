import Foundation
import XCTest

@testable import SymairaTheme

/// The shared components resolve their strings from the compiled package
/// resources, not from literals, and every language carries every key (#195).
final class LocalizationTests: XCTestCase {
    private func table(_ language: String) throws -> Bundle {
        let path = try XCTUnwrap(
            SymairaThemeResources.bundle.path(forResource: language, ofType: "lproj"),
            "\(language).lproj must ship in the SymairaTheme bundle")
        return try XCTUnwrap(Bundle(path: path))
    }

    private func keys(_ language: String) throws -> Set<String> {
        let bundle = try table(language)
        let url = try XCTUnwrap(bundle.url(forResource: "Localizable", withExtension: "strings"))
        let entries = try XCTUnwrap(NSDictionary(contentsOf: url) as? [String: String])
        return Set(entries.keys)
    }

    func testEnglishAndGermanCarryTheSameKeys() throws {
        let english = try keys("en")
        XCTAssertFalse(english.isEmpty)
        XCTAssertEqual(try keys("de"), english)
    }

    func testSidebarResizeHandleResolvesGerman() throws {
        let german = try table("de")
        XCTAssertEqual(
            SymairaStrings.string("sidebar.resize.label", "Resize sidebar", bundle: german), "Seitenleiste anpassen")
        let help = SymairaStrings.string("sidebar.resize.help", "", bundle: german)
        XCTAssertTrue(help.contains("Pfeiltasten"), help)
    }

    func testEnglishFallbackMatchesTheEnglishTable() throws {
        let english = try table("en")
        XCTAssertEqual(SymairaStrings.string("sidebar.resize.label", "", bundle: english), "Resize sidebar")
        // A missing key falls back to the English default instead of showing the key.
        XCTAssertEqual(SymairaStrings.string("sidebar.missing", "Fallback", bundle: english), "Fallback")
    }

    /// Shared components with fixed copy resolve German, including positional format arguments (#197).
    func testSharedComponentCopyResolvesGerman() throws {
        let german = try table("de")
        let expected = [
            "common.close": "Schließen", "common.cancel": "Abbrechen", "common.retry": "Erneut versuchen",
            "common.locked": "Gesperrt", "settings.title": "Einstellungen", "appearance.title": "Erscheinungsbild",
            "onboarding.next": "Weiter", "navigate.menu": "Navigieren",
        ]
        for (key, value) in expected {
            XCTAssertEqual(SymairaStrings.string(key, "", bundle: german), value, key)
        }
        let step = SymairaStrings.string("onboarding.step", "", bundle: german)
        XCTAssertEqual(String(format: step, 2, 5), "Schritt 2 von 5")
        XCTAssertEqual(SymairaStrings.onboardingStep(2, of: 5).filter(\.isNumber), "25")
    }

    #if os(macOS)
    /// The native splitter keeps its role and identifier and carries the resolved strings.
    @MainActor
    func testResizeHandleCarriesLocalizedAccessibility() {
        let handle = SymairaSidebarResizeHandle(width: 272, isEnabled: true, onResize: { _ in }, onStep: { _ in })
        let view = handle.configured(SymairaSidebarResizeHandle.Handle())
        XCTAssertEqual(view.accessibilityRole(), .splitter)
        XCTAssertEqual(view.accessibilityIdentifier(), "symaira-sidebar-resize")
        XCTAssertEqual(view.accessibilityLabel(), SymairaStrings.sidebarResizeLabel)
        XCTAssertEqual(view.toolTip, SymairaStrings.sidebarResizeHelp)
    }
    #endif
}
