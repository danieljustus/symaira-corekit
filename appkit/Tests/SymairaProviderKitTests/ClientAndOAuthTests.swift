import Foundation
import XCTest
@testable import SymairaProviderKit

final class ClientAndOAuthTests: XCTestCase {
    func testOpenRouterModelsAreDiscoveredAndAuthenticated() async throws {
        let descriptor = try XCTUnwrap(SymairaProviderCatalog.bundled.provider(id: "openrouter"))
        let http = RecordingHTTPClient(
            data: Data(#"{"data":[{"id":"model-a","context_window":1234}]}"#.utf8),
            statusCode: 200
        )
        let client = SymairaProviderClient(
            configuration: SymairaProviderConfiguration(descriptor: descriptor),
            credentialResolver: SymairaCredentialResolver(environment: ["OPENROUTER_API_KEY": "test-key"]),
            httpClient: http
        )

        let models = try await client.discoverModels()
        XCTAssertEqual(models, [SymairaProviderModel(id: "model-a", contextWindow: 1234)])
        XCTAssertEqual(http.lastRequest?.url?.absoluteString, "https://openrouter.ai/api/v1/models")
        XCTAssertEqual(http.lastRequest?.value(forHTTPHeaderField: "Authorization"), "Bearer test-key")
    }

    func testOllamaDiscoveryReplacesV1WithLocalDiscoveryPath() async throws {
        let descriptor = try XCTUnwrap(SymairaProviderCatalog.bundled.provider(id: "ollama"))
        let http = RecordingHTTPClient(
            data: Data(#"{"models":[{"name":"llama3.1","context_window":8192}]}"#.utf8),
            statusCode: 200
        )
        let client = SymairaProviderClient(
            configuration: SymairaProviderConfiguration(descriptor: descriptor),
            httpClient: http
        )

        let models = try await client.discoverModels()
        XCTAssertEqual(models.first?.id, "llama3.1")
        XCTAssertEqual(models.first?.contextWindow, 8192)
        XCTAssertEqual(http.lastRequest?.url?.absoluteString, "http://localhost:11434/api/tags")
        XCTAssertNil(http.lastRequest?.value(forHTTPHeaderField: "Authorization"))
    }

    func testConnectionUsesNonBillableModelsEndpoint() async throws {
        let descriptor = try XCTUnwrap(SymairaProviderCatalog.bundled.provider(id: "openai"))
        let http = RecordingHTTPClient(data: Data(#"{"data":[]}"#.utf8), statusCode: 200)
        let client = SymairaProviderClient(
            configuration: SymairaProviderConfiguration(descriptor: descriptor),
            credentialResolver: SymairaCredentialResolver(environment: ["OPENAI_API_KEY": "test-key"]),
            httpClient: http
        )

        let result = try await client.testConnection()
        XCTAssertEqual(result.providerID, "openai")
        XCTAssertEqual(result.endpoint.absoluteString, "https://api.openai.com/v1/models")
        XCTAssertEqual(http.lastRequest?.httpMethod, "GET")
        XCTAssertEqual(http.lastRequest?.url?.absoluteString, "https://api.openai.com/v1/models")
    }

    func testMissingRequiredBaseURLFailsBeforeNetwork() async throws {
        let descriptor = try XCTUnwrap(SymairaProviderCatalog.bundled.provider(id: "custom"))
        let http = RecordingHTTPClient(data: Data(), statusCode: 200)
        let client = SymairaProviderClient(
            configuration: SymairaProviderConfiguration(descriptor: descriptor),
            httpClient: http
        )

        do {
            _ = try await client.testConnection()
            XCTFail("expected required base URL error")
        } catch let error as SymairaProviderError {
            XCTAssertEqual(error.code, .providerError)
            XCTAssertNil(http.lastRequest)
        }
    }

    func testOAuthAuthorizationRequestUsesPKCES256() throws {
        let authenticator = makeAuthenticator()
        let request = try authenticator.makeAuthorizationRequest()
        let query = try XCTUnwrap(URLComponents(url: request.url, resolvingAgainstBaseURL: false)?.queryItems)
        let values = Dictionary(uniqueKeysWithValues: query.compactMap { item in
            item.value.map { (item.name, $0) }
        })
        XCTAssertEqual(values["response_type"], "code")
        XCTAssertEqual(values["client_id"], "client-id")
        XCTAssertEqual(values["code_challenge_method"], "S256")
        XCTAssertEqual(values["redirect_uri"], "symaira://oauth/callback")
        XCTAssertEqual(values["scope"], "openid profile")
        XCTAssertEqual(values["code_challenge"]?.count, 43)
        XCTAssertFalse(request.state.isEmpty)
        XCTAssertFalse(request.codeVerifier.isEmpty)
    }

    func testOAuthExchangeMapsTokenResponse() async throws {
        let http = RecordingHTTPClient(
            data: Data(#"{"access_token":"access-token","refresh_token":"refresh-token","token_type":"Bearer","expires_in":3600}"#.utf8),
            statusCode: 200
        )
        let authenticator = makeAuthenticator(httpClient: http)
        let authorization = try authenticator.makeAuthorizationRequest()
        let token = try await authenticator.exchange(code: "auth-code", state: authorization.state, request: authorization)

        XCTAssertEqual(token.accessToken, "access-token")
        XCTAssertEqual(token.refreshToken, "refresh-token")
        XCTAssertEqual(token.tokenType, "Bearer")
        XCTAssertNotNil(token.expiresAt)
        XCTAssertEqual(http.lastRequest?.httpMethod, "POST")
        XCTAssertEqual(http.lastRequest?.value(forHTTPHeaderField: "Content-Type"), "application/x-www-form-urlencoded")
        XCTAssertTrue(String(decoding: http.lastRequest?.httpBody ?? Data(), as: UTF8.self).contains("grant_type=authorization_code"))
    }

    func testOAuthStateMismatchFailsBeforeNetwork() async throws {
        let http = RecordingHTTPClient(data: Data(), statusCode: 200)
        let authenticator = makeAuthenticator(httpClient: http)
        let authorization = try authenticator.makeAuthorizationRequest()

        do {
            _ = try await authenticator.exchange(code: "auth-code", state: "wrong", request: authorization)
            XCTFail("expected state validation error")
        } catch let error as SymairaOAuthError {
            XCTAssertEqual(error, .invalidState)
            XCTAssertNil(http.lastRequest)
        }
    }

    private func makeAuthenticator(httpClient: any SymairaProviderHTTPClient = RecordingHTTPClient(data: Data(), statusCode: 200)) -> SymairaOAuthAuthenticator {
        SymairaOAuthAuthenticator(
            configuration: SymairaOAuthConfiguration(
                authorizationURL: URL(string: "https://auth.example.test/authorize")!,
                tokenURL: URL(string: "https://auth.example.test/token")!,
                clientID: "client-id",
                scopes: ["openid", "profile"],
                redirectURI: "symaira://oauth/callback"
            ),
            httpClient: httpClient
        )
    }
}

private final class RecordingHTTPClient: SymairaProviderHTTPClient, @unchecked Sendable {
    private let responseData: Data
    private let statusCode: Int
    private let responseHeaders: [String: String]
    private let lock = NSLock()
    private var storedRequest: URLRequest?

    init(data: Data, statusCode: Int, headers: [String: String] = [:]) {
        self.responseData = data
        self.statusCode = statusCode
        self.responseHeaders = headers
    }

    var lastRequest: URLRequest? {
        lock.withLock { storedRequest }
    }

    func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        lock.withLock { storedRequest = request }
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: statusCode,
            httpVersion: nil,
            headerFields: responseHeaders
        )!
        return (responseData, response)
    }
}
