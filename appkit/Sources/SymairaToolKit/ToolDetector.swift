import Foundation
import SymairaCLIRunner

/// Version information reported by a core via `version --json`.
///
/// Cores without the JSON version subcommand (older installs, or before the
/// corekit `versionkit` helper lands) are reported with `schemaVersion == 0`:
/// usable, but without contract guarantees.
public struct ToolVersionInfo: Sendable, Equatable {
    public let version: String
    public let schemaVersion: Int

    public init(version: String, schemaVersion: Int) {
        self.version = version
        self.schemaVersion = schemaVersion
    }
}

/// A tool that was found on this machine, with its resolved binary and
/// (best-effort) version handshake result.
public struct DetectedTool: Sendable {
    public let tool: SymairaTool
    public let location: BinaryLocator.Located
    public let versionInfo: ToolVersionInfo?

    public var isUsable: Bool { versionInfo != nil }
}

/// Detects installed Symaira tools and performs the version handshake.
public struct ToolDetector: Sendable {
    public let locator: BinaryLocator
    public let runner: CLIRunner

    /// Handshake calls are short-lived; keep the timeout tight so a hung
    /// binary cannot stall app startup (loose-coupling rule: runtime
    /// detection with a timeout and graceful fallback).
    public let handshakeTimeout: Double

    public init(
        locator: BinaryLocator = BinaryLocator(),
        runner: CLIRunner = CLIRunner(),
        handshakeTimeout: Double = 5
    ) {
        self.locator = locator
        self.runner = runner
        self.handshakeTimeout = handshakeTimeout
    }

    /// Locate a tool's binary and query its version. Returns nil when the
    /// binary is not installed. A binary that is present but fails the
    /// version query is still returned (with `versionInfo == nil`) so UIs
    /// can show a repair hint instead of "not installed".
    public func detect(_ tool: SymairaTool) async -> DetectedTool? {
        guard let location = locator.locate(tool.binaryName) else {
            return nil
        }
        let info = await queryVersion(at: location.url)
        return DetectedTool(tool: tool, location: location, versionInfo: info)
    }

    /// Detect every registry tool that is installed on this machine.
    public func detectInstalled(from tools: [SymairaTool] = SymairaToolRegistry.all) async -> [DetectedTool] {
        var detected: [DetectedTool] = []
        for tool in tools {
            if let hit = await detect(tool) {
                detected.append(hit)
            }
        }
        return detected
    }

    /// Verify a detected tool satisfies the schema version this app expects.
    public func requireSchemaVersion(_ expected: Int, of detected: DetectedTool) throws {
        let actual = detected.versionInfo?.schemaVersion ?? 0
        guard actual == 0 || actual == expected else {
            throw CLIRunnerError.schemaMismatch(expected: expected, actual: actual)
        }
    }

    // MARK: - Handshake

    private struct VersionJSON: Decodable {
        let version: String
        let schemaVersion: Int?
    }

    private func queryVersion(at url: URL) async -> ToolVersionInfo? {
        // Preferred: structured handshake.
        if let json = try? await runner.runDecoding(
            VersionJSON.self,
            executable: url,
            arguments: ["version", "--json"],
            timeout: handshakeTimeout
        ) {
            return ToolVersionInfo(version: json.version, schemaVersion: json.schemaVersion ?? 0)
        }

        // Fallbacks for cores without `version --json`.
        for args in [["version"], ["--version"]] {
            if let result = try? await runner.run(url, arguments: args, timeout: handshakeTimeout),
               result.exitCode == 0,
               let version = Self.extractVersionToken(from: result.stdoutText) {
                return ToolVersionInfo(version: version, schemaVersion: 0)
            }
        }
        return nil
    }

    /// Pull the first semver-looking token out of free-form version output
    /// (e.g. "symscope version v0.3.1 (darwin/arm64)" → "v0.3.1").
    static func extractVersionToken(from text: String) -> String? {
        for token in text.split(whereSeparator: { $0 == " " || $0 == "\n" }) {
            let trimmed = token.hasPrefix("v") ? token.dropFirst() : token[...]
            let parts = trimmed.split(separator: ".")
            if parts.count >= 2, parts.allSatisfy({ $0.allSatisfy(\.isNumber) || $0.contains("-") }) {
                return String(token)
            }
        }
        return nil
    }
}
