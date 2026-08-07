import XCTest
@testable import SymairaMCP

final class MCPServerTests: XCTestCase {

    // MARK: - Helpers

    /// Reads one newline-delimited line from a handle. Test-local only: a
    /// single iterator is created per handle so reads never interleave.
    private final class LineReader: @unchecked Sendable {
        private var iterator: AsyncLineSequence<FileHandle.AsyncBytes>.AsyncIterator

        init(handle: FileHandle) {
            iterator = handle.bytes.lines.makeAsyncIterator()
        }

        func nextLine() async throws -> String? {
            try await iterator.next()
        }
    }

    private struct Harness {
        let server: MCPServer
        let clientWrite: FileHandle
        let reader: LineReader
        let serverTask: Task<Void, Error>
    }

    private struct ResponseEnvelope: Decodable {
        let jsonrpc: String?
        let id: MCPJSONRPCID?
        let result: MCPJSONValue?
        let error: MCPJSONRPCErrorObject?
    }

    private enum TestTimeout: Error {
        case waitingForResponse
    }

    /// Boots a server on an in-process pipe pair and returns a harness that
    /// lets the test act as the MCP client.
    private func makeHarness(_ configure: (MCPServer) -> MCPServer) -> Harness {
        let clientToServer = Pipe()
        let serverToClient = Pipe()
        let transport = MCPStdioTransport(
            input: clientToServer.fileHandleForReading,
            output: serverToClient.fileHandleForWriting
        )
        let server = configure(MCPServer(name: "test-server", version: "1.0.0"))
        // Detached: async XCTest methods run on a special executor that never
        // schedules unstructured tasks created inside the test body.
        let serverTask = Task.detached { try await server.start(transport: transport) }
        return Harness(
            server: server,
            clientWrite: clientToServer.fileHandleForWriting,
            reader: LineReader(handle: serverToClient.fileHandleForReading),
            serverTask: serverTask
        )
    }

    private func send(_ line: String, to handle: FileHandle) throws {
        var data = Data(line.utf8)
        data.append(0x0A)
        try handle.write(contentsOf: data)
    }

    /// Reads the next response line, failing the test after a 10s timeout
    /// instead of hanging the suite if the server misbehaves.
    private func nextLine(_ reader: LineReader) async throws -> String {
        try await withThrowingTaskGroup(of: String?.self) { group in
            group.addTask { try await reader.nextLine() }
            group.addTask {
                try await Task.sleep(for: .seconds(10))
                return nil
            }
            guard let first = try await group.next() else {
                throw TestTimeout.waitingForResponse
            }
            group.cancelAll()
            if let line = first {
                return line
            }
            throw TestTimeout.waitingForResponse
        }
    }

    private func decodeEnvelope(_ line: String) throws -> ResponseEnvelope {
        try JSONDecoder().decode(ResponseEnvelope.self, from: Data(line.utf8))
    }

    private func decodeResult<T: Decodable>(_ envelope: ResponseEnvelope, as type: T.Type) throws -> T? {
        guard let result = envelope.result else { return nil }
        let data = try JSONEncoder().encode(result)
        return try JSONDecoder().decode(type, from: data)
    }

    // MARK: - End-to-end

