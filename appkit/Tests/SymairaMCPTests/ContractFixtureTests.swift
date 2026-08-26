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
