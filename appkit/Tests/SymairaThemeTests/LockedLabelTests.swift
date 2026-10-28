import XCTest

@testable import SymairaTheme

@MainActor
final class LockedLabelTests: XCTestCase {
    func testDefaultLabelIsLocalized() {
        XCTAssertEqual(SymairaLockedLabel().text, SymairaStrings.locked)
    }

    func testCustomReasonIsPreserved() {
        XCTAssertEqual(SymairaLockedLabel("Permission Required").text, "Permission Required")
    }
}
