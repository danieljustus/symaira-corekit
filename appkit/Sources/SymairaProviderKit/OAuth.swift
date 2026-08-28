import Foundation
import Security
import SymairaKeychain

#if canImport(CryptoKit)
import CryptoKit
#elseif canImport(Crypto)
import Crypto
#endif

/// Public OAuth client configuration. PKCE keeps the flow suitable for native apps.
public struct SymairaOAuthConfiguration: Sendable, Equatable {
    public let authorizationURL: URL
    public let tokenURL: URL
    public let clientID: String
    public let scopes: [String]
    public let redirectURI: String

    public init(
        authorizationURL: URL,
        tokenURL: URL,
        clientID: String,
        scopes: [String] = [],
        redirectURI: String
    ) {
        self.authorizationURL = authorizationURL
        self.tokenURL = tokenURL
        self.clientID = clientID
        self.scopes = scopes
        self.redirectURI = redirectURI
    }
}

/// The state required to complete a PKCE authorization flow.
public struct SymairaOAuthAuthorizationRequest: Sendable, Equatable {
    public let url: URL
    public let state: String
    public let codeVerifier: String

    public init(url: URL, state: String, codeVerifier: String) {
        self.url = url
        self.state = state
        self.codeVerifier = codeVerifier
    }
}

/// An OAuth access/refresh token stored without exposing its value in diagnostics.
public struct SymairaOAuthToken: Codable, Sendable, Equatable {
    public let accessToken: String
    public let refreshToken: String?
    public let tokenType: String
    public let expiresAt: Date?

    public init(
        accessToken: String,
        refreshToken: String? = nil,
        tokenType: String = "Bearer",
        expiresAt: Date? = nil
    ) {
        self.accessToken = accessToken
        self.refreshToken = refreshToken
        self.tokenType = tokenType
        self.expiresAt = expiresAt
    }

    public func isExpired(at date: Date = Date(), leeway: TimeInterval = 60) -> Bool {
        guard let expiresAt else { return false }
        return expiresAt <= date.addingTimeInterval(leeway)
    }

    private enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case tokenType = "token_type"
        case expiresAt = "expires_at"
    }
}

/// Keychain-backed storage for OAuth tokens.
public struct SymairaTokenStore: Sendable {
    public let keychain: SymairaKeychain
    public let account: String

    public init(
        providerID: String,
        keychain: SymairaKeychain = SymairaKeychain(app: "provider")
    ) {
        self.keychain = keychain
        self.account = "\(providerID)-oauth-token"
    }

    public func read() throws -> SymairaOAuthToken? {
        guard let value = try keychain.read(key: account) else { return nil }
        guard let data = value.data(using: .utf8) else {
            throw SymairaOAuthError.invalidStoredToken
        }
        do {
            return try JSONDecoder().decode(SymairaOAuthToken.self, from: data)
        } catch {
            throw SymairaOAuthError.invalidStoredToken
        }
    }

    @discardableResult
    public func save(_ token: SymairaOAuthToken) throws -> Bool {
        let data = try JSONEncoder().encode(token)
        guard let value = String(data: data, encoding: .utf8) else {
            throw SymairaOAuthError.invalidStoredToken
        }
        return try keychain.save(value, key: account)
    }

    @discardableResult
    public func delete() -> Bool {
        keychain.delete(key: account)
    }
}

public enum SymairaOAuthError: Error, LocalizedError, Sendable, Equatable {
    case invalidState
    case invalidAuthorizationCode
    case invalidStoredToken
    case randomGenerationFailed
    case invalidTokenResponse

    public var errorDescription: String? {
        switch self {
        case .invalidState:
            return "The OAuth callback state does not match the authorization request."
        case .invalidAuthorizationCode:
            return "The OAuth authorization code is missing or empty."
        case .invalidStoredToken:
            return "The stored OAuth token is invalid."
        case .randomGenerationFailed:
            return "Secure random generation failed while preparing OAuth."
        case .invalidTokenResponse:
            return "The OAuth server returned an invalid token response."
        }
    }
}

/// A reusable OAuth 2.0 authorization-code flow with PKCE and refresh support.
public struct SymairaOAuthAuthenticator: Sendable {
    public let configuration: SymairaOAuthConfiguration
    public let httpClient: any SymairaProviderHTTPClient

    public init(
        configuration: SymairaOAuthConfiguration,
        httpClient: any SymairaProviderHTTPClient = SymairaURLSessionHTTPClient()
    ) {
        self.configuration = configuration
        self.httpClient = httpClient
    }

