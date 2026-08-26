import Foundation
import Security
import SymairaKeychain

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
        let digest = sha256(Array(value.utf8))
        return Data(digest).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    // Small dependency-free SHA-256 implementation for PKCE S256.
    private static func sha256(_ input: [UInt8]) -> [UInt8] {
        let constants: [UInt32] = [
            0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
            0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
            0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
            0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
            0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
            0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
            0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
            0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
        ]
        var message = input
        message.append(0x80)
        while message.count % 64 != 56 { message.append(0) }
        let bitLength = UInt64(input.count) * 8
        message.append(contentsOf: (0..<8).reversed().map { UInt8((bitLength >> UInt64($0 * 8)) & 0xff) })

        var hash: [UInt32] = [
            0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
            0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
        ]
        for chunk in stride(from: 0, to: message.count, by: 64) {
            var words = [UInt32](repeating: 0, count: 64)
            for index in 0..<16 {
                let offset = chunk + index * 4
                words[index] = UInt32(message[offset]) << 24
                    | UInt32(message[offset + 1]) << 16
                    | UInt32(message[offset + 2]) << 8
                    | UInt32(message[offset + 3])
            }
            for index in 16..<64 {
                let value = words[index - 15]
                let s0 = value.rotateRight(7) ^ value.rotateRight(18) ^ (value >> 3)
                let previous = words[index - 2]
                let s1 = previous.rotateRight(17) ^ previous.rotateRight(19) ^ (previous >> 10)
                words[index] = words[index - 16] &+ s0 &+ words[index - 7] &+ s1
            }

            var a = hash[0], b = hash[1], c = hash[2], d = hash[3]
            var e = hash[4], f = hash[5], g = hash[6], h = hash[7]
            for index in 0..<64 {
                let sum1 = e.rotateRight(6) ^ e.rotateRight(11) ^ e.rotateRight(25)
                let choose = (e & f) ^ ((~e) & g)
                let temp1 = h &+ sum1 &+ choose &+ constants[index] &+ words[index]
                let sum0 = a.rotateRight(2) ^ a.rotateRight(13) ^ a.rotateRight(22)
                let majority = (a & b) ^ (a & c) ^ (b & c)
                let temp2 = sum0 &+ majority
                h = g; g = f; f = e; e = d &+ temp1
                d = c; c = b; b = a; a = temp1 &+ temp2
            }
            hash[0] &+= a; hash[1] &+= b; hash[2] &+= c; hash[3] &+= d
            hash[4] &+= e; hash[5] &+= f; hash[6] &+= g; hash[7] &+= h
        }

        return hash.flatMap { value in
            [
                UInt8(truncatingIfNeeded: value >> 24),
                UInt8(truncatingIfNeeded: value >> 16),
                UInt8(truncatingIfNeeded: value >> 8),
                UInt8(truncatingIfNeeded: value),
            ]
        }
    }
}

private extension UInt32 {
    func rotateRight(_ amount: UInt32) -> UInt32 {
        (self >> amount) | (self << (32 - amount))
    }
}