    func testEndToEndInitializeListAndCallTool() async throws {
        let echoTool = MCPTool(
            name: "echo",
            description: "Echoes the provided text",
            inputSchema: MCPJSONSchema(
                properties: [
                    "text": MCPJSONSchemaProperty(type: "string", description: "Text to echo")
                ],
                required: ["text"]
            )
        )

        let harness = makeHarness { server in
            server
                .withMethodHandler("tools/list") { (_: MCPNoParams) async throws -> MCPListToolsResult in
                    MCPListToolsResult(tools: [echoTool])
                }
                .withMethodHandler("tools/call") { (params: MCPCallToolParams) async throws -> MCPCallToolResult in
                    guard params.name == "echo" else {
                        throw MCPError("Unknown tool: \(params.name)")
                    }
                    let text: String
                    if case .string(let value) = params.arguments?["text"] {
                        text = value
                    } else {
                        text = "(no text)"
                    }
                    let count = params.arguments?["count"]?.intValue ?? 0
                    return MCPCallToolResult(content: [MCPTextContent(text: "echo: \(text) x\(count)")])
                }
        }

        // 1. initialize → protocol version echo + server info + tools capability
        try send(#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test-client","version":"1.0"}}}"#, to: harness.clientWrite)
        let initLine = try await nextLine(harness.reader)
        let initEnvelope = try decodeEnvelope(initLine)
        XCTAssertEqual(initEnvelope.id, .number(1))
        let initResult = try XCTUnwrap(try decodeResult(initEnvelope, as: MCPInitializeResult.self))
        XCTAssertEqual(initResult.protocolVersion, "2025-06-18")
        XCTAssertEqual(initResult.serverInfo.name, "test-server")
        XCTAssertEqual(initResult.serverInfo.version, "1.0.0")
        if case .object(let caps) = initResult.capabilities["tools"] {
            XCTAssertEqual(caps["listChanged"], .bool(false))
        } else {
            XCTFail("Expected a tools capability, got \(String(describing: initResult.capabilities["tools"]))")
        }

        // 2. notifications/initialized must not produce a response: the next
        //    line read must be the tools/list response.
        try send(#"{"jsonrpc":"2.0","method":"notifications/initialized"}"#, to: harness.clientWrite)
        try send(#"{"jsonrpc":"2.0","id":2,"method":"tools/list"}"#, to: harness.clientWrite)
        let listLine = try await nextLine(harness.reader)
        let listEnvelope = try decodeEnvelope(listLine)
        XCTAssertEqual(listEnvelope.id, .number(2))
        let listResult = try XCTUnwrap(try decodeResult(listEnvelope, as: MCPListToolsResult.self))
        XCTAssertEqual(listResult.tools.map(\.name), ["echo"])
        XCTAssertEqual(listResult.tools.first?.inputSchema.required, ["text"])
        XCTAssertEqual(listResult.tools.first?.inputSchema.properties["text"]?.type, "string")

        // 3. tools/call with typed arguments (string + integer access)
        try send(#"{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"echo","arguments":{"text":"hello","count":3}}}"#, to: harness.clientWrite)
        let callLine = try await nextLine(harness.reader)
        let callEnvelope = try decodeEnvelope(callLine)
        XCTAssertEqual(callEnvelope.id, .number(3))
        let callResult = try XCTUnwrap(try decodeResult(callEnvelope, as: MCPCallToolResult.self))
        XCTAssertEqual(callResult.content.first?.text, "echo: hello x3")
        XCTAssertNil(callResult.isError)

        // 4. ping → empty result
        try send(#"{"jsonrpc":"2.0","id":4,"method":"ping"}"#, to: harness.clientWrite)
        let pingLine = try await nextLine(harness.reader)
        let pingEnvelope = try decodeEnvelope(pingLine)
        XCTAssertEqual(pingEnvelope.id, .number(4))
        XCTAssertEqual(pingEnvelope.result, .object([:]))

        // 5. EOF on stdin ends the server loop cleanly.
        try harness.clientWrite.close()
        try await harness.serverTask.value
    }

    // MARK: - Error paths

    func testUnknownMethodReturnsMethodNotFound() async throws {
        let harness = makeHarness { $0 }
        defer { try? harness.clientWrite.close() }

        try send(#"{"jsonrpc":"2.0","id":42,"method":"bogus/method"}"#, to: harness.clientWrite)
        let envelope = try decodeEnvelope(try await nextLine(harness.reader))
        XCTAssertEqual(envelope.id, .number(42))
        XCTAssertNil(envelope.result)
        XCTAssertEqual(envelope.error?.code, -32601)
        XCTAssertTrue(envelope.error?.message.contains("bogus/method") == true)
    }

    func testMalformedJSONReturnsParseError() async throws {
        let harness = makeHarness { $0 }
        defer { try? harness.clientWrite.close() }

        try send("this is not json", to: harness.clientWrite)
        let envelope = try decodeEnvelope(try await nextLine(harness.reader))
        // The response carries `"id": null`; optional decoding surfaces it as nil.
        XCTAssertNil(envelope.id)
        XCTAssertEqual(envelope.error?.code, -32700)
    }

    func testValidJSONButInvalidRequestReturnsInvalidRequestError() async throws {
        let harness = makeHarness { $0 }
        defer { try? harness.clientWrite.close() }

        // Valid JSON, but missing the required "method" field.
        try send(#"{"jsonrpc":"2.0","id":7}"#, to: harness.clientWrite)
        let envelope = try decodeEnvelope(try await nextLine(harness.reader))
        XCTAssertNil(envelope.id)
        XCTAssertEqual(envelope.error?.code, -32600)
    }

    func testHandlerErrorReturnsInternalErrorWithMessage() async throws {
        let harness = makeHarness { server in
            server.withMethodHandler("tools/fail") { (_: MCPNoParams) async throws -> MCPJSONValue in
                throw MCPError("deliberate failure")
            }
        }
        defer { try? harness.clientWrite.close() }

        try send(#"{"jsonrpc":"2.0","id":8,"method":"tools/fail"}"#, to: harness.clientWrite)
        let envelope = try decodeEnvelope(try await nextLine(harness.reader))
        XCTAssertEqual(envelope.id, .number(8))
        XCTAssertEqual(envelope.error?.code, -32603)
        XCTAssertEqual(envelope.error?.message, "deliberate failure")
    }

    func testHandlerErrorCarriesDataOverTheWire() async throws {
        let harness = makeHarness { server in
            server.withMethodHandler("tools/fail") { (_: MCPNoParams) async throws -> MCPJSONValue in
                throw MCPError("operation failed", data: .object(["code": .string("operation_failed")]))
            }
        }
        defer { try? harness.clientWrite.close() }

        try send(#"{"jsonrpc":"2.0","id":8,"method":"tools/fail"}"#, to: harness.clientWrite)
        let envelope = try decodeEnvelope(try await nextLine(harness.reader))
        XCTAssertEqual(envelope.id, .number(8))
        XCTAssertEqual(envelope.error?.code, -32603)
        XCTAssertEqual(envelope.error?.message, "operation failed")
        XCTAssertEqual(envelope.error?.data, .object(["code": .string("operation_failed")]))
    }

    func testUndecodableParamsReturnsInvalidParamsError() async throws {
        let harness = makeHarness { server in
            server.withMethodHandler("tools/call") { (_: MCPCallToolParams) async throws -> MCPCallToolResult in
                MCPCallToolResult(content: [])
            }
        }
        defer { try? harness.clientWrite.close() }

        // Missing the required "name" field.
        try send(#"{"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"arguments":{}}}"#, to: harness.clientWrite)
        let envelope = try decodeEnvelope(try await nextLine(harness.reader))
        XCTAssertEqual(envelope.id, .number(9))
        XCTAssertEqual(envelope.error?.code, -32602)
        XCTAssertTrue(envelope.error?.message.contains("name") == true)
    }

    // MARK: - Lifecycle

    func testStopEndsTheServerLoop() async throws {
        let harness = makeHarness { $0 }

        try send(#"{"jsonrpc":"2.0","id":1,"method":"ping"}"#, to: harness.clientWrite)
        let envelope = try decodeEnvelope(try await nextLine(harness.reader))
        XCTAssertEqual(envelope.id, .number(1))

        harness.server.stop()
        try await harness.serverTask.value
    }

    // MARK: - Schema bounds

    func testSchemaPropertyEncodesMinMaxBounds() throws {
        let property = MCPJSONSchemaProperty(
            type: "number",
            description: "Brightness 0.0–1.0",
            minimum: 0.0,
            maximum: 1.0
        )
        let data = try JSONEncoder().encode(property)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["type"] as? String, "number")
        XCTAssertEqual(object["minimum"] as? Double, 0.0)
        XCTAssertEqual(object["maximum"] as? Double, 1.0)
    }

    func testSchemaPropertyRoundTripsMinMaxBounds() throws {
        let property = MCPJSONSchemaProperty(
            type: "integer",
            description: "Charge limit percent",
            minimum: 50.0,
            maximum: 100.0
        )
        let data = try JSONEncoder().encode(property)
        let decoded = try JSONDecoder().decode(MCPJSONSchemaProperty.self, from: data)
        XCTAssertEqual(decoded, property)
        XCTAssertEqual(decoded.minimum, 50.0)
        XCTAssertEqual(decoded.maximum, 100.0)
    }

    func testSchemaPropertyOmitsAbsentBounds() throws {
        let property = MCPJSONSchemaProperty(type: "string")
        let data = try JSONEncoder().encode(property)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertNil(object["minimum"])
        XCTAssertNil(object["maximum"])
    }

    func testToolListCarriesMinMaxBoundsOverTheWire() async throws {
        let harness = makeHarness { server in
            server.withMethodHandler("tools/list") { (_: MCPNoParams) async throws -> MCPListToolsResult in
                MCPListToolsResult(tools: [
                    MCPTool(
                        name: "set_brightness",
                        description: "Set built-in display brightness",
                        inputSchema: MCPJSONSchema(
                            properties: [
                                "value": MCPJSONSchemaProperty(
                                    type: "number",
                                    minimum: 0.0,
                                    maximum: 1.0
                                )
                            ],
                            required: ["value"]
                        )
                    )
                ])
            }
        }
        defer { try? harness.clientWrite.close() }

        try send(#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#, to: harness.clientWrite)
        let envelope = try decodeEnvelope(try await nextLine(harness.reader))
        let listResult = try XCTUnwrap(try decodeResult(envelope, as: MCPListToolsResult.self))
        let value = try XCTUnwrap(listResult.tools.first?.inputSchema.properties["value"])
        XCTAssertEqual(value.minimum, 0.0)
        XCTAssertEqual(value.maximum, 1.0)
    }
}
