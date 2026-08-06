#if os(macOS)
import Foundation
import Darwin

// MARK: - Typed errors

/// Errors surfaced by bounded subprocess execution inside the update flow.
/// Internal to `SymairaUpdateCheck`; call sites map the timeout path onto
/// the public `UpdateApplierError.subprocessTimeout` case.
enum SubprocessRunnerError: Error, Equatable {
    /// The executable could not be launched.
    case launchFailed(command: String)
}

// MARK: - Bounded subprocess execution

/// Result of a bounded subprocess invocation.
struct SubprocessResult: Equatable {
    /// Captured stdout (bounded at `maxOutputBytes`).
    let stdout: Data
    /// Captured stderr (bounded at `maxOutputBytes`).
    let stderr: Data
    /// The exit code of the process (a signal-derived value when terminated).
    let exitCode: Int32
    /// `true` when the timeout expired and the child was terminated.
    let timedOut: Bool
}

/// Runs subprocesses for the update flow with a mandatory timeout and
/// bounded, concurrent pipe draining (AGENTS.md loose-coupling rule:
/// "Subprocess execution must always have a timeout").
///
/// Mirrors the conventions of `SymairaCLIRunner.CLIRunner`: every
/// invocation has a timeout; stdout/stderr are drained concurrently while
/// the process runs so a full pipe buffer (64 KiB on Darwin) cannot
/// deadlock the child; output per stream is capped.
enum SubprocessRunner {
    /// Default per-invocation timeout in seconds.
    static let defaultTimeout: TimeInterval = 30
    /// Default per-stream output cap (16 MiB, same as `CLIRunner`).
    static let defaultMaxOutputBytes = 16 * 1024 * 1024
    /// Grace period after `terminate()` before escalating to SIGKILL.
    private static let terminationGraceSeconds: TimeInterval = 3

    /// Run a subprocess with a bounded wait. Does not throw on non-zero
    /// exit codes — inspect `SubprocessResult.exitCode`.
    ///
    /// - Throws: `SubprocessRunnerError.launchFailed` when the executable
    ///   cannot be launched.
    static func run(
        executable: URL,
        arguments: [String] = [],
        timeout: TimeInterval = defaultTimeout,
        maxOutputBytes: Int = defaultMaxOutputBytes
    ) throws -> SubprocessResult {
        let box = ProcessBox()
        box.process.executableURL = executable
        box.process.arguments = arguments

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        box.process.standardOutput = stdoutPipe
        box.process.standardError = stderrPipe

        do {
            try box.process.run()
        } catch {
            throw SubprocessRunnerError.launchFailed(command: commandName(executable, arguments))
        }

        // Drain both pipes concurrently while the process runs; reading
        // only after termination can deadlock once a pipe buffer fills.
        let stdoutHandleBox = HandleBox(stdoutPipe.fileHandleForReading)
        let stderrHandleBox = HandleBox(stderrPipe.fileHandleForReading)
        let stdoutBox = OutputBox()
        let stderrBox = OutputBox()
        let drainGroup = GroupBox()

        drainGroup.group.enter()
        DispatchQueue.global(qos: .userInitiated).async {
            stdoutBox.data = read(handle: stdoutHandleBox.handle, maxBytes: maxOutputBytes, box: box)
            drainGroup.group.leave()
        }
        drainGroup.group.enter()
        DispatchQueue.global(qos: .userInitiated).async {
            stderrBox.data = read(handle: stderrHandleBox.handle, maxBytes: maxOutputBytes, box: box)
            drainGroup.group.leave()
        }

        let timedOut = waitUntilExit(box, timeout: timeout)

        // The child is gone (exited or terminated), so both pipes have hit
        // EOF; join the drain tasks before returning their data.
        drainGroup.group.wait()

        return SubprocessResult(
            stdout: stdoutBox.data,
            stderr: stderrBox.data,
            exitCode: box.process.terminationStatus,
            timedOut: timedOut
        )
    }

    /// Run a subprocess and throw `UpdateApplierError.subprocessTimeout`
    /// when the timeout expires instead of returning a timed-out result.
    static func runChecked(
        executable: URL,
        arguments: [String] = [],
        timeout: TimeInterval = defaultTimeout,
        maxOutputBytes: Int = defaultMaxOutputBytes
    ) throws -> SubprocessResult {
        let result = try run(
            executable: executable,
            arguments: arguments,
            timeout: timeout,
            maxOutputBytes: maxOutputBytes
        )
        if result.timedOut {
            throw UpdateApplierError.subprocessTimeout(commandName(executable, arguments))
        }
        return result
    }

    // MARK: - Plumbing

    /// Block until the process exits, terminating it when `timeout`
    /// expires. Returns `true` when the timeout path was taken.
    private static func waitUntilExit(_ box: ProcessBox, timeout: TimeInterval) -> Bool {
        let semaphore = DispatchSemaphore(value: 0)
        box.process.terminationHandler = { _ in
            semaphore.signal()
        }
        // The handler is only guaranteed to fire when it is installed
        // before the process dies. A fast child (e.g. `which`) may already
        // be gone; never wait on a signal that can no longer arrive.
        guard box.process.isRunning else {
            return false
        }
        if semaphore.wait(timeout: .now() + timeout) == .timedOut {
            // Timeout: terminate the child, then give it a short grace
            // period before escalating to SIGKILL.
            box.process.terminate()
            if semaphore.wait(timeout: .now() + terminationGraceSeconds) == .timedOut {
                kill(box.process.processIdentifier, SIGKILL)
                // SIGKILL cannot be ignored; wait bounded for the handler.
                _ = semaphore.wait(timeout: .now() + terminationGraceSeconds)
            }
            return true
        }
        return false
    }

    /// Read a pipe in 64 KiB chunks until EOF, capping the accumulated
    /// data at `maxBytes`. When the cap is exceeded the child is
    /// terminated so the other drain sees EOF promptly.
    private static func read(handle: FileHandle, maxBytes: Int, box: ProcessBox) -> Data {
        var data = Data()
        data.reserveCapacity(min(65536, maxBytes))
        while true {
            guard let chunk = try? handle.read(upToCount: 65536), !chunk.isEmpty else { break }
            if data.count + chunk.count > maxBytes {
                let remaining = maxBytes - data.count
                if remaining > 0 {
                    data.append(chunk.prefix(remaining))
                }
                box.terminateIfRunning()
                break
            }
            data.append(chunk)
        }
        return data
    }

    private static func commandName(_ executable: URL, _ arguments: [String]) -> String {
        ([executable.lastPathComponent] + arguments).joined(separator: " ")
    }
}

// MARK: - Sendable boxes (Foundation types are not Sendable)

/// Non-Sendable `Process` confined behind an `@unchecked Sendable` box so
/// it can be reached from the drain and timeout paths.
private final class ProcessBox: @unchecked Sendable {
    let process = Process()

    func terminateIfRunning() {
        if process.isRunning {
            process.terminate()
        }
    }
}

/// Non-Sendable `FileHandle` confined behind an `@unchecked Sendable` box.
private final class HandleBox: @unchecked Sendable {
    let handle: FileHandle

    init(_ handle: FileHandle) {
        self.handle = handle
    }
}

/// Mutable accumulated output behind an `@unchecked Sendable` box; each
/// box is only ever written by its single drain task and read after the
/// drain has joined.
private final class OutputBox: @unchecked Sendable {
    var data = Data()
}

/// Non-Sendable `DispatchGroup` confined behind an `@unchecked Sendable`
/// box so the drain tasks can signal completion.
private final class GroupBox: @unchecked Sendable {
    let group = DispatchGroup()
}
#endif
