import Foundation

/// A provider configuration assembled from a descriptor and user choices.
public struct SymairaProviderConfiguration: Sendable, Equatable {
    public let descriptor: SymairaProviderDescriptor
    public let baseURLOverride: URL?
    public let credentialReference: String?
    public let authSchemeOverride: SymairaProviderAuthScheme?
    public let customAuthorizationScheme: String?
    public let dialectOverride: SymairaProviderDialect?
    public let model: String?

    public init(
        descriptor: SymairaProviderDescriptor,
        baseURLOverride: URL? = nil,
        credentialReference: String? = nil,
        authSchemeOverride: SymairaProviderAuthScheme? = nil,
        customAuthorizationScheme: String? = nil,
        dialectOverride: SymairaProviderDialect? = nil,
        model: String? = nil
    ) {
        self.descriptor = descriptor
        self.baseURLOverride = baseURLOverride
        self.credentialReference = credentialReference
        self.authSchemeOverride = authSchemeOverride
        self.customAuthorizationScheme = customAuthorizationScheme
        self.dialectOverride = dialectOverride
        self.model = model
    }

    public var effectiveDialect: SymairaProviderDialect {
        dialectOverride ?? descriptor.dialect
    }

    public var effectiveAuthScheme: SymairaProviderAuthScheme {
        authSchemeOverride ?? descriptor.auth.scheme
    }
}

/// Normalized model metadata returned by a provider endpoint.
public struct SymairaConnectionResult: Sendable, Equatable {
    public let providerID: String
    public let endpoint: URL
    public let model: String?
    public let discoveredModelCount: Int
    public let latency: TimeInterval

    public init(
        providerID: String,
        endpoint: URL,
        model: String?,
        discoveredModelCount: Int = 0,
        latency: TimeInterval
    ) {
        self.providerID = providerID
        self.endpoint = endpoint
        self.model = model
        self.discoveredModelCount = discoveredModelCount
        self.latency = latency
    }
}

/// The HTTP seam used by the provider client. Hosts and tests can inject their own transport.
public protocol SymairaProviderHTTPClient: Sendable {
    func data(for request: URLRequest) async throws -> (Data, URLResponse)
}

/// Foundation URLSession implementation used in production.
public final class SymairaURLSessionHTTPClient: SymairaProviderHTTPClient, @unchecked Sendable {
    private let session: URLSession

    public init(session: URLSession = .shared) {
        self.session = session
    }

    public func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        try await session.data(for: request)
    }
}

/// Descriptor-driven provider connectivity and model discovery.
///
/// This is deliberately limited to provider setup concerns: it does not own
/// agent turns, usage accounting, billing or application-specific state.
public struct SymairaProviderClient: Sendable {
    public let configuration: SymairaProviderConfiguration
    public let credentialResolver: SymairaCredentialResolver
    public let httpClient: any SymairaProviderHTTPClient

    public init(
        configuration: SymairaProviderConfiguration,
        credentialResolver: SymairaCredentialResolver = SymairaCredentialResolver(),
        httpClient: any SymairaProviderHTTPClient = SymairaURLSessionHTTPClient()
    ) {
        self.configuration = configuration
        self.credentialResolver = credentialResolver
        self.httpClient = httpClient
    }

    /// Returns discovered models, or the static default as a one-item list.
    public func discoverModels() async throws -> [SymairaProviderModel] {
        switch configuration.descriptor.models.mode {
        case .static:
            guard let model = configuration.descriptor.models.defaultModel else { return [] }
            return [SymairaProviderModel(id: model)]
        case .configured, .deployment:
            return []
        case .discovered:
            let path = configuration.descriptor.models.discoveryPath ?? "/models"
            let request = try await makeRequest(method: "GET", path: path)
            let (data, response) = try await perform(request)
            do {
                if configuration.descriptor.id == "ollama" || path.contains("/api/tags") {
                    return try JSONDecoder().decode(OllamaModelsResponse.self, from: data).models.map {
                        SymairaProviderModel(id: $0.name, contextWindow: $0.contextWindow)
                    }
                }
                return try JSONDecoder().decode(OpenAIModelsResponse.self, from: data).data.map {
                    SymairaProviderModel(id: $0.id, contextWindow: $0.contextWindow)
                }
            } catch {
                throw SymairaProviderError(
                    code: .providerError,
                    message: "The provider returned an invalid model list.",
                    statusCode: (response as? HTTPURLResponse)?.statusCode
                )
            }
        }
    }

