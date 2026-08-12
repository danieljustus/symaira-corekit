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
        let locator = BinaryLocator(searchPATH: "", extraDirectories: [])
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

    // MARK: - Client command construction (fake symingest binary)

    private var tempDirectories: [URL] = []

    override func tearDown() {
        for dir in tempDirectories {
            try? FileManager.default.removeItem(at: dir)
        }
        tempDirectories.removeAll()
        super.tearDown()
    }

    private static let validReOCRResponse = #"{"schema_version":1,"document_id":7,"job_id":42,"status":"completed","output_path":"/vault/note.md"}"#

    /// Creates a client whose locator resolves to a fake `symingest` shell
    /// script in a fresh temp directory. The script records its argv to
    /// `last-args` and answers with `cannedOutput` (written to a separate
    /// file so no shell quoting issues), so `reprocess` argument mapping
    /// and schema-check behavior are verified end to end through the
    /// existing `CLIRunner` seam without a real binary.
    private func makeFakeBinaryClient(
        vaultPath: String? = nil,
        configPath: String? = nil,
        cannedOutput: String = #"{"schema_version":1,"document_id":7,"job_id":42,"status":"completed","output_path":"/vault/note.md"}"#
    ) throws -> (SymingestReOCRClient, URL) {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("symingest-reocr-fake-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        tempDirectories.append(dir)

        try Data(cannedOutput.utf8).write(to: dir.appendingPathComponent("canned-response"))
        let binary = dir.appendingPathComponent("symingest")
        let script = """
        #!/bin/sh
        DIR="$(cd "$(dirname "$0")" && pwd)"
        printf '%s\\n' "$@" > "$DIR/last-args"
        cat "$DIR/canned-response"
        """
        try Data(script.utf8).write(to: binary)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: binary.path)

        let locator = BinaryLocator(searchPATH: "", extraDirectories: [dir.path])
        let client = SymingestReOCRClient(vaultPath: vaultPath, configPath: configPath, locator: locator)
        return (client, dir)
    }

    private func readLastArgs(from dir: URL) throws -> [String] {
        let text = try String(contentsOf: dir.appendingPathComponent("last-args"), encoding: .utf8)
        return text.split(separator: "\n").map(String.init)
    }

    func testReprocessByDocumentIDConstructsCommandAndDecodes() async throws {
        let (client, dir) = try makeFakeBinaryClient()
        let response = try await client.reprocess(documentID: 7)
        XCTAssertEqual(try readLastArgs(from: dir), ["reocr", "--json", "--document-id", "7"])
        XCTAssertEqual(response.schemaVersion, 1)
        XCTAssertEqual(response.documentID, 7)
        XCTAssertEqual(response.jobID, 42)
        XCTAssertEqual(response.status, "completed")
        XCTAssertEqual(response.outputPath, "/vault/note.md")
        XCTAssertNil(response.error)
    }

    func testReprocessByArchivePathConstructsPositionalCommand() async throws {
        let (client, dir) = try makeFakeBinaryClient()
        let response = try await client.reprocess(archivePath: "/archive/source.pdf")
        XCTAssertEqual(try readLastArgs(from: dir), ["reocr", "--json", "/archive/source.pdf"])
        XCTAssertEqual(response.documentID, 7)
    }

    func testReprocessIncludesVaultAndConfigFlags() async throws {
        let (client, dir) = try makeFakeBinaryClient(vaultPath: "/vault", configPath: "/tmp/config.toml")
        _ = try await client.reprocess(documentID: 7)
        XCTAssertEqual(
            try readLastArgs(from: dir),
            ["reocr", "--json", "-db", "/tmp/config.toml", "-vault", "/vault", "--document-id", "7"]
        )
        _ = try await client.reprocess(archivePath: "/archive/source.pdf")
        XCTAssertEqual(
            try readLastArgs(from: dir),
            ["reocr", "--json", "-db", "/tmp/config.toml", "-vault", "/vault", "/archive/source.pdf"]
        )
    }

    func testReprocessRejectsUnsupportedSchemaFromRunner() async throws {
        let (client, dir) = try makeFakeBinaryClient(cannedOutput: #"{"schema_version":2,"document_id":1,"job_id":1,"status":"completed","output_path":""}"#)
        do {
            _ = try await client.reprocess(documentID: 1)
            XCTFail("expected unsupported schema error")
        } catch {
            XCTAssertEqual(error as? ReOCRContractError, .unsupportedSchema(2))
        }
        XCTAssertEqual(try readLastArgs(from: dir), ["reocr", "--json", "--document-id", "1"])
    }

    func testReprocessMapsNonJSONRunnerOutputToInvalidResponse() async throws {
        let (client, dir) = try makeFakeBinaryClient(cannedOutput: "not json")
        do {
            _ = try await client.reprocess(archivePath: "/x.pdf")
            XCTFail("expected invalid response error")
        } catch {
            XCTAssertEqual(error as? ReOCRContractError, .invalidResponse)
        }
        XCTAssertEqual(try readLastArgs(from: dir), ["reocr", "--json", "/x.pdf"])
    }
}
