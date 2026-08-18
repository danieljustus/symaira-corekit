import Foundation

// MARK: - MCPServer

/// A minimal, dependency-free Model Context Protocol (MCP) server.
///
/// `SymairaMCP` implements the server side of MCP on Foundation and Swift
/// Concurrency only — no third-party packages, per this repo's rule. The
/// architecture mirrors the `Server` + `StdioTransport` +
/// `withMethodHandler(_:)` design of `modelcontextprotocol/swift-sdk`: typed
/// per-method closure registration replaces a hand-rolled
/// `switch request.method` dispatcher. Only the design pattern is adopted;
/// the implementation is written from scratch (see
/// `docs/module-boundary-decisions.md`).
///
/// The server handles the MCP handshake (`initialize`, which echoes the
/// configured `protocolVersion`, and `notifications/initialized`), answers
/// `ping`, and dispatches every other method to handlers registered with
/// `withMethodHandler(_:handler:)`. Error mapping follows JSON-RPC 2.0:
/// malformed JSON → `-32700 Parse error`, invalid request → `-32600`,
/// unknown method → `-32601 Method not found`, undecodable params →
/// `-32602 Invalid params`, handler errors → `-32603 Internal error` with
/// the error's message. Requests without an id are notifications: they are
/// dispatched for side effects but never answered.
///
/// The `tools` capability (`tools/list`, `tools/call`) is fully supported.
/// `resources`, `prompts`, `sampling`, `elicitation`, and `completions` are
/// out of scope for now; the dispatcher is generic, so each of them is just
/// another `withMethodHandler` registration whenever a consumer needs it.
///
/// Usage:
///
///     let server = MCPServer(name: "symoperate", version: "1.0.0")
///         .withMethodHandler("tools/list") { (_: MCPNoParams) async throws -> MCPListToolsResult in
///             MCPListToolsResult(tools: [])
///         }
///         .withMethodHandler("tools/call") { (params: MCPCallToolParams) async throws -> MCPCallToolResult in
///             MCPCallToolResult(content: [MCPTextContent(text: "hi \(params.name)")])
///         }
///     try await server.start(transport: MCPStdioTransport())
///
/// Transport framing follows the MCP spec's stdio convention: one JSON-RPC
/// message per newline-delimited line.
public final class MCPServer: @unchecked Sendable {
    /// The MCP protocol version this server speaks: the 2025-06-18 revision
    /// of the spec, which is what current MCP clients negotiate.
    public static let supportedProtocolVersion = "2025-06-18"

    private let lock = NSLock()

    private let name: String
    private let version: String
    private let protocolVersion: String
    private let capabilities: [String: MCPJSONValue]

    private var handlers: [String: AnyMethodHandler] = [:]
    private var transport: (any MCPTransport)?
    private var stopRequested = false

    /// Creates a server that advertises `name`/`version` in its `initialize`
    /// response.
    ///
    /// - Parameters:
    ///   - name: Server name reported as `serverInfo.name`.
    ///   - version: Server version reported as `serverInfo.version`.
    ///   - protocolVersion: MCP protocol version echoed on `initialize`.
    ///     Defaults to `MCPServer.supportedProtocolVersion` (`"2025-06-18"`).
    ///   - capabilities: Additional MCP capabilities advertised on
    ///     `initialize`. A `tools` capability is added automatically when
    ///     `tools/list` or `tools/call` handlers are registered, unless
    ///     already present.
    public init(
        name: String,
        version: String,
        protocolVersion: String = MCPServer.supportedProtocolVersion,
        capabilities: [String: MCPJSONValue] = [:]
    ) {
        self.name = name
        self.version = version
        self.protocolVersion = protocolVersion
        self.capabilities = capabilities

        // Built-in methods — capture values as locals to avoid retaining self.
        let serverName = name
        let serverVersion = version
        let serverProtocolVersion = protocolVersion
        withMethodHandler("ping") { (_: MCPNoParams) async throws -> MCPJSONValue in
            .object([:])
        }
        withMethodHandler("initialize") { [weak self] (_: MCPInitializeParams) async throws -> MCPInitializeResult in
            let caps = self?.effectiveCapabilities ?? [:]
            return MCPInitializeResult(
                protocolVersion: serverProtocolVersion,
                capabilities: caps,
                serverInfo: MCPServerInfo(name: serverName, version: serverVersion)
            )
        }
    }

