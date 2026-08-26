import XCTest
@testable import SymairaProviderKit

final class CredentialAndErrorTests: XCTestCase {
    func testCredentialReferencesRoundTrip() throws {
        let references: [SymairaCredentialReference] = [
            .environment(variable: "OPENAI_API_KEY"),
            .keychain(service: "dev.symaira.provider", account: "openai-api-key"),
            .symvault(path: "secrets/openai_key"),
        ]
        for reference in references {
            XCTAssertEqual(try SymairaCredentialReference(rawValue: reference.rawValue), reference)
        }
        XCTAssertEqual(
            try SymairaCredentialReference(rawValue: "vault://secrets/openai_key"),
            .symvault(path: "secrets/openai_key")
        )
    }

    func testInvalidCredentialReferencesFailClosed() {
        for rawValue in ["", "file://secret", "env://not-valid!", "keychain:///account", "symvault://"] {
            XCTAssertThrowsError(try SymairaCredentialReference(rawValue: rawValue), rawValue)
        }
    }

    func testEnvironmentResolverNeverNeedsKeychain() async throws {
        let resolver = SymairaCredentialResolver(environment: ["OPENAI_API_KEY": "test-key"])
        let configured = try await resolver.resolve("env://OPENAI_API_KEY")
        let missing = try await resolver.resolve("env://MISSING_KEY")
        XCTAssertEqual(configured, "test-key")
        XCTAssertNil(missing)
    }

    func testRedactorHidesProviderCredentialShapes() {
        let token = "sk-" + "abcdEFGH12345678ijkl"
        let input = "Authorization: Bearer *** api_key=\(token)"
        let redacted = SymairaSecretRedactor.redact(input)
        XCTAssertFalse(redacted.contains(token))
        XCTAssertEqual(redacted.filter { $0 == "<" }.count, 1)
    }

    func testRedactorCoversDelimitedCredentialValues() {
        let value = "placeholder-value-1234"
        let input = "api_key = \"\(value)\" token: \(value)"

        let redacted = SymairaSecretRedactor.redact(input)

        XCTAssertFalse(redacted.contains(value))
    }

    func testHTTPErrorTaxonomy() {
        XCTAssertEqual(SymairaProviderErrorMapper.http(statusCode: 401).code, .authFailure)
        XCTAssertEqual(SymairaProviderErrorMapper.http(statusCode: 429).code, .rateLimited)
        XCTAssertEqual(
            SymairaProviderErrorMapper.http(statusCode: 400, body: Data("maximum context length exceeded".utf8)).code,
            .contextOverflow
        )
        XCTAssertEqual(SymairaProviderErrorMapper.http(statusCode: 404).code, .modelNotFound)
        XCTAssertEqual(SymairaProviderErrorMapper.http(statusCode: 500).code, .providerError)
    }

    func testHTTPErrorRedactsBodyExcerpt() {
        let token = "sk-" + "abcdEFGH12345678ijkl"
        let error = SymairaProviderErrorMapper.http(statusCode: 500, body: Data("upstream \(token)".utf8))
        XCTAssertFalse(error.bodyExcerpt?.contains(token) == true)
        XCTAssertTrue(error.bodyExcerpt?.contains(SymairaSecretRedactor.placeholder) == true)
    }
}
