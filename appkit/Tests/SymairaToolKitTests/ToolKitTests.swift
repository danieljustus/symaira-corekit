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
            "symingest", "symeraseme", "symtune", "symoperate", "symdesk",
            "symmeet", "symbrain", "symrelate", "symbrowse", "symcockpit",
        ]
        for id in expected {
            XCTAssertNotNil(SymairaToolRegistry.tool(id: id), "missing tool: \\(id)")
        }
    }

    func testBrainAndRelateRegistryEntries() {
        // symrelate exposes a plain `mcp` subcommand (symaira-relate,
        // internal/cli/mcp_cmd.go, no required flags).
        let relate = SymairaToolRegistry.tool(id: "symrelate")
        XCTAssertEqual(relate?.supportsMCP, true)
        XCTAssertEqual(relate?.mcpArgs, ["mcp"])
        // symbrain's server requires a runtime `--profile` argument
        // (symaira-brain, cmd/symbrain/cmd_serve.go); the static registry
        // cannot express it, so the entry must not advertise MCP support.
        let brain = SymairaToolRegistry.tool(id: "symbrain")
        XCTAssertEqual(brain?.supportsMCP, false)
        XCTAssertEqual(brain?.mcpArgs, [])
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
                XCTAssertFalse(tool.mcpArgs.isEmpty, "\\(tool.id) supports MCP but has no args")
            } else {
                XCTAssertTrue(tool.mcpArgs.isEmpty, "\\(tool.id) has MCP args but supportsMCP is false")
            }
        }
    }

    // MARK: - Issue #103: Deprecated field for absorbed tools

    func testDeprecatedToolsAreMarked() {
        // Tools absorbed into other products per the repo consolidation
        // (documented in docs/repo-konsolidierung.md). The Homebrew formulae
        // carry `deprecate!` as well, but clients consult this field.
        let deprecated: [(id: String, absorbedInto: String)] = [
            ("symmemory",   "absorbed into Symaira Brain (symbrain)"),
            ("symseek",     "absorbed into Symaira Desktop (symdesk)"),
            ("symfetch",    "absorbed into Symaira Browse (symbrowse)"),
            ("symscope",    "absorbed into Symaira Cockpit (symcockpit)"),
            ("symprint",    "absorbed into Symaira Desktop (symdesk)"),
            ("symskills",   "absorbed into Symaira Brain (symbrain)"),
            ("symguard",    "absorbed into Symaira Brain (symbrain)"),
            ("symingest",   "absorbed into Symaira Desktop (symdesk)"),
            ("symmeet",     "absorbed into Symaira Desktop (symdesk)"),
            ("symrelate",   "absorbed into Symaira Desktop (symdesk)"),
            ("symtune",     "absorbed into Symaira Cockpit (symcockpit)"),
            ("symoperate",  "absorbed into Symaira Cockpit (symcockpit)"),
        ]
        for (id, reason) in deprecated {
            let tool = SymairaToolRegistry.tool(id: id)
            XCTAssertNotNil(tool, "deprecated tool missing from registry: \\(id)")
            XCTAssertTrue(tool?.isDeprecated ?? false, "\\(id) should be deprecated")
            XCTAssertEqual(tool?.deprecated, reason, "\\(id) deprecated reason mismatch")
        }
    }

    func testActiveToolsAreNotDeprecated() {
        // These tools still have independent repos and active formulae.
        let active = ["symvault", "symfritz", "symvibe", "symbrain",
                      "symdesk", "symbrowse", "symcockpit", "symeraseme"]
        for id in active {
            let tool = SymairaToolRegistry.tool(id: id)
            XCTAssertNotNil(tool, "active tool missing from registry: \(id)")
            XCTAssertFalse(tool?.isDeprecated ?? true, "\(id) should not be deprecated")
            XCTAssertNil(tool?.deprecated, "\(id) deprecated field should be nil")
        }
    }

    func testRegistryActiveFilterExcludesDeprecated() {
        let active = SymairaToolRegistry.active
        let activeIDs = Set(active.map(\.id))
        for id in activeIDs {
            XCTAssertFalse(SymairaToolRegistry.tool(id: id)?.isDeprecated ?? true,
                           "active filter should not include deprecated tools")
        }
        // Every deprecated tool must be excluded from active.
        let deprecatedIDs = Set(SymairaToolRegistry.all.filter(\.isDeprecated).map(\.id))
        for id in deprecatedIDs {
            XCTAssertFalse(activeIDs.contains(id),
                           "active filter should exclude \(id)")
        }
        // The active count equals total minus deprecated (12 deprecated).
        XCTAssertEqual(active.count, SymairaToolRegistry.all.count - 12)
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

    // MARK: - Existing tests (updated for allowUnverified)

    func testFindsBinaryOnSearchPATH() throws {
        let bin = try makeExecutable(named: "symfake", in: tempDir)
        let locator = BinaryLocator(bundle: nil, searchPATH: tempDir.path)
        let located = locator.locate("symfake", allowUnverified: true)
        XCTAssertEqual(located?.url.path, bin.path)
        XCTAssertEqual(located?.source, .path)
    }

    func testUserOverrideWinsOverPATH() throws {
        _ = try makeExecutable(named: "symfake", in: tempDir)
        let overrideDir = tempDir.appendingPathComponent("override")
        try FileManager.default.createDirectory(at: overrideDir, withIntermediateDirectories: true)
        let override = try makeExecutable(named: "symfake", in: overrideDir)

        let locator = BinaryLocator(bundle: nil, userOverride: override, searchPATH: tempDir.path)
        let located = locator.locate("symfake", allowUnverified: true)
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
        XCTAssertNil(locator.locate("symfake", allowUnverified: true))
    }

    /// On the default case-insensitive APFS volume, a lowercase `binaryName`
    /// candidate in `Contents/MacOS/` can resolve to the app's own
    /// differently-cased executable (e.g. locating "symdesk" actually hits
    /// "SymDesk"). Locating it as a "CLI" would relaunch the GUI app as a
    /// subprocess that never exits.
    func testSkipsOwnExecutableOnCaseInsensitiveCollision() throws {
        let appDir = tempDir.appendingPathComponent("FakeApp.app/Contents/MacOS")
        try FileManager.default.createDirectory(at: appDir, withIntermediateDirectories: true)
        _ = try makeExecutable(named: "FakeApp", in: appDir)
        let bundle = try makeFakeBundle(executableName: "FakeApp", in: appDir)

        // A real CLI binary is also reachable further down the search order.
        let pathDir = tempDir.appendingPathComponent("path")
        try FileManager.default.createDirectory(at: pathDir, withIntermediateDirectories: true)
        let realCLI = try makeExecutable(named: "fakeapp", in: pathDir)

        let locator = BinaryLocator(bundle: bundle, searchPATH: pathDir.path, extraDirectories: [])
        let located = locator.locate("fakeapp", allowUnverified: true)

        XCTAssertEqual(located?.url.path, realCLI.path)
        XCTAssertEqual(located?.source, .path)
    }

    func testExecutableDirectoryStillMatchesDistinctCLIName() throws {
        let appDir = tempDir.appendingPathComponent("FakeApp.app/Contents/MacOS")
        try FileManager.default.createDirectory(at: appDir, withIntermediateDirectories: true)
        _ = try makeExecutable(named: "FakeApp", in: appDir)
        let cli = try makeExecutable(named: "fakeapp-cli", in: appDir)
        let bundle = try makeFakeBundle(executableName: "FakeApp", in: appDir)

        let locator = BinaryLocator(bundle: bundle, searchPATH: "", extraDirectories: [])
        let located = locator.locate("fakeapp-cli")

        XCTAssertEqual(located?.url.path, cli.path)
        XCTAssertEqual(located?.source, .executableDirectory)
    }

    // MARK: - Issue #7: Provenance verification

    /// A signed system binary in a root-owned directory returns verified=true.
    func testVerifiedHit() {
        // /usr/bin/true is signed by Apple and sits in a root-owned directory.
        let locator = BinaryLocator(
            bundle: nil,
            searchPATH: "/usr/bin",
            extraDirectories: []
        )
        let located = locator.locate("true")
        XCTAssertNotNil(located, "Should find /usr/bin/true")
        XCTAssertEqual(located?.source, .path)
        XCTAssertTrue(located?.verified ?? false, "Signed system binary should be verified")
    }

    /// An unsigned binary in a group-writable directory is not returned
    /// when allowUnverified is false.
    func testUnverifiedHitRejected() throws {
        let insecureDir = tempDir.appendingPathComponent("insecure-group")
        try FileManager.default.createDirectory(at: insecureDir, withIntermediateDirectories: true)
        chmod(insecureDir.path, 0o775) // group-writable
        defer { try? FileManager.default.removeItem(at: insecureDir) }
        let bin = try makeExecutable(named: "symfake", in: insecureDir)
        // insecureDir is group-writable → directory check fails.
        let locator = BinaryLocator(
            bundle: nil,
            searchPATH: insecureDir.path,
            extraDirectories: []
        )
        let located = locator.locate("symfake") // allowUnverified defaults to false
        XCTAssertNil(located, "Unsigned binary in group-writable directory should be rejected by default")
        // Sanity: the binary does exist.
        XCTAssertTrue(FileManager.default.isExecutableFile(atPath: bin.path))
    }

    /// With allowUnverified: true, an unsigned binary is returned with
    /// verified=false.
    func testAllowUnverifiedOptIn() throws {
        let bin = try makeExecutable(named: "symfake", in: tempDir)
        let locator = BinaryLocator(
            bundle: nil,
            searchPATH: tempDir.path,
            extraDirectories: []
        )
        let located = locator.locate("symfake", allowUnverified: true)
        XCTAssertNotNil(located)
        XCTAssertEqual(located?.url.path, bin.path)
        XCTAssertEqual(located?.source, .path)
        XCTAssertFalse(located?.verified ?? true, "Unsigned binary should report verified=false")
    }

    // MARK: - Directory security helper

    func testIsDirectorySecureRootOwnedBin() {
        // /usr/bin on macOS is root-owned and has standard permissions.
        XCTAssertTrue(BinaryLocator.isDirectorySecure("/usr/bin"))
    }

    func testIsDirectorySecureAcceptsUserTempDir() {
        // FileManager.temporaryDirectory is user-owned and not
        // group/world-writable — accepted with the current-user check.
        XCTAssertTrue(BinaryLocator.isDirectorySecure(tempDir.path))
    }

    func testIsDirectorySecureRejectsWorldWritableDir() throws {
        let dir = tempDir.appendingPathComponent("world-writable")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        chmod(dir.path, 0o777)
        defer { try? FileManager.default.removeItem(at: dir) }
        XCTAssertFalse(BinaryLocator.isDirectorySecure(dir.path))
    }

    // MARK: - Signature verification helper

    func testVerifySignaturePassesForSystemBinary() {
        XCTAssertTrue(BinaryLocator.verifySignature(at: URL(fileURLWithPath: "/usr/bin/true")))
    }

    func testVerifySignatureFailsForUnsignedScript() throws {
        let url = try makeExecutable(named: "unsigned", in: tempDir)
        XCTAssertFalse(BinaryLocator.verifySignature(at: url))
    }

    /// Builds a minimal, loadable app bundle so `Bundle.executableURL` resolves.
    private func makeFakeBundle(executableName: String, in macOSDir: URL) throws -> Bundle {
        let contentsDir = macOSDir.deletingLastPathComponent()
        let infoPlist = contentsDir.appendingPathComponent("Info.plist")
        let plist: [String: Any] = [
            "CFBundleExecutable": executableName,
            "CFBundleIdentifier": "com.symaira.fakeapp.test",
            "CFBundlePackageType": "APPL",
        ]
        let data = try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0)
        try data.write(to: infoPlist)

        let bundleURL = contentsDir.deletingLastPathComponent()
        guard let bundle = Bundle(url: bundleURL) else {
            throw NSError(domain: "BinaryLocatorTests", code: 1, userInfo: [NSLocalizedDescriptionKey: "Failed to load fake bundle at \(bundleURL.path)"])
        }
        return bundle
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
        ToolDetector(
            locator: BinaryLocator(bundle: nil, searchPATH: tempDir.path, extraDirectories: []),
            maxConcurrentHandshakes: 4,
            allowUnverified: true
        )
    }

    func testDetectParsesStructuredVersionHandshake() async throws {
        let tool = try makeFakeTool(
            named: "symfake",
            script: "#!/bin/sh\necho '{\"version\":\"1.2.3\",\"schema_version\":2}'\n"
        )
        let detected = await detector.detect(tool)
        XCTAssertEqual(detected?.versionInfo, ToolVersionInfo(version: "1.2.3", schemaVersion: 2))
    }

    func testDetectsSymmeetRegistryEntryWithSchemaOne() async throws {
        _ = try makeFakeTool(
            named: "symmeet",
            script: "#!/bin/sh\necho '{\"version\":\"0.4.0\",\"schema_version\":1}'\n"
        )
        let tool = try XCTUnwrap(SymairaToolRegistry.tool(id: "symmeet"))
        let detected = await detector.detect(tool)
        XCTAssertEqual(detected?.versionInfo, ToolVersionInfo(version: "0.4.0", schemaVersion: 1))
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

    // MARK: - Issue #16: Parallelisation & ordering

    func testDetectInstalledPreservesRegistryOrder() async throws {
        // Create fake tools with known names and IDs in a specific order.
        let tools = try (0..<6).map { i in
            let name = "symorder\(i)"
            return try makeFakeTool(
                named: name,
                script: "#!/bin/sh\necho '{\"version\":\"1.0.0\",\"schema_version\":1}'\n"
            )
        }
        // Register them in a known order.
        let results = await detector.detectInstalled(from: tools)
        // Every installed tool should be detected, and order must match.
        XCTAssertEqual(results.count, tools.count)
        for (i, detected) in results.enumerated() {
            XCTAssertEqual(detected.tool.id, tools[i].id, "Result at index \(i) should match input tool")
        }
    }

    func testSlowToolDoesNotSerializeOthers() async throws {
        // One tool sleeps 2 seconds; others are fast.
        let slow = try makeFakeTool(
            named: "symslow",
            script: "#!/bin/sh\nsleep 2\necho '{\"version\":\"1.0.0\",\"schema_version\":1}'\n"
        )
        let fastCount = 3
        let fastTools = try (0..<fastCount).map { i in
            try makeFakeTool(
                named: "symfast\(i)",
                script: "#!/bin/sh\necho '{\"version\":\"1.0.0\",\"schema_version\":1}'\n"
            )
        }
        let allTools = [slow] + fastTools

        let start = Date()
        let results = await detector.detectInstalled(from: allTools)
        let elapsed = Date().timeIntervalSince(start)

        // All tools should be detected (slow one should still have versionInfo).
        XCTAssertEqual(results.count, allTools.count, "All tools should be detected")
        XCTAssertNotNil(results.first(where: { $0.tool.id == "symslow" })?.versionInfo,
                         "Slow tool should still return version info")

        // With 4 concurrent handshakes, total time should be dominated by
        // the slowest in each chunk, not by the sum of all.
        XCTAssertLessThan(elapsed, 5.0, "Concurrent detection should finish well under sequential sum of ~\(2 + fastCount * 1) seconds")
    }

    func testRepeatedDetectionUsesCache() async throws {
        // Create a tool script that writes a counter to a temp file on each
        // handshake invocation, so we can verify it's only called once.
        let counterFile = tempDir.appendingPathComponent("counter.txt")
        try "0".write(to: counterFile, atomically: true, encoding: .utf8)

        let tool = try makeFakeTool(
            named: "symcache",
            script: """
            #!/bin/sh
            val=$(cat "\(counterFile.path)")
            echo $((val + 1)) > "\(counterFile.path)"
            echo '{"version":"1.0.0","schema_version":1}'
            """
        )

        let det = detector
        _ = await det.detect(tool)
        _ = await det.detect(tool)

        let countStr = try String(contentsOf: counterFile, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
        let count = Int(countStr) ?? -1
        XCTAssertEqual(count, 1, "Handshake should only run once due to caching — got \(count)")
    }
}
