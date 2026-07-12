import XCTest
import Foundation
@testable import SymairaIngestContract
import SymairaToolKit

final class SymingestReOCRContractTests: XCTestCase {
    func testCompletedResponseDecodes() throws {
        let response = try ReOCRContract.decode(from: Data("""
        {"schema_version":1,"document_id":7,"job_id":42,"status":"completed","output_path":"/vault/note.md"}
        """.utf8))
        XCTAssertEqual(response.schemaVersion, 1)
        XCTAssertEqual(response.documentID, 7)
        XCTAssertEqual(response.jobID, 42)
        XCTAssertEqual(response.status, "completed")
        XCTAssertEqual(response.outputPath, "/vault/note.md")
        XCTAssertNil(response.error)
    }

    func testFailedResponseDecodesWithError() throws {
        let response = try ReOCRContract.decode(from: Data("""
        {"schema_version":1,"document_id":7,"job_id":0,"status":"failed","output_path":"","error":{"code":"source_missing","message":"archived source is unavailable"}}
        """.utf8))
        XCTAssertEqual(response.status, "failed")
        XCTAssertEqual(response.error, ReOCRError(code: "source_missing", message: "archived source is unavailable"))
    }

    func testSchemaVersionCheckRejectsUnknownVersion() {
        XCTAssertThrowsError(try ReOCRContract.decodeWithSchemaCheck(from: Data("{\"schema_version\":2,\"document_id\":1,\"job_id\":1,\"status\":\"completed\",\"output_path\":\"\"}".utf8))) { error in
            XCTAssertEqual(error as? ReOCRContractError, .unsupportedSchema(2))
        }
    }

    func testInvalidResponseFailsClearly() {
        XCTAssertThrowsError(try ReOCRContract.decode(from: Data("not json".utf8))) { error in
            XCTAssertEqual(error as? ReOCRContractError, .invalidResponse)
        }
    }

    func testMissingBinaryFailsClearly() async {
        let locator = BinaryLocator(searchPATH: "")
        let client = SymingestReOCRClient(locator: locator)
        do {
            _ = try await client.reprocess(documentID: 1)
            XCTFail("expected missing binary error")
        } catch {
            XCTAssertEqual(error as? ReOCRContractError, .missingBinary)
        }
    }

    func testRequestDiscriminatesInputs() {
        let byID = ReOCRRequest.documentID(7)
        let byPath = ReOCRRequest.archivePath("/archive/source.pdf")
        XCTAssertEqual(byID.documentID, 7)
        XCTAssertNil(byID.archivePath)
        XCTAssertNil(byPath.documentID)
        XCTAssertEqual(byPath.archivePath, "/archive/source.pdf")
    }
}