    /// Registers a typed handler for `method`.
    ///
    /// When a request for `method` arrives, its `params` object is decoded
    /// into `Params` and the handler is awaited; the handler's return value
    /// is encoded as the JSON-RPC `result`. A request whose params do not
    /// decode into `Params` fails with `-32602 Invalid params`; an error
    /// thrown by the handler fails with `-32603 Internal error` carrying the
    /// error's message.
    ///
    /// Registering a handler for a built-in method replaces the built-in
    /// implementation. Handlers registered for methods that arrive as
    /// notifications (requests without an id) are invoked for their side
    /// effects and never produce a response.
    ///
    /// - Parameters:
    ///   - method: The MCP method name, e.g. `"tools/list"`.
    ///   - handler: The typed handler. Use `MCPNoParams` as `Params` for
    ///     parameterless methods.
    /// - Returns: `self`, so registrations can be chained.
    @discardableResult
    public func withMethodHandler<Params: Decodable & Sendable, Result: Encodable & Sendable>(
        _ method: String,
        handler: @escaping @Sendable (Params) async throws -> Result
    ) -> MCPServer {
        let boxed: @Sendable (MCPJSONValue?) async throws -> MCPJSONValue = { params in
            let decoded: Params
            do {
                let paramsData: Data
                if let params {
                    paramsData = try JSONEncoder().encode(params)
                } else {
                    // Missing or null params decode as an empty object, so
                    // parameterless methods can use `MCPNoParams`.
                    paramsData = Data("{}".utf8)
                }
                decoded = try JSONDecoder().decode(Params.self, from: paramsData)
            } catch let error as DecodingError {
                throw MCPInvalidParamsError(underlying: error)
            }
            let result = try await handler(decoded)
            let resultData = try JSONEncoder().encode(result)
            return try JSONDecoder().decode(MCPJSONValue.self, from: resultData)
        }
        lock.lock()
        handlers[method] = AnyMethodHandler(handle: boxed)
        lock.unlock()
        return self
    }

    /// Starts serving on `transport` and runs until the transport's input
    /// closes (e.g. stdin EOF) or `stop()` is called.
    ///
    /// Messages are processed sequentially in the order they arrive, so a
    /// handler that awaits I/O delays later messages until it returns — the
    /// same serialization the reference swift-sdk server applies.
    public func start(transport: any MCPTransport) async throws {
        let shouldStop = try beginStart(transport)
        if shouldStop {
            transport.stop()
            return
        }

        let messages = transport.start()
        for await message in messages {
            await handleIncoming(message)
        }
    }

