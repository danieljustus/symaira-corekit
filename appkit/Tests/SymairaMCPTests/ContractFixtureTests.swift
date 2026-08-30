import XCTest
@testable import SymairaMCP

/// Asserts `SymairaMCP` against `contracts/json_encoding.json`, vendored from
/// `symaira-corekit` (see `contracts/README.md`). This is a regression guard
/// for the wire-protocol half of the fixture: the JSON-RPC envelope must keep
/// its MCP-spec camelCase field names verbatim (`jsonrpc`, `id`, `method`,
/// `params`, `code`, `message`, `data`) — not the `snake_case` convention
/// that applies to tool-defined result/argument payloads. If someone adds a
/// `keyEncodingStrategy` to one of `MCPServer`'s `JSONEncoder` calls, this
/// test catches the wire-protocol break before a client does.
final class MCPJSONEncodingContractFixtureTests: XCTestCase {
    private struct Fixture: Decodable {
        let protocolEnvelopeKeyCase: String

        enum CodingKeys: String, CodingKey {
            case protocolEnvelopeKeyCase = "protocol_envelope_key_case"
        }
    }

    private func loadFixture() throws -> Fixture {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // ContractFixtureTests.swift
            .deletingLastPathComponent() // SymairaMCPTests
            .deletingLastPathComponent() // Tests
            .appendingPathComponent("contracts/json_encoding.json")
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(Fixture.self, from: data)
    }

    func testRequestEnvelopeKeysMatchFixture() throws {
        let fixture = try loadFixture()
        XCTAssertEqual(fixture.protocolEnvelopeKeyCase, "camelCase")

        let request = MCPJSONRPCRequest(id: .number(1), method: "ping", params: nil)
        let data = try JSONEncoder().encode(request)
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(Set(object.keys), ["jsonrpc", "id", "method"])
    }

    func testErrorResponseEnvelopeKeysMatchFixture() throws {
        let fixture = try loadFixture()
        XCTAssertEqual(fixture.protocolEnvelopeKeyCase, "camelCase")

        let response = MCPJSONRPCErrorResponse(
            id: .number(1),
            error: MCPJSONRPCErrorObject(code: -32601, message: "Method not found")
        )
        let data = try JSONEncoder().encode(response)
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(Set(object.keys), ["jsonrpc", "id", "error"])
        let errorObject = try XCTUnwrap(object["error"] as? [String: Any])
        XCTAssertEqual(Set(errorObject.keys), ["code", "message"])
    }
}

/// Asserts `MCPTool.annotations` against `contracts/mcp_tool_annotations.json`
/// (see issue #142 / `contracts/README.md`): the four hint fields must keep
/// the contract's exact wire names, and a tool without annotations must emit
/// no `annotations` key at all — the contract's own explicit-declaration
/// rule says a missing `readOnlyHint` is read as the least-trusted "write"
/// classification downstream, so silence there is meaningful and must not be
/// spoofed by an empty object.
final class MCPToolAnnotationsContractFixtureTests: XCTestCase {
    private struct Hint: Decodable {
        let wireName: String
        let mustBeDeclaredExplicitly: Bool

        enum CodingKeys: String, CodingKey {
            case wireName = "wire_name"
            case mustBeDeclaredExplicitly = "must_be_declared_explicitly"
        }
    }

    private struct Fixture: Decodable {
        let schemaVersion: Int
        let hints: [Hint]

        enum CodingKeys: String, CodingKey {
            case schemaVersion = "schema_version"
            case hints
        }
    }

    private func loadFixture() throws -> Fixture {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // ContractFixtureTests.swift
            .deletingLastPathComponent() // SymairaMCPTests
            .deletingLastPathComponent() // Tests
            .appendingPathComponent("contracts/mcp_tool_annotations.json")
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(Fixture.self, from: data)
    }

    func testAnnotationFieldNamesMatchFixture() throws {
        let fixture = try loadFixture()
        XCTAssertEqual(fixture.schemaVersion, 1)

        let annotations = MCPToolAnnotations(
            readOnlyHint: true,
            idempotentHint: true,
            openWorldHint: false,
            destructiveHint: false
        )
        let data = try JSONEncoder().encode(annotations)
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(Set(object.keys), Set(fixture.hints.map(\.wireName)))
    }

    func testReadOnlyHintMustBeDeclaredExplicitlyPerFixture() throws {
        let fixture = try loadFixture()
        let readOnly = try XCTUnwrap(fixture.hints.first { $0.wireName == "readOnlyHint" })
        XCTAssertTrue(readOnly.mustBeDeclaredExplicitly)
    }

    func testToolWithoutAnnotationsEmitsNoAnnotationsKey() throws {
        let tool = MCPTool(name: "ping", inputSchema: MCPJSONSchema())
        let data = try JSONEncoder().encode(tool)
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertFalse(object.keys.contains("annotations"))
    }

    func testToolWithAnnotationsEncodesUnderAnnotationsKeyWithMCPSpecNames() throws {
        var tool = MCPTool(name: "read_file", inputSchema: MCPJSONSchema())
        tool.annotations = MCPToolAnnotations(readOnlyHint: true)
        let data = try JSONEncoder().encode(tool)
        let object = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        let annotations = try XCTUnwrap(object["annotations"] as? [String: Any])

        XCTAssertEqual(annotations["readOnlyHint"] as? Bool, true)
        XCTAssertNil(annotations["idempotentHint"], "Unset hints must be omitted, not encoded as null")
    }
}