    /// Builds the URL a host app should open in its browser or web-auth session.
    public func makeAuthorizationRequest() throws -> SymairaOAuthAuthorizationRequest {
        let state = try Self.randomBase64URL(byteCount: 32)
        let verifier = try Self.randomBase64URL(byteCount: 64)
        let challenge = Self.sha256Base64URL(verifier)
        guard var components = URLComponents(
            url: configuration.authorizationURL,
            resolvingAgainstBaseURL: false
        ) else {
            throw SymairaOAuthError.invalidState
        }
        var queryItems = components.queryItems ?? []
        queryItems += [
            URLQueryItem(name: "response_type", value: "code"),
            URLQueryItem(name: "client_id", value: configuration.clientID),
            URLQueryItem(name: "redirect_uri", value: configuration.redirectURI),
            URLQueryItem(name: "state", value: state),
            URLQueryItem(name: "code_challenge", value: challenge),
            URLQueryItem(name: "code_challenge_method", value: "S256"),
        ]
        if !configuration.scopes.isEmpty {
            queryItems.append(URLQueryItem(name: "scope", value: configuration.scopes.joined(separator: " ")))
        }
        components.queryItems = queryItems
        guard let url = components.url else { throw SymairaOAuthError.invalidState }
        return SymairaOAuthAuthorizationRequest(url: url, state: state, codeVerifier: verifier)
    }

    public func exchange(
        code: String,
        state: String,
        request: SymairaOAuthAuthorizationRequest
    ) async throws -> SymairaOAuthToken {
        guard state == request.state else { throw SymairaOAuthError.invalidState }
        guard !code.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw SymairaOAuthError.invalidAuthorizationCode
        }
        return try await requestToken([
            "grant_type": "authorization_code",
            "client_id": configuration.clientID,
            "code": code,
            "redirect_uri": configuration.redirectURI,
            "code_verifier": request.codeVerifier,
        ], fallbackRefreshToken: nil)
    }

    public func refresh(_ token: SymairaOAuthToken) async throws -> SymairaOAuthToken {
        guard let refreshToken = token.refreshToken, !refreshToken.isEmpty else {
            throw SymairaOAuthError.invalidStoredToken
        }
        return try await requestToken([
            "grant_type": "refresh_token",
            "client_id": configuration.clientID,
            "refresh_token": refreshToken,
        ], fallbackRefreshToken: refreshToken)
    }

    private func requestToken(
        _ fields: [String: String],
        fallbackRefreshToken: String?
    ) async throws -> SymairaOAuthToken {
        var request = URLRequest(url: configuration.tokenURL)
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        request.httpBody = formEncoded(fields).data(using: .utf8)

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await httpClient.data(for: request)
        } catch let error as SymairaProviderError {
            throw error
        } catch {
            throw SymairaProviderErrorMapper.transport(error)
        }
        guard let httpResponse = response as? HTTPURLResponse else {
            throw SymairaProviderErrorMapper.transport(URLError(.badServerResponse))
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            throw SymairaProviderErrorMapper.http(
                statusCode: httpResponse.statusCode,
                body: data
            )
        }

        let payload: OAuthTokenPayload
        do {
            payload = try JSONDecoder().decode(OAuthTokenPayload.self, from: data)
        } catch {
            throw SymairaOAuthError.invalidTokenResponse
        }
        let refreshToken = payload.refreshToken ?? fallbackRefreshToken
        let expiresAt = payload.expiresIn.map { Date().addingTimeInterval(TimeInterval($0)) }
        return SymairaOAuthToken(
            accessToken: payload.accessToken,
            refreshToken: refreshToken,
            tokenType: payload.tokenType ?? "Bearer",
            expiresAt: expiresAt
        )
    }

    private func formEncoded(_ fields: [String: String]) -> String {
        var components = URLComponents()
        components.queryItems = fields.keys.sorted().map { URLQueryItem(name: $0, value: fields[$0]) }
        return components.percentEncodedQuery ?? ""
    }

    private struct OAuthTokenPayload: Decodable {
        let accessToken: String
        let refreshToken: String?
        let tokenType: String?
        let expiresIn: Int?

        private enum CodingKeys: String, CodingKey {
            case accessToken = "access_token"
            case refreshToken = "refresh_token"
            case tokenType = "token_type"
            case expiresIn = "expires_in"
        }
    }

    private static func randomBase64URL(byteCount: Int) throws -> String {
        var bytes = Data(count: byteCount)
        let status = bytes.withUnsafeMutableBytes { buffer in
            SecRandomCopyBytes(kSecRandomDefault, byteCount, buffer.baseAddress!)
        }
        guard status == errSecSuccess else { throw SymairaOAuthError.randomGenerationFailed }
        return bytes.base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    private static func sha256Base64URL(_ value: String) -> String {
        let digest = SHA256.hash(data: Data(value.utf8))
        return Data(digest).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

}
