import Foundation

/// A bidirectional transport for MCP JSON-RPC messages.
///
/// Messages are exchanged as newline-delimited JSON strings, matching the MCP
/// spec's stdio framing. A transport delivers incoming messages through the
/// stream returned by `start()` and writes outgoing messages via `send(_:)`.
public protocol MCPTransport: Sendable {
    /// Begins reading from the transport's input and returns the stream of
    /// incoming messages, one JSON-RPC message per element.
    ///
    /// Must be called exactly once. The stream finishes when the input closes
    /// (e.g. stdin EOF) or when `stop()` is called.
    func start() -> AsyncStream<String>

    /// Writes one JSON-RPC message to the transport's output.
    ///
    /// The message is written as a single line, terminated with a newline.
    /// Throws if the output cannot be written (e.g. broken pipe).
    func send(_ message: String) async throws

    /// Stops reading and finishes the incoming message stream. Safe to call
    /// more than once and before `start()`.
    func stop()
}

/// The standard MCP stdio transport.
///
/// Reads newline-delimited JSON from an input `FileHandle` and writes to an
/// output `FileHandle`. The default initializer uses the process's standard
/// input and output; the handles are injectable so tests and embedding apps
/// can drive the server in-process through `Pipe`s.
///
/// Incoming data is read through `readabilityHandler` (a dispatch source), so
/// the transport works alongside other `FileHandle` readers in the same
/// process — notably `FileHandle.bytes.lines`, whose shared IO actor queue
/// deadlocks when two readers use it concurrently.
public final class MCPStdioTransport: MCPTransport, @unchecked Sendable {
    private let input: FileHandle
    private let output: FileHandle
    private let lock = NSLock()

    private var continuation: AsyncStream<String>.Continuation?
    private var lineBuffer = Data()
    private var stopped = false

    /// Creates a transport reading from `input` and writing to `output`.
    public init(input: FileHandle, output: FileHandle) {
        self.input = input
        self.output = output
    }

    /// Creates a transport on the process's standard input and output.
    public convenience init() {
        self.init(input: .standardInput, output: .standardOutput)
    }

    public func start() -> AsyncStream<String> {
        AsyncStream { continuation in
            lock.lock()
            if stopped {
                lock.unlock()
                continuation.finish()
                return
            }
            self.continuation = continuation
            lock.unlock()

            continuation.onTermination = { [weak self] _ in
                self?.stop()
            }

            input.readabilityHandler = { [weak self] handle in
                guard let self else { return }
                let data = handle.availableData
                self.processIncoming(data, continuation: continuation)
            }
        }
    }

    public func send(_ message: String) async throws {
        try writeSync(message)
    }

    /// Synchronous write path: `NSLock` is unavailable from async contexts in
    /// the macOS 27 SDK, and the lock must never be held across a suspension.
    private func writeSync(_ message: String) throws {
        var data = Data(message.utf8)
        data.append(0x0A)
        lock.lock()
        defer { lock.unlock() }
        try output.write(contentsOf: data)
    }

    public func stop() {
        lock.lock()
        stopped = true
        input.readabilityHandler = nil
        let cont = continuation
        continuation = nil
        lock.unlock()
        cont?.finish()
    }

    // MARK: - Read loop

    /// Called from the readability handler for each chunk of incoming data.
    /// An empty chunk marks EOF.
    private func processIncoming(_ data: Data, continuation: AsyncStream<String>.Continuation) {
        var lines: [String] = []
        var flushFinal = false

        lock.lock()
        if data.isEmpty {
            // EOF: deliver any trailing partial line, then finish.
            input.readabilityHandler = nil
            if let finalLine = extractLine(flushRemainder: true) {
                lines.append(finalLine)
            }
            flushFinal = true
            self.continuation = nil
        } else {
            lineBuffer.append(data)
            while let line = extractLine(flushRemainder: false) {
                lines.append(line)
            }
        }
        lock.unlock()

        for line in lines {
            continuation.yield(line)
        }
        if flushFinal {
            continuation.finish()
        }
    }

    /// Extracts one newline-delimited line from `lineBuffer` (called with the
    /// lock held). Blank lines are skipped. With `flushRemainder`, a trailing
    /// line without a newline is returned as the final line.
    private func extractLine(flushRemainder: Bool) -> String? {
        if let newlineIndex = lineBuffer.firstIndex(of: 0x0A) {
            let lineData = lineBuffer[lineBuffer.startIndex..<newlineIndex]
            lineBuffer.removeSubrange(lineBuffer.startIndex...newlineIndex)
            let text = String(decoding: lineData, as: UTF8.self)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if text.isEmpty {
                return extractLine(flushRemainder: flushRemainder)
            }
            return text
        }
        if flushRemainder, !lineBuffer.isEmpty {
            let text = String(decoding: lineBuffer, as: UTF8.self)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            lineBuffer.removeAll(keepingCapacity: true)
            return text.isEmpty ? nil : text
        }
        return nil
    }
}
