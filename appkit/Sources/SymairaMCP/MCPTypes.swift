import Foundation

// MARK: - JSON values

/// A JSON value, used wherever the MCP protocol carries arbitrary structured
/// data: request `params`, response `result`, tool `arguments`, and
/// `capabilities`. Kept dependency-free and `Sendable` so it crosses task and
/// actor boundaries freely.
public enum MCPJSONValue: Sendable, Equatable, Hashable {
    case null
    case bool(Bool)
    case number(Double)
    case string(String)
    case array([MCPJSONValue])
    case object([String: MCPJSONValue])

    /// The value as a string, if it is one.
    public var stringValue: String? {
        if case .string(let value) = self { value } else { nil }
    }

    /// The value as a boolean, if it is one.
    public var boolValue: Bool? {
        if case .bool(let value) = self { value } else { nil }
    }

    /// The value as a double, if it is a number.
    public var doubleValue: Double? {
        if case .number(let value) = self { value } else { nil }
    }

    /// The value as an `Int64`, if it is an integral number within the exact
    /// `Double` range (±2⁵³). Use this instead of `doubleValue` for integer
    /// tool arguments such as counts.
    public var intValue: Int64? {
        guard case .number(let value) = self,
              value.rounded() == value,
              value >= -9_007_199_254_740_992, value <= 9_007_199_254_740_992
        else { return nil }
        return Int64(value)
    }

    /// The value as an array, if it is one.
    public var arrayValue: [MCPJSONValue]? {
        if case .array(let value) = self { value } else { nil }
    }

    /// The value as an object, if it is one.
    public var objectValue: [String: MCPJSONValue]? {
        if case .object(let value) = self { value } else { nil }
    }
}

extension MCPJSONValue: Codable {
    public init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
            return
        }
        if let value = try? container.decode(Bool.self) {
            self = .bool(value)
            return
        }
        if let value = try? container.decode(String.self) {
            self = .string(value)
            return
        }
        if let value = try? container.decode(Double.self) {
            self = .number(value)
            return
        }
        if let value = try? container.decode([MCPJSONValue].self) {
            self = .array(value)
            return
        }
        if let value = try? container.decode([String: MCPJSONValue].self) {
            self = .object(value)
            return
        }
        throw DecodingError.typeMismatch(
            MCPJSONValue.self,
            .init(codingPath: decoder.codingPath, debugDescription: "Unsupported JSON value")
        )
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null:
            try container.encodeNil()
        case .bool(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .string(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        }
    }
}

// MARK: - JSON-RPC 2.0 messages

/// A JSON-RPC 2.0 request id: a string, a number, or null.
public enum MCPJSONRPCID: Sendable, Equatable, Hashable {
    case string(String)
    case number(Int64)
    case null
}

extension MCPJSONRPCID: Codable {
    public init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
            return
        }
        if let value = try? container.decode(String.self) {
            self = .string(value)
            return
        }
        if let value = try? container.decode(Int64.self) {
            self = .number(value)
            return
        }
        throw DecodingError.typeMismatch(
            MCPJSONRPCID.self,
            .init(codingPath: decoder.codingPath, debugDescription: "JSON-RPC id must be a string, a number, or null")
        )
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }
}

/// An inbound JSON-RPC 2.0 request or notification.
public struct MCPJSONRPCRequest: Sendable, Equatable, Codable {
    public var jsonrpc: String?
    public var id: MCPJSONRPCID?
    public var method: String
    public var params: MCPJSONValue?

    /// Requests without an id — or with an explicit null id — are
    /// notifications: the server dispatches them for side effects and never
    /// responds, per JSON-RPC 2.0 §2.2.
    public var isNotification: Bool { id == nil || id == .null }

    public init(jsonrpc: String? = "2.0", id: MCPJSONRPCID? = nil, method: String, params: MCPJSONValue? = nil) {
        self.jsonrpc = jsonrpc
        self.id = id
        self.method = method
        self.params = params
    }