    /// Performs a credential-aware, non-generation connectivity check.
    ///
    /// The check uses a model-list endpoint where the descriptor provides one,
    /// otherwise the provider's standard `/models` endpoint. It never sends a
    /// billable chat completion merely to test credentials.
    public func testConnection() async throws -> SymairaConnectionResult {
        let started = Date()
        let mode = configuration.descriptor.models.mode
        if mode == .discovered {
            let models = try await discoverModels()
            let endpoint = try endpointURL(path: configuration.descriptor.models.discoveryPath ?? "/models")
            return SymairaConnectionResult(
                providerID: configuration.descriptor.id,
                endpoint: endpoint,
                model: configuration.model ?? models.first?.id,
                discoveredModelCount: models.count,
                latency: Date().timeIntervalSince(started)
            )
        }

        let path: String
        if configuration.descriptor.id == "anthropic" {
            path = "/v1/models"
        } else {
            path = "/models"
        }
        let request = try await makeRequest(method: "GET", path: path)
        _ = try await perform(request)
        let endpoint = try endpointURL(path: path)
        return SymairaConnectionResult(
            providerID: configuration.descriptor.id,
            endpoint: endpoint,
            model: configuration.model ?? configuration.descriptor.models.defaultModel,
            latency: Date().timeIntervalSince(started)
        )
    }

    private func makeRequest(method: String, path: String) async throws -> URLRequest {
        let url = try endpointURL(path: path)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 30

        for (name, value) in configuration.descriptor.extraHeaders {
            request.setValue(value, forHTTPHeaderField: name)
        }

        let scheme = configuration.effectiveAuthScheme
        guard scheme != .none else { return request }

        let reference = configuration.credentialReference
            ?? configuration.descriptor.credentialRefEnvDefault.map { "env://\($0)" }
        let credential = try await credentialResolver.resolve(reference)?.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let credential, !credential.isEmpty else {
            let referenceName = reference ?? "the provider credential"
            throw SymairaProviderError(
                code: .authFailure,
                message: "No credential is available for \(referenceName)."
            )
        }

        switch scheme {
        case .bearer:
            let prefix = configuration.customAuthorizationScheme?.trimmingCharacters(in: .whitespacesAndNewlines)
            request.setValue("\(prefix ?? "Bearer") \(credential)", forHTTPHeaderField: "Authorization")
        case .header:
            guard let header = configuration.descriptor.auth.header, !header.isEmpty else {
                throw SymairaProviderErrorMapper.invalidConfiguration("The provider header authentication is missing its header name.")
            }
            request.setValue(credential, forHTTPHeaderField: header)
        case .none:
            break
        }
        return request
    }

    private func perform(_ request: URLRequest) async throws -> (Data, URLResponse) {
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
            throw SymairaProviderError(
                code: .transportError,
                message: "The provider returned a response without an HTTP status."
            )
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            let headers = httpResponse.allHeaderFields.reduce(into: [String: String]()) { result, item in
                if let key = item.key as? String, let value = item.value as? String {
                    result[key] = value
                }
            }
            throw SymairaProviderErrorMapper.http(
                statusCode: httpResponse.statusCode,
                headers: headers,
                body: data
            )
        }
        return (data, response)
    }

    private func endpointURL(path: String) throws -> URL {
        guard let base = configuration.baseURLOverride ?? configuration.descriptor.baseURL else {
            throw SymairaProviderErrorMapper.invalidConfiguration(
                "Provider \(configuration.descriptor.displayName) requires a base URL override."
            )
        }
        guard let scheme = base.scheme?.lowercased(), scheme == "http" || scheme == "https" else {
            throw SymairaProviderErrorMapper.invalidConfiguration("The provider base URL must use http or https.")
        }
        guard !configuration.descriptor.baseURLRequiredOverride || configuration.baseURLOverride != nil else {
            throw SymairaProviderErrorMapper.invalidConfiguration(
                "Provider \(configuration.descriptor.displayName) requires a base URL override."
            )
        }
        guard configuration.baseURLOverride == nil
            || configuration.descriptor.baseURLOverridable
            || configuration.descriptor.baseURLRequiredOverride else {
            throw SymairaProviderErrorMapper.invalidConfiguration(
                "Provider \(configuration.descriptor.displayName) does not allow a base URL override."
            )
        }

        guard !path.isEmpty else { return base }
        guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else {
            throw SymairaProviderErrorMapper.invalidConfiguration("The provider base URL is invalid.")
        }

        let cleanPath = path.hasPrefix("/") ? path : "/\(path)"
        let basePath = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        // Ollama's discovery endpoint lives beside `/v1`, not below it.
        if cleanPath.hasPrefix("/api/") && basePath.hasSuffix("v1") {
            components.path = cleanPath
        } else {
            components.path = "/" + [basePath, cleanPath.trimmingCharacters(in: CharacterSet(charactersIn: "/"))]
                .filter { !$0.isEmpty }
                .joined(separator: "/")
        }
        guard let url = components.url else {
            throw SymairaProviderErrorMapper.invalidConfiguration("The provider endpoint URL is invalid.")
        }
        return url
    }

    private struct OpenAIModelsResponse: Decodable {
        let data: [OpenAIModel]
    }

    private struct OpenAIModel: Decodable {
        let id: String
        let contextWindow: Int?

        private enum CodingKeys: String, CodingKey {
            case id
            case contextWindow = "context_window"
        }
    }

    private struct OllamaModelsResponse: Decodable {
        let models: [OllamaModel]
    }

    private struct OllamaModel: Decodable {
        let name: String
        let contextWindow: Int?

        private enum CodingKeys: String, CodingKey {
            case name
            case contextWindow = "context_window"
        }
    }
}