    /// Synchronous start path: `NSLock` is unavailable from async contexts in
    /// the macOS 27 SDK.
    private func beginStart(_ transport: any MCPTransport) throws -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard self.transport == nil else {
            throw MCPError("MCPServer.start(transport:) must only be called once")
        }
        self.transport = transport
        return stopRequested
    }

    /// Stops the server: ends `start(transport:)` and finishes the
    /// transport's incoming stream. Safe to call before or while `start` is
    /// running, and from any thread.
    public func stop() {
        lock.lock()
        stopRequested = true
        let transport = self.transport
        lock.unlock()
        transport?.stop()
    }

    /// The capabilities advertised on `initialize`, with the `tools`
    /// capability added automatically when tool handlers are registered.
    private var effectiveCapabilities: [String: MCPJSONValue] {
        lock.lock()
        defer { lock.unlock() }
        var caps = capabilities
        if handlers["tools/list"] != nil || handlers["tools/call"] != nil {
            caps["tools"] = caps["tools"] ?? .object(["listChanged": .bool(false)])
        }
        return caps
    }

    // MARK: - Dispatch

    private func handleIncoming(_ line: String) async {
        let data = Data(line.utf8)

        // 1. Must be syntactically valid JSON. Fragments are allowed so a
        //    scalar (valid JSON, not a request) reaches the -32600 path below.
        guard (try? JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed])) != nil else {
            await sendError(id: .null, code: .parseError, message: "Parse error")
            return
        }

        // 2. Must be a valid request object.
        let request: MCPJSONRPCRequest
        do {
            request = try JSONDecoder().decode(MCPJSONRPCRequest.self, from: data)
        } catch {
            await sendError(id: .null, code: .invalidRequest, message: "Invalid Request")
            return
        }

        // 3. If present, jsonrpc must be "2.0".
        if let jsonrpc = request.jsonrpc, jsonrpc != "2.0" {
            await sendError(
                id: request.id ?? .null,
                code: .invalidRequest,
                message: "Invalid Request: jsonrpc must be \"2.0\""
            )
            return
        }

        // Requests without an id are notifications: dispatch for side
        // effects, never respond — even with an error (JSON-RPC 2.0 §2.2).
        let responseID: MCPJSONRPCID?
        if let id = request.id, id != .null {
            responseID = id
        } else {
            responseID = nil
        }

        guard let handler = handler(for: request.method) else {
            if let responseID {
                await sendError(
                    id: responseID,
                    code: .methodNotFound,
                    message: "Method not found: \(request.method)"
                )
            }
            return
        }

        do {
            let result = try await handler.handle(request.params)
            if let responseID {
                await sendResponse(id: responseID, result: result)
            }
        } catch let error as MCPInvalidParamsError {
            if let responseID {
                await sendError(id: responseID, code: .invalidParams, message: "Invalid params: \(error.description)")
            }
        } catch let error as MCPError {
            if let responseID {
                await sendError(id: responseID, code: .internalError, message: error.message, data: error.data)
            }
        } catch {
            if let responseID {
                await sendError(id: responseID, code: .internalError, message: String(describing: error))
            }
        }
    }

    private func handler(for method: String) -> AnyMethodHandler? {
        lock.lock()
        defer { lock.unlock() }
        return handlers[method]
    }

    private func sendResponse(id: MCPJSONRPCID, result: MCPJSONValue) async {
        let response = MCPJSONRPCResponse(id: id, result: result)
        guard let data = try? JSONEncoder().encode(response) else { return }
        await write(data)
    }

    private func sendError(id: MCPJSONRPCID, code: MCPJSONRPCErrorCode, message: String, data: MCPJSONValue? = nil) async {
        let response = MCPJSONRPCErrorResponse(
            id: id,
            error: MCPJSONRPCErrorObject(code: code.rawValue, message: message, data: data)
        )
        guard let data = try? JSONEncoder().encode(response) else { return }
        await write(data)
    }

    /// Reads `transport` under the lock (synchronous safe).
    private func lockedTransport() -> (any MCPTransport)? {
        lock.lock()
        defer { lock.unlock() }
        return transport
    }

    private func write(_ data: Data) async {
        guard let transport = lockedTransport(), let line = String(data: data, encoding: .utf8) else { return }
        do {
            try await transport.send(line)
        } catch {
            // The client went away (e.g. broken pipe): shut down the loop.
            stop()
        }
    }
}

/// Type-erased box for a registered typed method handler.
private struct AnyMethodHandler: Sendable {
    let handle: @Sendable (MCPJSONValue?) async throws -> MCPJSONValue
}

/// Marks a failure to decode a request's params into the handler's typed
/// `Params`; `MCPServer` maps it to JSON-RPC `-32602 Invalid params`.
private struct MCPInvalidParamsError: Error, Sendable {
    let underlying: DecodingError

    var description: String {
        switch underlying {
        case .keyNotFound(let key, _):
            return "Missing key: \(key.stringValue)"
        case .typeMismatch(let type, _):
            return "Type mismatch: expected \(type)"
        case .valueNotFound(let type, _):
            return "Value not found: \(type)"
        case .dataCorrupted(let context):
            return context.debugDescription
        @unknown default:
            return String(describing: underlying)
        }
    }
}
