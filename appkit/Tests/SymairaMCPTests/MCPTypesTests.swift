import XCTest
@testable import SymairaMCP

final class MCPTypesTests: XCTestCase {

    // MARK: - JSON-RPC request id semantics

    /// JSON-RPC 2.0 §2.2: a request without an id is a notification. An
    /// explicit null id must behave identically, per the custom `id` decoding
    /// in `MCPJSONRPCRequest`.
    func testNullIdAndMissingIdAreBothNotifications() throws {
        let decoder = JSONDecoder()

        let explicitNull = try decoder.decode(
            MCPJSONRPCRequest.self,
            from: Data(#"{"method":"x","id":null}"#.utf8)
        )
        XCTAssertTrue(explicitNull.isNotification)
        XCTAssertNil(explicitNull.id)
        XCTAssertEqual(explicitNull.method, "x")

        let missingId = try decoder.decode(
            MCPJSONRPCRequest.self,
            from: Data(#"{"method":"x"}"#.utf8)
        )
        XCTAssertTrue(missingId.isNotification)
        XCTAssertNil(missingId.id)
        XCTAssertEqual(missingId.method, "x")
    }

    /// A request carrying a real id is not a notification, whether the id is
    /// a number or a string.
    func testRequestWithIdIsNotANotification() throws {
        let decoder = JSONDecoder()

        let numeric = try decoder.decode(
            MCPJSONRPCRequest.self,
            from: Data(#"{"method":"x","id":7}"#.utf8)
        )
        XCTAssertFalse(numeric.isNotification)
        XCTAssertEqual(numeric.id, .number(7))

        let string = try decoder.decode(
            MCPJSONRPCRequest.self,
            from: Data(#"{"method":"x","id":"req-1"}"#.utf8)
        )
        XCTAssertFalse(string.isNotification)
        XCTAssertEqual(string.id, .string("req-1"))
    }

    /// Encoding a request with an id and decoding it again must preserve the
    /// id and the request as a whole.
    func testRequestWithIdRoundTrips() throws {
        let request = MCPJSONRPCRequest(
            id: .string("abc-123"),
            method: "tools/call",
            params: .object(["name": .string("echo")])
        )

        let data = try JSONEncoder().encode(request)
        let decoded = try JSONDecoder().decode(MCPJSONRPCRequest.self, from: data)

        XCTAssertEqual(decoded, request)
        XCTAssertEqual(decoded.id, .string("abc-123"))
        XCTAssertEqual(decoded.params, .object(["name": .string("echo")]))
        XCTAssertFalse(decoded.isNotification)
    }

    /// A notification (no id) encodes without an `id` key at all.
    func testNotificationOmitsIdKeyWhenEncoded() throws {
        let notification = MCPJSONRPCRequest(method: "notifications/initialized")

        let data = try JSONEncoder().encode(notification)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertNil(object["id"])
        XCTAssertEqual(object["method"] as? String, "notifications/initialized")
    }

    // MARK: - MCPJSONValue accessors

    func testStringValueAccessor() {
        XCTAssertEqual(MCPJSONValue.string("hello").stringValue, "hello")
        XCTAssertNil(MCPJSONValue.number(3.14).stringValue)
        XCTAssertNil(MCPJSONValue.bool(true).stringValue)
        XCTAssertNil(MCPJSONValue.null.stringValue)
        XCTAssertNil(MCPJSONValue.array([.string("a")]).stringValue)
        XCTAssertNil(MCPJSONValue.object(["k": .string("v")]).stringValue)
    }

    func testBoolValueAccessor() {
        XCTAssertEqual(MCPJSONValue.bool(true).boolValue, true)
        XCTAssertEqual(MCPJSONValue.bool(false).boolValue, false)
        XCTAssertNil(MCPJSONValue.string("true").boolValue)
        XCTAssertNil(MCPJSONValue.number(1).boolValue)
        XCTAssertNil(MCPJSONValue.null.boolValue)
    }

    func testDoubleValueAccessor() {
        XCTAssertEqual(MCPJSONValue.number(3.14).doubleValue, 3.14)
        XCTAssertEqual(MCPJSONValue.number(-0.5).doubleValue, -0.5)
        XCTAssertNil(MCPJSONValue.string("3.14").doubleValue)
        XCTAssertNil(MCPJSONValue.bool(true).doubleValue)
        XCTAssertNil(MCPJSONValue.null.doubleValue)
    }

    /// Decoding a heterogeneous JSON payload yields values whose accessors
    /// line up with their wire types.
    func testAccessorsAfterDecoding() throws {
        let value = try JSONDecoder().decode(
            MCPJSONValue.self,
            from: Data(#"{"name":"echo","count":3,"enabled":true,"ratio":0.5,"nothing":null}"#.utf8)
        )

        guard case .object(let fields) = value else {
            return XCTFail("Expected an object, got \(value)")
        }
        XCTAssertEqual(fields["name"]?.stringValue, "echo")
        XCTAssertEqual(fields["count"]?.doubleValue, 3)
        XCTAssertEqual(fields["enabled"]?.boolValue, true)
        XCTAssertEqual(fields["ratio"]?.doubleValue, 0.5)
        XCTAssertEqual(fields["nothing"], .null)
        // Non-matching accessors must stay nil.
        XCTAssertNil(fields["name"]?.boolValue)
        XCTAssertNil(fields["count"]?.stringValue)
        XCTAssertNil(fields["enabled"]?.doubleValue)
    }

    /// The custom Codable conformance round-trips every case of the enum.
    func testJSONValueRoundTrips() throws {
        let original = MCPJSONValue.object([
            "name": .string("echo"),
            "count": .number(3),
            "enabled": .bool(true),
            "tags": .array([.string("a"), .string("b")]),
            "nested": .object(["x": .null])
        ])

        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(MCPJSONValue.self, from: data)

        XCTAssertEqual(decoded, original)
    }

    // MARK: - Memberwise inits

    /// `MCPCallToolParams` is the tools/call params type; its memberwise init
    /// defaults `arguments` to nil.
    func testToolCallParamsMemberwiseInit() {
        let withArguments = MCPCallToolParams(name: "echo", arguments: ["text": .string("hi")])
        XCTAssertEqual(withArguments.name, "echo")
        XCTAssertEqual(withArguments.arguments, ["text": .string("hi")])

        let bare = MCPCallToolParams(name: "ping")
        XCTAssertEqual(bare.name, "ping")
        XCTAssertNil(bare.arguments)
    }

    /// `MCPInitializeParams` accepts all-optional fields and defaults each to
    /// nil.
    func testInitializeParamsMemberwiseInit() {
        let full = MCPInitializeParams(
            protocolVersion: "2025-06-18",
            capabilities: .object(["tools": .object(["listChanged": .bool(false)])]),
            clientInfo: .object(["name": .string("test-client"), "version": .string("1.0")])
        )
        XCTAssertEqual(full.protocolVersion, "2025-06-18")
        XCTAssertEqual(full.capabilities, .object(["tools": .object(["listChanged": .bool(false)])]))
        XCTAssertEqual(full.clientInfo, .object(["name": .string("test-client"), "version": .string("1.0")]))

        let empty = MCPInitializeParams()
        XCTAssertNil(empty.protocolVersion)
        XCTAssertNil(empty.capabilities)
        XCTAssertNil(empty.clientInfo)
    }

    /// The params types decode from wire JSON, matching what a client sends
    /// during `initialize` and `tools/call`.
    func testParamsTypesDecodeFromWireJSON() throws {
        let decoder = JSONDecoder()

        let initParams = try decoder.decode(
            MCPInitializeParams.self,
            from: Data(#"{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test-client","version":"1.0"}}"#.utf8)
        )
        XCTAssertEqual(initParams.protocolVersion, "2025-06-18")
        XCTAssertEqual(initParams.capabilities, .object([:]))
        XCTAssertEqual(initParams.clientInfo, .object(["name": .string("test-client"), "version": .string("1.0")]))

        let callParams = try decoder.decode(
            MCPCallToolParams.self,
            from: Data(#"{"name":"echo","arguments":{"text":"hello"}}"#.utf8)
        )
        XCTAssertEqual(callParams.name, "echo")
        XCTAssertEqual(callParams.arguments, ["text": .string("hello")])
    }
}
