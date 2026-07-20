#if os(macOS)
import Foundation

/// Defines the operational state of a background daemon.
public enum DaemonState: Sendable, Equatable {
    case stopped
    case starting
    case running(pid: Int32)
    case failed(String)
}

/// A single log entry from stdout or stderr of a daemon.
public struct DaemonLogLine: Sendable, Identifiable, Equatable {
    public let id: UUID
    public let timestamp: Date
    public let text: String
    public let isError: Bool

    public init(id: UUID = UUID(), timestamp: Date = Date(), text: String, isError: Bool) {
        self.id = id
        self.timestamp = timestamp
        self.text = text
        self.isError = isError
    }
}

/// A long-running background process supervisor that handles start/stop lifecycle,
/// environment setup, stdout/stderr pipe streaming, and termination escalation.
public final class DaemonSupervisor: @unchecked Sendable {
    private let lock = NSLock()
    
    private var process: Process?
    private var stdoutFH: FileHandle?
    private var stderrFH: FileHandle?
    private var logContinuation: AsyncStream<DaemonLogLine>.Continuation?
    private var stopRequested = false
    
    private var _state: DaemonState = .stopped
    private var _logs: [DaemonLogLine] = []
    
    private let maxLogsLimit = 1000
    
    /// The current operational state of the supervisor.
    public var state: DaemonState {
        lock.lock()
        defer { lock.unlock() }
        return _state
    }
    
    /// Buffered historical log lines. Capped at `maxLogsLimit`.
    public var logs: [DaemonLogLine] {
        lock.lock()
        defer { lock.unlock() }
        return _logs
    }
    
    /// Optional closure called on every new log line.
    public var onLog: (@Sendable (DaemonLogLine) -> Void)?
    
    /// Optional closure called when the daemon state changes.
    public var onStateChange: (@Sendable (DaemonState) -> Void)?
    
    public init(onLog: (@Sendable (DaemonLogLine) -> Void)? = nil, onStateChange: (@Sendable (DaemonState) -> Void)? = nil) {
        self.onLog = onLog
        self.onStateChange = onStateChange
    }
    
    deinit {
        lock.lock()
        let proc = process
        lock.unlock()
        proc?.terminate()
    }
    
