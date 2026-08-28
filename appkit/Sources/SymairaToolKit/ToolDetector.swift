#if os(macOS)
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

/// Caches handshake results keyed by binary path + modification time so
/// repeated `detect` calls within the same session skip redundant subprocess
/// spawns.
private actor HandshakeCache {
    private struct Key: Hashable {
        let path: String
        let mtime: TimeInterval
    }

    private var storage: [Key: ToolVersionInfo?] = [:]

    func get(path: String, mtime: TimeInterval) -> ToolVersionInfo?? {
        storage[Key(path: path, mtime: mtime)]
    }

    func set(path: String, mtime: TimeInterval, value: ToolVersionInfo?) {
        storage[Key(path: path, mtime: mtime)] = value
    }
}

/// Detects installed Symaira tools and performs the version handshake.
public struct ToolDetector: Sendable {
    public let locator: BinaryLocator
    public let runner: CLIRunner

    /// Handshake calls are short-lived; keep the timeout tight so a hung
    /// binary cannot stall app startup (loose-coupling rule: runtime
    /// detection with a timeout and graceful fallback).
    public let handshakeTimeout: Double

    /// Maximum number of concurrent handshake spawns. Kept low so detection
    /// does not overwhelm the system on machines with many registered tools.
    public let maxConcurrentHandshakes: Int

    /// When `true`, `locate` is called with `allowUnverified: true` so
    /// binaries in non-root-owned directories and unsigned binaries are
    /// still returned. Useful for local dev builds and testing.
    public let allowUnverified: Bool

    private let handshakeCache: HandshakeCache

    public init(
        locator: BinaryLocator = BinaryLocator(),
        runner: CLIRunner = CLIRunner(),
        handshakeTimeout: Double = 5,
        maxConcurrentHandshakes: Int = 4,
        allowUnverified: Bool = false
    ) {
        self.locator = locator
        self.runner = runner
        self.handshakeTimeout = handshakeTimeout
        self.maxConcurrentHandshakes = maxConcurrentHandshakes
        self.allowUnverified = allowUnverified
        self.handshakeCache = HandshakeCache()
    }

    /// Locate a tool's binary and query its version. Returns nil when the
    /// binary is not installed. A binary that is present but fails the
    /// version query is still returned (with `versionInfo == nil`) so UIs
    /// can show a repair hint instead of "not installed".
    public func detect(_ tool: SymairaTool) async -> DetectedTool? {
        guard let location = locator.locate(tool.binaryName, allowUnverified: allowUnverified) else {
            return nil
        }
        let info = await queryVersionCached(at: location.url)
        return DetectedTool(tool: tool, location: location, versionInfo: info)
    }

    /// Detect every registry tool that is installed on this machine.
    ///
    /// Handshakes run concurrently in a bounded sliding window (default 4),
    /// admitting the next tool as soon as any in-flight handshake completes.
    /// Results are returned in the same order as the input `tools` array.
    public func detectInstalled(from tools: [SymairaTool] = SymairaToolRegistry.all) async -> [DetectedTool] {
        let concurrency = max(1, maxConcurrentHandshakes)
        var detected = Array<DetectedTool?>(repeating: nil, count: tools.count)

        await withTaskGroup(of: (Int, DetectedTool?).self) { group in
            var nextIndex = 0
            for _ in 0..<min(concurrency, tools.count) {
                let index = nextIndex
                nextIndex += 1
                group.addTask {
                    (index, await self.detect(tools[index]))
                }
            }

            while let (index, result) = await group.next() {
                detected[index] = result
                guard nextIndex < tools.count else { continue }

                let indexToStart = nextIndex
                nextIndex += 1
                group.addTask {
                    (indexToStart, await self.detect(tools[indexToStart]))
                }
            }
        }

        return detected.compactMap { $0 }
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

    private func queryVersionCached(at url: URL) async -> ToolVersionInfo? {
        let path = url.path
        let mtime: TimeInterval
        if let values = try? url.resourceValues(forKeys: [.contentModificationDateKey]),
           let date = values.contentModificationDate {
            mtime = date.timeIntervalSinceReferenceDate
        } else {
            mtime = 0
        }

        if let cached = await handshakeCache.get(path: path, mtime: mtime) {
            return cached
        }

        let info = await queryVersion(at: url)
        await handshakeCache.set(path: path, mtime: mtime, value: info)
        return info
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
#endif
