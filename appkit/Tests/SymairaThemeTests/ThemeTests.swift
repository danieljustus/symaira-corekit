import XCTest
import SwiftUI
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
}
