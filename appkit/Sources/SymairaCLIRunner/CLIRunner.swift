import Foundation

/// Result of a completed CLI invocation.
public struct CLIResult: Sendable {
    public let stdout: Data
    public let stderr: Data
    public let exitCode: Int32

    public init(stdout: Data, stderr: Data, exitCode: Int32) {
        self.stdout = stdout
        self.stderr = stderr
        self.exitCode = exitCode
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
    case executionFailed(code: Int32, stderr: String)
    case timeout(seconds: Double)
    case invalidJSON(description: String)
    case schemaMismatch(expected: Int, actual: Int)

    public var errorDescription: String? {
        switch self {
        case .binaryNotFound(let tool):
            return "The \(tool) binary could not be found (bundle, PATH, or Homebrew paths)."
        case .executionFailed(let code, let stderr):
            return "CLI execution failed with exit code \(code): \(stderr)"
        case .timeout(let seconds):
            return "CLI execution timed out after \(seconds) seconds."
        case .invalidJSON(let description):
            return "Failed to parse CLI JSON output: \(description)"
        case .schemaMismatch(let expected, let actual):
            return "CLI schema version \(actual) does not match expected \(expected). Try `brew upgrade`."
        }
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

    public let defaultTimeout: Double

    public init(defaultTimeout: Double = 30) {
        self.defaultTimeout = defaultTimeout
    }

    /// Run an executable and return stdout/stderr/exit code. Does NOT throw on
    /// non-zero exit codes — use `runChecked`/`runDecoding` for that.
    public func run(
        _ executable: URL,
        arguments: [String] = [],
        stdin: Data? = nil,
        timeout: Double? = nil
    ) async throws -> CLIResult {
        let seconds = timeout ?? defaultTimeout
        return try await withThrowingTaskGroup(of: CLIResult?.self) { group in
            group.addTask {
                try await Self.execute(executable: executable, arguments: arguments, stdin: stdin)
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

    /// Run and throw `executionFailed` on non-zero exit, returning stdout.
    @discardableResult
    public func runChecked(
        _ executable: URL,
        arguments: [String] = [],
        stdin: Data? = nil,
        timeout: Double? = nil
    ) async throws -> Data {
        let result = try await run(executable, arguments: arguments, stdin: stdin, timeout: timeout)
        guard result.exitCode == 0 else {
            throw CLIRunnerError.executionFailed(code: result.exitCode, stderr: result.stderrText)
        }
        return result.stdout
    }

    /// Run, check the exit code, and decode stdout as snake_case JSON.
    public func runDecoding<T: Decodable>(
        _ type: T.Type,
        executable: URL,
        arguments: [String] = [],
        stdin: Data? = nil,
        timeout: Double? = nil
    ) async throws -> T {
        let data = try await runChecked(executable, arguments: arguments, stdin: stdin, timeout: timeout)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw CLIRunnerError.invalidJSON(description: String(describing: error))
        }
    }

    // MARK: - Subprocess plumbing

    private static func execute(executable: URL, arguments: [String], stdin: Data?) async throws -> CLIResult {
        let box = ProcessBox()
        box.process.executableURL = executable
        box.process.arguments = arguments

        var env = ProcessInfo.processInfo.environment
        env["PATH"] = env["PATH"].map { "\(augmentedPATHPrefix):\($0)" } ?? augmentedPATHPrefix
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
            async let stdoutData = readToEnd(stdoutPipe.fileHandleForReading)
            async let stderrData = readToEnd(stderrPipe.fileHandleForReading)

            var exitCode: Int32 = -1
            for await code in exitStream {
                exitCode = code
            }

            return CLIResult(stdout: await stdoutData, stderr: await stderrData, exitCode: exitCode)
        } onCancel: {
            box.terminateIfRunning()
        }
    }

    private static func readToEnd(_ handle: FileHandle) async -> Data {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let data = (try? handle.readToEnd()) ?? Data()
                continuation.resume(returning: data)
            }
        }
    }
}