    /// Starts the specified binary with arguments and environment.
    /// Returns an `AsyncStream` that yields new log lines as they arrive.
    public func start(
        executable: URL,
        arguments: [String],
        environment: [String: String]? = nil
    ) -> AsyncStream<DaemonLogLine> {
        stopInternal()
        
        updateState(.starting)
        appendLogLine("[daemon] Starting \(executable.lastPathComponent) \(arguments.joined(separator: " "))…", isError: false)
        
        guard FileManager.default.isExecutableFile(atPath: executable.path) else {
            let errMsg = "Binary is not executable at path: \(executable.path)"
            updateState(.failed(errMsg))
            appendLogLine("[daemon] ERROR: \(errMsg)", isError: true)
            return AsyncStream { $0.finish() }
        }
        
        let proc = Process()
        proc.executableURL = executable
        proc.arguments = arguments
        
        var mergedEnv = ProcessInfo.processInfo.environment
        if let path = mergedEnv["PATH"] {
            mergedEnv["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:\(path)"
        } else {
            mergedEnv["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        }
        if let environment = environment {
            for (key, val) in environment {
                mergedEnv[key] = val
            }
        }
        proc.environment = mergedEnv
        
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        proc.standardOutput = stdoutPipe
        proc.standardError = stderrPipe
        
        let outFH = stdoutPipe.fileHandleForReading
        let errFH = stderrPipe.fileHandleForReading
        
        lock.lock()
        stdoutFH = outFH
        stderrFH = errFH
        process = proc
        stopRequested = false
        lock.unlock()
        
        return AsyncStream<DaemonLogLine> { continuation in
            lock.lock()
            self.logContinuation = continuation
            lock.unlock()
            
            outFH.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
                self?.processIncomingOutput(text, isError: false)
            }
            
            errFH.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
                self?.processIncomingOutput(text, isError: true)
            }
            
            proc.terminationHandler = { [weak self] proc in
                guard let self = self else { return }
                let exitCode = proc.terminationStatus
                
                self.lock.lock()
                if exitCode != 0, !self.stopRequested {
                    self._state = .failed("Process exited with code \(exitCode)")
                    self.appendLogLineInternal("[daemon] Process exited with code \(exitCode)", isError: true)
                } else {
                    self._state = .stopped
                    self.appendLogLineInternal("[daemon] Process stopped cleanly", isError: false)
                }
                let changeCallback = self.onStateChange
                let stateCopy = self._state
                let continuation = self.logContinuation
                self.cleanup()
                self.logContinuation = nil
                self.lock.unlock()

                continuation?.finish()
                if let changeCallback {
                    changeCallback(stateCopy)
                }
            }
            
            do {
                try proc.run()
                let pid = proc.processIdentifier
                updateState(.running(pid: pid))
                appendLogLine("[daemon] Process started (PID \(pid))", isError: false)
            } catch {
                updateState(.failed(error.localizedDescription))
                appendLogLine("[daemon] Failed to start: \(error.localizedDescription)", isError: true)
                
                lock.lock()
                cleanup()
                self.logContinuation?.finish()
                self.logContinuation = nil
                lock.unlock()
            }
        }
    }
    
    /// Stops the process gracefully. Escalates to force-killing via SIGINT and SIGKILL if the process fails to exit.
    public func stop() {
        stopInternal()
    }
    
    private func stopInternal() {
        lock.lock()
        let currentProcess = process
        lock.unlock()

        guard let proc = currentProcess, proc.isRunning else {
            updateState(.stopped)

            lock.lock()
            cleanup()
            let continuation = logContinuation
            logContinuation = nil
            lock.unlock()

            continuation?.finish()
            return
        }
        
        appendLogLine("[daemon] Stopping process...", isError: false)
        lock.lock()
        stopRequested = true
        lock.unlock()
        proc.terminate()
        
        let processToKill = proc
        let pid = proc.processIdentifier
        
        // Schedule fallback escalation
        DispatchQueue.global(qos: .userInitiated).asyncAfter(deadline: .now() + 2.0) { [weak self] in
            guard processToKill.isRunning else { return }
            self?.appendLogLine("[daemon] Escalating stop: sending SIGINT to PID \(pid)...", isError: true)
            processToKill.interrupt()
            
            DispatchQueue.global(qos: .userInitiated).asyncAfter(deadline: .now() + 1.5) { [weak self, processToKill] in
                guard processToKill.isRunning else { return }
                self?.appendLogLine("[daemon] Force killing process: sending SIGKILL to PID \(pid)...", isError: true)
                Darwin.kill(pid, SIGKILL)
            }
        }
    }
    
    private func cleanup() {
        stdoutFH?.readabilityHandler = nil
        stderrFH?.readabilityHandler = nil
        stdoutFH = nil
        stderrFH = nil
        process = nil
        stopRequested = false
    }
    
    private func processIncomingOutput(_ text: String, isError: Bool) {
        let lines = text.components(separatedBy: .newlines)
        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { continue }
            appendLogLine(trimmed, isError: isError)
        }
    }
    
    private func appendLogLine(_ message: String, isError: Bool) {
        lock.lock()
        let line = appendLogLineInternal(message, isError: isError)
        let logCallback = onLog
        let continuation = logContinuation
        lock.unlock()
        
        if let logCallback {
            logCallback(line)
        }
        
        continuation?.yield(line)
    }
    
    @discardableResult
    private func appendLogLineInternal(_ message: String, isError: Bool) -> DaemonLogLine {
        let line = DaemonLogLine(text: message, isError: isError)
        _logs.append(line)
        if _logs.count > maxLogsLimit {
            _logs.removeFirst(_logs.count - maxLogsLimit)
        }
        return line
    }
    
    private func updateState(_ newState: DaemonState) {
        lock.lock()
        _state = newState
        let changeCallback = onStateChange
        lock.unlock()
        
        if let changeCallback {
            changeCallback(newState)
        }
    }
}
#endif
