import XCTest

@testable import SymairaTheme

@MainActor
final class LockedLabelTests: XCTestCase {
    func testDefaultLabelIsEnglish() {
        XCTAssertEqual(SymairaLockedLabel().text, "Locked")
    }

    func testCustomReasonIsPreserved() {
        XCTAssertEqual(SymairaLockedLabel("Permission Required").text, "Permission Required")
    }
}
