import XCTest
@testable import SymairaToolKit

final class RegistryTests: XCTestCase {
    func testRegistryHasNoGhostTools() {
        // symcanvas was listed in the old StackKit registry but never existed.
        XCTAssertNil(SymairaToolRegistry.tool(id: "symcanvas"))
    }

    func testRegistryContainsAllKnownTools() {
        let expected = [
            "symvault", "symmemory", "symseek", "symfetch", "symscope",
            "symfritz", "symprint", "symskills", "symvibe", "symguard",
            "symingest", "symeraseme", "symtune", "symoperate",
        ]
        for id in expected {
            XCTAssertNotNil(SymairaToolRegistry.tool(id: id), "missing tool: \(id)")
        }
    }

    func testRegistryIDsAreUniqueAndSymPrefixed() {
        let ids = SymairaToolRegistry.all.map(\.id)
        XCTAssertEqual(ids.count, Set(ids).count)
        for tool in SymairaToolRegistry.all {
            XCTAssertTrue(tool.binaryName.hasPrefix("sym"), tool.binaryName)
            XCTAssertTrue(tool.homebrewFormula.hasPrefix("danieljustus/tap/"), tool.homebrewFormula)
        }
    }

    func testMCPToolsDeclareArgs() {
        for tool in SymairaToolRegistry.all {
            if tool.supportsMCP {
                XCTAssertFalse(tool.mcpArgs.isEmpty, "\(tool.id) supports MCP but has no args")
            } else {
                XCTAssertTrue(tool.mcpArgs.isEmpty, "\(tool.id) has MCP args but supportsMCP is false")
            }
        }
    }
}

final class BinaryLocatorTests: XCTestCase {
    private var tempDir: URL!

    override func setUpWithError() throws {
        tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("appkit-locator-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: tempDir)
    }

    private func makeExecutable(named name: String, in dir: URL) throws -> URL {
        let url = dir.appendingPathComponent(name)
        try "#!/bin/sh\nexit 0\n".write(to: url, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: url.path)
        return url
    }

    func testFindsBinaryOnSearchPATH() throws {
        let bin = try makeExecutable(named: "symfake", in: tempDir)
        let locator = BinaryLocator(bundle: nil, searchPATH: tempDir.path)
        let located = locator.locate("symfake")
        XCTAssertEqual(located?.url.path, bin.path)
        XCTAssertEqual(located?.source, .path)
    }

    func testUserOverrideWinsOverPATH() throws {
        _ = try makeExecutable(named: "symfake", in: tempDir)
        let overrideDir = tempDir.appendingPathComponent("override")
        try FileManager.default.createDirectory(at: overrideDir, withIntermediateDirectories: true)
        let override = try makeExecutable(named: "symfake", in: overrideDir)

        let locator = BinaryLocator(bundle: nil, userOverride: override, searchPATH: tempDir.path)
        let located = locator.locate("symfake")
        XCTAssertEqual(located?.url.path, override.path)
        XCTAssertEqual(located?.source, .userOverride)
    }

    func testReturnsNilWhenNotInstalled() {
        let locator = BinaryLocator(bundle: nil, searchPATH: tempDir.path, extraDirectories: [])
        XCTAssertNil(locator.locate("symdoesnotexist"))
    }

    func testNonExecutableFileIsSkipped() throws {
        let url = tempDir.appendingPathComponent("symfake")
        try "not executable".write(to: url, atomically: true, encoding: .utf8)
        let locator = BinaryLocator(bundle: nil, searchPATH: tempDir.path, extraDirectories: [])
        XCTAssertNil(locator.locate("symfake"))
    }
}

final class ToolDetectorTests: XCTestCase {
    private var tempDir: URL!

    override func setUpWithError() throws {
        tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("appkit-detector-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: tempDir)
    }

    private func makeFakeTool(named name: String, script: String) throws -> SymairaTool {
        let url = tempDir.appendingPathComponent(name)
        try script.write(to: url, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: url.path)
        return SymairaTool(id: name, displayName: name, binaryName: name, homebrewFormula: "danieljustus/tap/\(name)")
    }

    private var detector: ToolDetector {
        ToolDetector(locator: BinaryLocator(bundle: nil, searchPATH: tempDir.path, extraDirectories: []))
    }

    func testDetectParsesStructuredVersionHandshake() async throws {
        let tool = try makeFakeTool(
            named: "symfake",
            script: "#!/bin/sh\necho '{\"version\":\"1.2.3\",\"schema_version\":2}'\n"
        )
        let detected = await detector.detect(tool)
        XCTAssertEqual(detected?.versionInfo, ToolVersionInfo(version: "1.2.3", schemaVersion: 2))
    }

    func testDetectFallsBackToPlainVersionOutput() async throws {
        let tool = try makeFakeTool(
            named: "symplain",
            script: "#!/bin/sh\nif [ \"$2\" = \"--json\" ]; then exit 2; fi\necho 'symplain version v0.4.1 (darwin/arm64)'\n"
        )
        let detected = await detector.detect(tool)
        XCTAssertEqual(detected?.versionInfo, ToolVersionInfo(version: "v0.4.1", schemaVersion: 0))
    }

    func testDetectReturnsNilForMissingBinary() async {
        let tool = SymairaTool(id: "symmissing", displayName: "x", binaryName: "symmissing", homebrewFormula: "x")
        let detected = await detector.detect(tool)
        XCTAssertNil(detected)
    }

    func testSchemaMismatchThrows() async throws {
        let tool = try makeFakeTool(
            named: "symfake",
            script: "#!/bin/sh\necho '{\"version\":\"1.2.3\",\"schema_version\":2}'\n"
        )
        let maybeDetected = await detector.detect(tool)
        let detected = try XCTUnwrap(maybeDetected)
        XCTAssertNoThrow(try detector.requireSchemaVersion(2, of: detected))
        XCTAssertThrowsError(try detector.requireSchemaVersion(3, of: detected))
    }

    func testVersionTokenExtraction() {
        XCTAssertEqual(ToolDetector.extractVersionToken(from: "symseek version v0.3.1 (darwin)"), "v0.3.1")
        XCTAssertEqual(ToolDetector.extractVersionToken(from: "1.0.0"), "1.0.0")
        XCTAssertNil(ToolDetector.extractVersionToken(from: "no version here"))
    }
}