    private enum CodingKeys: String, CodingKey {
        case jsonrpc, id, method, params
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        jsonrpc = try container.decodeIfPresent(String.self, forKey: .jsonrpc)
        if container.contains(.id) {
            // An explicit null id decodes to `.none` here; the request is then
            // treated as a notification via `isNotification`.
            id = try container.decode(MCPJSONRPCID?.self, forKey: .id)
        } else {
            id = nil
        }
        method = try container.decode(String.self, forKey: .method)
        params = try container.decodeIfPresent(MCPJSONValue.self, forKey: .params)
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encodeIfPresent(jsonrpc, forKey: .jsonrpc)
        if let id {
            try container.encode(id, forKey: .id)
        }
        try container.encode(method, forKey: .method)
        try container.encodeIfPresent(params, forKey: .params)
    }
}

/// An outbound JSON-RPC 2.0 success response.
public struct MCPJSONRPCResponse: Sendable, Equatable, Codable {
    public var jsonrpc: String
    public var id: MCPJSONRPCID
    public var result: MCPJSONValue

    public init(id: MCPJSONRPCID, result: MCPJSONValue, jsonrpc: String = "2.0") {
        self.jsonrpc = jsonrpc
        self.id = id
        self.result = result
    }
}

/// An outbound JSON-RPC 2.0 error response.
public struct MCPJSONRPCErrorResponse: Sendable, Equatable, Codable {
    public var jsonrpc: String
    public var id: MCPJSONRPCID
    public var error: MCPJSONRPCErrorObject

    public init(id: MCPJSONRPCID, error: MCPJSONRPCErrorObject, jsonrpc: String = "2.0") {
        self.jsonrpc = jsonrpc
        self.id = id
        self.error = error
    }
}

/// The `error` object of a JSON-RPC error response.
public struct MCPJSONRPCErrorObject: Sendable, Equatable, Codable {
    public var code: Int
    public var message: String
    public var data: MCPJSONValue?

    public init(code: Int, message: String, data: MCPJSONValue? = nil) {
        self.code = code
        self.message = message
        self.data = data
    }
}

/// Standard JSON-RPC 2.0 error codes used by `MCPServer`.
public enum MCPJSONRPCErrorCode: Int, Sendable {
    /// Invalid JSON was received.
    case parseError = -32700
    /// The JSON sent is not a valid request object.
    case invalidRequest = -32600
    /// The method does not exist.
    case methodNotFound = -32601
    /// The method's params are invalid (e.g. they do not decode into the
    /// handler's typed `Params`).
    case invalidParams = -32602
    /// The method handler threw an error.
    case internalError = -32603
}

// MARK: - Method plumbing

/// A parameter type for methods that take no arguments.
///
/// Decodes successfully from any JSON payload — including a request with no
/// `params` at all — so it can be used with `MCPServer.withMethodHandler`
/// for parameterless methods such as `ping` or `tools/list`.
public struct MCPNoParams: Sendable, Equatable, Decodable {
    public init() {}

    public init(from decoder: any Decoder) throws {
        // Accepts any payload: there is nothing to decode.
    }
}

/// An error a method handler can throw to fail the request with a specific
/// message.
///
/// `MCPServer` maps it to a JSON-RPC `-32603 Internal error` response whose
/// `message` carries the error text. Any other error thrown by a handler is
/// mapped the same way, with a description of the error as the message.
public struct MCPError: Error, Sendable, Equatable {
    public let message: String

    public init(_ message: String) {
        self.message = message
    }
}

// MARK: - Tools capability

/// A tool advertised by `tools/list`, per the MCP `tools` capability.
public struct MCPTool: Sendable, Equatable, Codable {
    public var name: String
    public var description: String?
    public var inputSchema: MCPJSONSchema

    public init(name: String, description: String? = nil, inputSchema: MCPJSONSchema) {
        self.name = name
        self.description = description
        self.inputSchema = inputSchema
    }
}

/// A JSON Schema object describing a tool's input, in the shape MCP clients
/// expect: `{ "type": "object", "properties": …, "required": […] }`.
public struct MCPJSONSchema: Sendable, Equatable, Codable {
    public var type: String
    public var properties: [String: MCPJSONSchemaProperty]
    public var required: [String]
    public var description: String?

    public init(
        type: String = "object",
        properties: [String: MCPJSONSchemaProperty] = [:],
        required: [String] = [],
        description: String? = nil
    ) {
        self.type = type
        self.properties = properties
        self.required = required
        self.description = description
    }
}

