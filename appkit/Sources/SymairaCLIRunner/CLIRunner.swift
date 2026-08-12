#if os(macOS)
import Foundation

/// Result of a completed CLI invocation.
public struct CLIResult: Sendable {
    public let stdout: Data
    public let stderr: Data
    public let exitCode: Int32
    /// `true` when either stdout or stderr exceeded `maxOutputBytes` and the
    /// process was terminated before reading all output.
    public let isTruncated: Bool

    public init(stdout: Data, stderr: Data, exitCode: Int32, isTruncated: Bool = false) {
        self.stdout = stdout
        self.stderr = stderr
        self.exitCode = exitCode
        self.isTruncated = isTruncated
    }

    public var stdoutText: String {
        String(data: stdout, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    public var stderrText: String {
        String(data: stderr, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }
}

/// Unified error type for CLI execution, mapped to the Symaira exit-code
/// convention (0 ok, 1 runtime, 2 usage/config, 3 auth/permission, 4 unsupported).
public enum CLIRunnerError: Error, LocalizedError, Sendable {
    case binaryNotFound(tool: String)
    /// The full, raw stderr string is stored as an associated value so it
    /// is always reachable for diagnostics, but it is intentionally **not**
    /// interpolated into the user-facing `errorDescription`.
    case executionFailed(code: Int32, fullStderr: String)
    case timeout(seconds: Double)
    case invalidJSON(description: String)
    case schemaMismatch(expected: Int, actual: Int)
    /// Thrown when subprocess output exceeds `maxOutputBytes` and was truncated.
    case outputTruncated(size: Int)

    // MARK: - Non‑LocalizedError diagnostic accessors

    /// The full, raw stderr produced by the subprocess.  Never redacted,
    /// never bounded — use this for logging / diagnostics, not for UI.
    public var fullStderr: String? {
        guard case .executionFailed(_, let s) = self else { return nil }
        return s
    }

    /// The output-size limit that was exceeded (only meaningful for
    /// `outputTruncated`).
    public var truncatedSize: Int? {
        guard case .outputTruncated(let size) = self else { return nil }
        return size
    }

    // MARK: - LocalizedError

    /// User-facing description: exit code + a bounded, redacted first line
    /// of stderr.  The description **never** exceeds ~200 bytes and
    /// obvious secret shapes are replaced with `[REDACTED]`.
    public var errorDescription: String? {
        switch self {
        case .binaryNotFound(let tool):
            return "The \(tool) binary could not be found (bundle, PATH, or Homebrew paths)."
        case .executionFailed(let code, let fullStderr):
            let bounded = CLIRunnerError.redactedForUser(fullStderr, maxBytes: 200)
            return "CLI execution failed with exit code \(code): \(bounded)"
        case .timeout(let seconds):
            return "CLI execution timed out after \(seconds) seconds."
        case .invalidJSON(let description):
            return "Failed to parse CLI JSON output: \(description)"
        case .schemaMismatch(let expected, let actual):
            return "CLI schema version \(actual) does not match expected \(expected). Try `brew upgrade`."
        case .outputTruncated(let size):
            return "Subprocess output exceeded \(size) bytes and was truncated."
        }
    }

    // MARK: - Redaction

    /// Returns a redacted, length‑bounded version of the raw text suitable
    /// for a user‑facing error message.
    ///
    /// - The result is truncated to `maxBytes` bytes (not characters).
    /// - Only the **first line** (up to the first newline) is kept.
    /// - Obvious secret shapes (PEM blocks, long base64‑like tokens,
    ///   hex‑heavy strings, and key‑name‑prefixed values) are replaced
    ///   with `[REDACTED]`.
    public static func redactedForUser(_ raw: String, maxBytes: Int = 200) -> String {
        var redacted = raw

        // 1. Redact PEM blocks (multiline — must happen before we split to
        //    first line, otherwise BEGIN/END markers span lines).
        let pemPattern = #"-----BEGIN [A-Z ]+-----[A-Za-z0-9+/=.\s]+?-----END [A-Z ]+-----"#
        if let regex = try? NSRegularExpression(pattern: pemPattern, options: [.dotMatchesLineSeparators]) {
            redacted = regex.stringByReplacingMatches(
                in: redacted,
                range: NSRange(redacted.startIndex..., in: redacted),
                withTemplate: "[REDACTED]"
            )
        }

        // 2. Take only the first line for the user‑facing message.
        let firstLine = redacted.split(separator: "\n", omittingEmptySubsequences: false).first.map(String.init) ?? redacted
        redacted = firstLine

        // 3. Long base64‑like tokens (40+ chars of base64 alphabet).
        let b64Pattern = #"[A-Za-z0-9+/=]{40,}"#
        if let regex = try? NSRegularExpression(pattern: b64Pattern, options: []) {
            redacted = regex.stringByReplacingMatches(
                in: redacted,
                range: NSRange(redacted.startIndex..., in: redacted),
                withTemplate: "[REDACTED]"
            )
        }

        // Provider‑prefixed tokens whose structural separators (underscores,
        // dots, dashes) defeat the length‑based patterns in this function:
        // GitHub PATs, Slack tokens, Stripe live keys, AWS access key IDs and JWTs.
        let providerPatterns = [
            #"gh[pousr]_[A-Za-z0-9]{20,}"#,                         // GitHub PAT / OAuth / user-to-server / server-to-server / refresh
            #"github_pat_[A-Za-z0-9_]{20,}"#,                       // fine‑grained GitHub PAT
            #"xox[baprs]-[A-Za-z0-9-]{10,}"#,                       // Slack
            #"sk_live_[A-Za-z0-9]{10,}"#,                           // Stripe live secret key
            #"(?:AKIA|ASIA)[0-9A-Z]{16}"#,                          // AWS access key id
            #"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"#,  // JWT (header.payload.signature)
        ]
        for pattern in providerPatterns {
            if let regex = try? NSRegularExpression(pattern: pattern, options: []) {
                redacted = regex.stringByReplacingMatches(
                    in: redacted,
                    range: NSRange(redacted.startIndex..., in: redacted),
                    withTemplate: "[REDACTED]"
                )
            }
        }

        // Long hex strings (32+ hex chars).
        let hexPattern = #"\b[0-9a-fA-F]{32,}\b"#
        if let regex = try? NSRegularExpression(pattern: hexPattern, options: []) {
            redacted = regex.stringByReplacingMatches(
                in: redacted,
                range: NSRange(redacted.startIndex..., in: redacted),
                withTemplate: "[REDACTED]"
            )
        }

        // Key‑prefixed secrets: patterns like KEY=... or token: ... or
        // secret=... where the value part is long and opaque.
        let keyValuePattern = #"(?:api[_-]?key|apikey|secret|token|password|passwd|credential|auth)\s*[=:]\s*\S{8,}"#
        if let regex = try? NSRegularExpression(pattern: keyValuePattern, options: [.caseInsensitive]) {
            redacted = regex.stringByReplacingMatches(
                in: redacted,
                range: NSRange(redacted.startIndex..., in: redacted),
                withTemplate: "[REDACTED]"
            )
        }

        // Truncate to maxBytes (UTF‑8).  Walk character by character
        // so we never split a multi-byte codepoint.
        var byteCount = 0
        var result = ""
        for ch in redacted {
            let chBytes = String(ch).utf8.count
            if byteCount + chBytes > maxBytes { break }
            result.append(ch)
            byteCount += chBytes
        }
        if byteCount < redacted.utf8.count {
            result += "…"
        }
        return result
    }
}

/// Non-Sendable Foundation types confined behind an @unchecked Sendable box
/// so they can be reached from the cancellation handler.
private final class ProcessBox: @unchecked Sendable {
    let process = Process()

    func terminateIfRunning() {
        if process.isRunning {
            process.terminate()
        }
    }
}

/// Executes Symaira CLI binaries as subprocesses with a mandatory timeout,
/// stderr capture, and snake_case JSON decoding.
///
/// Consolidates the former per-app runners (scope `CLIClient`, print
/// `CliManager`, skills `CLICommandRunner`, seek `EngineManager`).
public struct CLIRunner: Sendable {
    /// PATH entries prepended so GUI apps (which do not inherit a shell PATH)
    /// find Homebrew-installed binaries and helpers like docker.
    public static let augmentedPATHPrefix = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

    /// Returns `base` with the augmented `PATH` prefix merged in.
    /// If `base` already contains a `PATH` key the prefix is prepended;
    /// otherwise the prefix is used as the sole `PATH` value.
    public static func augmentedEnvironment(_ base: [String: String]) -> [String: String] {
        var env = base
        env["PATH"] = env["PATH"].map { "\(augmentedPATHPrefix):\($0)" } ?? augmentedPATHPrefix
        return env
    }

    /// Default per-stream byte limit for subprocess output (16 MiB).
    /// When either stdout or stderr exceeds this limit the process is
    /// terminated and the returned `CLIResult.isTruncated` is `true`.
    public static let defaultMaxOutputBytes = 16 * 1024 * 1024

    public let defaultTimeout: Double

    public init(defaultTimeout: Double = 30) {
        self.defaultTimeout = defaultTimeout
    }

    // MARK: - Public API

    /// Run an executable and return stdout/stderr/exit code. Does NOT throw on
    /// non-zero exit codes — use `runChecked`/`runDecoding` for that.
    ///
    /// `environment` entries are merged over the inherited (PATH-augmented)
    /// environment — for tool config like `SYMINGEST_VAULT`.
    ///
    /// - Parameter maxOutputBytes: Per-stream byte limit for stdout and
    ///   stderr.  When exceeded the child is terminated and
    ///   `CLIResult.isTruncated` is set.  Defaults to
    ///   `CLIRunner.defaultMaxOutputBytes` (16 MiB).
    public func run(
        _ executable: URL,
        arguments: [String] = [],
        stdin: Data? = nil,
        timeout: Double? = nil,
        environment: [String: String] = [:],
        maxOutputBytes: Int = defaultMaxOutputBytes
    ) async throws -> CLIResult {
        let seconds = timeout ?? defaultTimeout
        return try await withThrowingTaskGroup(of: CLIResult?.self) { group in
            group.addTask {
                try await Self.execute(
                    executable: executable,
                    arguments: arguments,
                    stdin: stdin,
                    environment: environment,
                    maxOutputBytes: maxOutputBytes
                )
            }
            group.addTask {
                try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
                return nil
            }
            defer { group.cancelAll() }
            guard let first = try await group.next(), let result = first else {
                throw CLIRunnerError.timeout(seconds: seconds)
            }
            return result
        }
    }

    /// Run and return the full result regardless of exit code. Use this when
    /// stdout is meaningful even on a non-zero exit (e.g. a health-check
    /// command that exits 1 on warnings but still writes a complete report).
    public func runAllowingFailure(
        _ executable: URL,
        arguments: [String] = [],
        stdin: Data? = nil,
        timeout: Double? = nil,
        environment: [String: String] = [:],
        maxOutputBytes: Int = defaultMaxOutputBytes
    ) async throws -> CLIResult {
        try await run(
            executable,
            arguments: arguments,
            stdin: stdin,
            timeout: timeout,
            environment: environment,
            maxOutputBytes: maxOutputBytes
        )
    }

    /// Run and throw `executionFailed` on non-zero exit, returning stdout.
    /// Also throws `outputTruncated` when the per-stream `maxOutputBytes`
    /// limit is exceeded.
    @discardableResult
    public func runChecked(
        _ executable: URL,
        arguments: [String] = [],
        stdin: Data? = nil,
        timeout: Double? = nil,
        environment: [String: String] = [:],
        maxOutputBytes: Int = defaultMaxOutputBytes
    ) async throws -> Data {
        let result = try await run(
            executable,
            arguments: arguments,
            stdin: stdin,
            timeout: timeout,
            environment: environment,
            maxOutputBytes: maxOutputBytes
        )
        guard !result.isTruncated else {
            throw CLIRunnerError.outputTruncated(size: maxOutputBytes)
        }
        guard result.exitCode == 0 else {
            throw CLIRunnerError.executionFailed(code: result.exitCode, fullStderr: result.stderrText)
        }
        return result.stdout
    }

    /// Run, check the exit code and output limit, and decode stdout as
    /// snake_case JSON.  Truncated output is surfaced as `outputTruncated`
    /// rather than a confusing parse failure.
    public func runDecoding<T: Decodable>(
        _ type: T.Type,
        executable: URL,
        arguments: [String] = [],
        stdin: Data? = nil,
        timeout: Double? = nil,
        environment: [String: String] = [:],
        maxOutputBytes: Int = defaultMaxOutputBytes
    ) async throws -> T {
        let result = try await run(
            executable,
            arguments: arguments,
            stdin: stdin,
            timeout: timeout,
            environment: environment,
            maxOutputBytes: maxOutputBytes
        )
        guard !result.isTruncated else {
            throw CLIRunnerError.outputTruncated(size: maxOutputBytes)
        }
        guard result.exitCode == 0 else {
            throw CLIRunnerError.executionFailed(code: result.exitCode, fullStderr: result.stderrText)
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        do {
            return try decoder.decode(T.self, from: result.stdout)
        } catch {
            throw CLIRunnerError.invalidJSON(description: String(describing: error))
        }
    }

    // MARK: - Subprocess plumbing

    private static func execute(
        executable: URL,
        arguments: [String],
        stdin: Data?,
        environment: [String: String],
        maxOutputBytes: Int
    ) async throws -> CLIResult {
        let box = ProcessBox()
        box.process.executableURL = executable
        box.process.arguments = arguments

        var env = CLIRunner.augmentedEnvironment(ProcessInfo.processInfo.environment)
        environment.forEach { env[$0.key] = $0.value }
        box.process.environment = env

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        box.process.standardOutput = stdoutPipe
        box.process.standardError = stderrPipe

        let stdinPipe: Pipe? = stdin != nil ? Pipe() : nil
        if let stdinPipe {
            box.process.standardInput = stdinPipe
        }

        return try await withTaskCancellationHandler {
            let (exitStream, exitContinuation) = AsyncStream.makeStream(of: Int32.self)
            box.process.terminationHandler = { proc in
                exitContinuation.yield(proc.terminationStatus)
                exitContinuation.finish()
            }

            try box.process.run()

            if let stdin, let stdinPipe {
                stdinPipe.fileHandleForWriting.write(stdin)
                try? stdinPipe.fileHandleForWriting.close()
            }

            // Drain both pipes concurrently while the process runs; reading
            // only after termination can deadlock once a pipe buffer fills.
            // Each pipe is capped at maxOutputBytes — exceeding the cap
            // terminates the child and sets the truncated flag.
            let truncatedFlag = TruncationFlag()
            async let stdoutData = readWithLimit(
                stdoutPipe.fileHandleForReading,
                maxBytes: maxOutputBytes,
                box: box,
                truncated: truncatedFlag
            )
            async let stderrData = readWithLimit(
                stderrPipe.fileHandleForReading,
                maxBytes: maxOutputBytes,
                box: box,
                truncated: truncatedFlag
            )

            var exitCode: Int32 = -1
            for await code in exitStream {
                exitCode = code
            }

            return CLIResult(
                stdout: await stdoutData,
                stderr: await stderrData,
                exitCode: exitCode,
                isTruncated: truncatedFlag.value
            )
        } onCancel: {
            box.terminateIfRunning()
        }
    }

    // MARK: - Chunked pipe reading

    /// Reads from `handle` in 64 KiB chunks.  If the accumulated byte count
    /// reaches `maxBytes`, the process is terminated and the `truncated`
    /// flag is set.  Returns the accumulated data (which may be partial).
    private static func readWithLimit(
        _ handle: FileHandle,
        maxBytes: Int,
        box: ProcessBox,
        truncated: TruncationFlag
    ) async -> Data {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let chunkSize = 65536
                var data = Data()
                data.reserveCapacity(min(chunkSize, maxBytes))

                while true {
                    guard let chunk = try? handle.read(upToCount: chunkSize),
                          !chunk.isEmpty
                    else { break }

                    if data.count + chunk.count > maxBytes {
                        let remaining = maxBytes - data.count
                        if remaining > 0 {
                            data.append(chunk.prefix(remaining))
                        }
                        truncated.value = true
                        box.terminateIfRunning()
                        break
                    }
                    data.append(chunk)
                }
                continuation.resume(returning: data)
            }
        }
    }
}

// MARK: - Shared mutable truncation flag

/// Lightweight `@unchecked Sendable` box for a boolean flag that
/// `readWithLimit` sets when output exceeds the cap.  Only ever
/// accessed from the `DispatchQueue` serial context or read after
/// both reads have settled, so a full lock is not required.
private final class TruncationFlag: @unchecked Sendable {
    var value = false
}
#endif