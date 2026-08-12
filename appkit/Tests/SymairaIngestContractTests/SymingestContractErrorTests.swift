import XCTest
import Foundation
@testable import SymairaIngestContract

final class SymingestContractErrorTests: XCTestCase {
    // MARK: - errorDescription surface (all four cases)

    func testErrorDescriptionCoversAllFourCases() {
        let cases: [(SymingestContractError, String)] = [
            (.missingBinary, "symingest is not installed or not on PATH."),
            (.unsupportedSchema(2), "Unsupported symingest schema version 2."),
            (.unsupportedSchema(9), "Unsupported symingest schema version 9."),
            (.invalidResponse, "Invalid symingest JSON response."),
            (.commandFailed("boom"), "boom"),
        ]
        for (error, expected) in cases {
            XCTAssertEqual(error.errorDescription, expected)
        }
    }

    // MARK: - decodeSchemaChecked(_:expecting:) nested-error rethrow

    /// A Decodable whose `init(from:)` throws a `SymingestContractError`.
    /// `decodeSchemaChecked` must rethrow it unchanged (not fold it into
    /// `.invalidResponse`) — this drives the `catch let error as
    /// SymingestContractError { throw error }` branch.
    private struct NestedThrowingDecodable: Decodable, Sendable {
        init(from decoder: any Decoder) throws {
            throw SymingestContractError.commandFailed("nested failure")
        }
    }

    func testDecodeSchemaCheckedRethrowsNestedSymingestError() {
        XCTAssertThrowsError(try decodeSchemaChecked(Data(#"{"schema_version":1}"#.utf8)) as NestedThrowingDecodable) { error in
            XCTAssertEqual(error as? SymingestContractError, .commandFailed("nested failure"))
        }
    }

    func testDecodeSchemaCheckedRethrowsNestedErrorEvenWithCustomVersion() {
        XCTAssertThrowsError(
            try decodeSchemaChecked(Data(#"{"schema_version":2}"#.utf8), expecting: 2) as NestedThrowingDecodable
        ) { error in
            XCTAssertEqual(error as? SymingestContractError, .commandFailed("nested failure"))
        }
    }

    func testDecodeSchemaCheckedPassesThroughSuccessfulDecode() throws {
        struct Payload: Decodable, Sendable, Equatable {
            let value: Int
        }
        let payload: Payload = try decodeSchemaChecked(Data(#"{"schema_version":1,"value":42}"#.utf8))
        XCTAssertEqual(payload, Payload(value: 42))
    }

    func testDecodeSchemaCheckedHonorsExpectingVersionOverride() {
        XCTAssertThrowsError(try decodeSchemaChecked(Data(#"{"schema_version":1}"#.utf8), expecting: 2) as PayloadDummy) { error in
            XCTAssertEqual(error as? SymingestContractError, .unsupportedSchema(1))
        }
    }

    private struct PayloadDummy: Decodable, Sendable {}
}