/// One property of an `MCPJSONSchema`.
///
/// A reference type because `items` — the property's own item schema, used
/// for `type == "array"` properties — would make a struct recursively contain
/// itself. All stored properties are immutable.
public final class MCPJSONSchemaProperty: Equatable, Codable, Sendable {
    public let type: String
    public let description: String?
    /// The item schema for `type == "array"` properties.
    public let items: MCPJSONSchemaProperty?
    /// Allowed values, encoded as JSON Schema's `enum` keyword.
    public let enumValues: [MCPJSONValue]?
    /// JSON Schema `minimum` bound for numeric properties (e.g. brightness 0.0).
    public let minimum: Double?
    /// JSON Schema `maximum` bound for numeric properties (e.g. brightness 1.0).
    public let maximum: Double?

    public init(
        type: String,
        description: String? = nil,
        items: MCPJSONSchemaProperty? = nil,
        enumValues: [MCPJSONValue]? = nil,
        minimum: Double? = nil,
        maximum: Double? = nil
    ) {
        self.type = type
        self.description = description
        self.items = items
        self.enumValues = enumValues
        self.minimum = minimum
        self.maximum = maximum
    }

    private enum CodingKeys: String, CodingKey {
        case type, description, items
        case enumValues = "enum"
        case minimum, maximum
    }

    public static func == (lhs: MCPJSONSchemaProperty, rhs: MCPJSONSchemaProperty) -> Bool {
        lhs.type == rhs.type
            && lhs.description == rhs.description
            && lhs.items == rhs.items
            && lhs.enumValues == rhs.enumValues
            && lhs.minimum == rhs.minimum
            && lhs.maximum == rhs.maximum
    }
}

/// The result of `tools/list`.
public struct MCPListToolsResult: Sendable, Equatable, Codable {
    public var tools: [MCPTool]

    public init(tools: [MCPTool]) {
        self.tools = tools
    }
}

/// Params of a `tools/call` request.
public struct MCPCallToolParams: Sendable, Equatable, Decodable {
    public var name: String
    public var arguments: [String: MCPJSONValue]?

    public init(name: String, arguments: [String: MCPJSONValue]? = nil) {
        self.name = name
        self.arguments = arguments
    }
}

/// A text content block of a tool call result: `{ "type": "text", "text": … }`.
public struct MCPTextContent: Sendable, Equatable, Codable {
    public var type: String
    public var text: String

    public init(type: String = "text", text: String) {
        self.type = type
        self.text = text
    }
}

/// The result of `tools/call`: MCP content blocks plus an optional error flag.
///
/// Setting `isError` to `true` reports a tool-level failure to the client
/// without failing the JSON-RPC request itself.
public struct MCPCallToolResult: Sendable, Equatable, Codable {
    public var content: [MCPTextContent]
    public var isError: Bool?

    public init(content: [MCPTextContent], isError: Bool? = nil) {
        self.content = content
        self.isError = isError
    }
}

// MARK: - Initialize handshake

/// The result of `initialize`: the negotiated protocol version, the server's
/// capabilities, and its identity.
public struct MCPInitializeResult: Sendable, Equatable, Codable {
    public var protocolVersion: String
    public var capabilities: [String: MCPJSONValue]
    public var serverInfo: MCPServerInfo

    public init(protocolVersion: String, capabilities: [String: MCPJSONValue], serverInfo: MCPServerInfo) {
        self.protocolVersion = protocolVersion
        self.capabilities = capabilities
        self.serverInfo = serverInfo
    }
}

/// The `serverInfo` object of an `initialize` result.
public struct MCPServerInfo: Sendable, Equatable, Codable {
    public var name: String
    public var version: String

    public init(name: String, version: String) {
        self.name = name
        self.version = version
    }
}

/// Params of an `initialize` request. All fields are optional: the built-in
/// handler only decodes them for validation and never inspects them.
public struct MCPInitializeParams: Sendable, Equatable, Decodable {
    public var protocolVersion: String?
    public var capabilities: MCPJSONValue?
    public var clientInfo: MCPJSONValue?

    public init(protocolVersion: String? = nil, capabilities: MCPJSONValue? = nil, clientInfo: MCPJSONValue? = nil) {
        self.protocolVersion = protocolVersion
        self.capabilities = capabilities
        self.clientInfo = clientInfo
    }
}
