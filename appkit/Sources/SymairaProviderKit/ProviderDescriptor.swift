import Foundation

/// The wire dialect used by a provider endpoint.
public enum SymairaProviderDialect: String, Codable, Sendable, Equatable {
    case openai
    case anthropic
}

/// How a provider authenticates requests.
public enum SymairaProviderAuthScheme: String, Codable, Sendable, Equatable {
    case bearer
    case header
    case none
}

/// The model-list strategy declared by the shared provider contract.
public enum SymairaProviderModelsMode: String, Codable, Sendable, Equatable {
    case `static`
    case discovered
    case deployment
    case configured
}

/// Provider capabilities promised by the shared descriptor.
public struct SymairaProviderCapabilities: Codable, Sendable, Equatable {
    public let streaming: Bool
    public let toolUse: Bool
    public let embeddings: Bool
    public let vision: Bool
    public let systemPrompt: Bool

    public init(
        streaming: Bool,
        toolUse: Bool,
        embeddings: Bool,
        vision: Bool,
        systemPrompt: Bool
    ) {
        self.streaming = streaming
        self.toolUse = toolUse
        self.embeddings = embeddings
        self.vision = vision
        self.systemPrompt = systemPrompt
    }

    private enum CodingKeys: String, CodingKey {
        case streaming
        case toolUse = "tool_use"
        case embeddings
        case vision
        case systemPrompt = "system_prompt"
    }
}

/// Authentication details from `contracts/llm_providers.json`.
public struct SymairaProviderAuth: Codable, Sendable, Equatable {
    public let scheme: SymairaProviderAuthScheme
    public let header: String?
    public let configurableScheme: Bool

    public init(
        scheme: SymairaProviderAuthScheme,
        header: String? = nil,
        configurableScheme: Bool = false
    ) {
        self.scheme = scheme
        self.header = header
        self.configurableScheme = configurableScheme
    }

    private enum CodingKeys: String, CodingKey {
        case scheme
        case header
        case configurableScheme = "configurable_scheme"
    }

    private enum DecodeDefaults {
        static let configurableScheme = false
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        scheme = try container.decode(SymairaProviderAuthScheme.self, forKey: .scheme)
        header = try container.decodeIfPresent(String.self, forKey: .header)
        configurableScheme = try container.decodeIfPresent(Bool.self, forKey: .configurableScheme)
            ?? DecodeDefaults.configurableScheme
    }
}

/// Model selection and discovery metadata from the shared descriptor.
public struct SymairaProviderModelsDescriptor: Codable, Sendable, Equatable {
    public let mode: SymairaProviderModelsMode
    public let discoveryPath: String?
    public let defaultModel: String?

    public init(
        mode: SymairaProviderModelsMode,
        discoveryPath: String? = nil,
        defaultModel: String? = nil
    ) {
        self.mode = mode
        self.discoveryPath = discoveryPath
        self.defaultModel = defaultModel
    }

    private enum CodingKeys: String, CodingKey {
        case mode
        case discoveryPath = "discovery_path"
        case defaultModel = "default"
    }
}

/// One declarative provider entry shared with corekit's Go implementation.
public struct SymairaProviderDescriptor: Codable, Sendable, Equatable, Identifiable {
    public let id: String
    public let displayName: String
    public let baseURL: URL?
    public let baseURLOverridable: Bool
    public let baseURLRequiredOverride: Bool
    public let auth: SymairaProviderAuth
    public let extraHeaders: [String: String]
    public let dialect: SymairaProviderDialect
    public let dialectConfigurable: Bool
    public let capabilities: SymairaProviderCapabilities
    public let models: SymairaProviderModelsDescriptor
    public let credentialRefEnvDefault: String?

    public init(
        id: String,
        displayName: String,
        baseURL: URL?,
        baseURLOverridable: Bool = false,
        baseURLRequiredOverride: Bool = false,
        auth: SymairaProviderAuth,
        extraHeaders: [String: String] = [:],
        dialect: SymairaProviderDialect,
        dialectConfigurable: Bool = false,
        capabilities: SymairaProviderCapabilities,
        models: SymairaProviderModelsDescriptor,
        credentialRefEnvDefault: String?
    ) {
        self.id = id
        self.displayName = displayName
        self.baseURL = baseURL
        self.baseURLOverridable = baseURLOverridable
        self.baseURLRequiredOverride = baseURLRequiredOverride
        self.auth = auth
        self.extraHeaders = extraHeaders
        self.dialect = dialect
        self.dialectConfigurable = dialectConfigurable
        self.capabilities = capabilities
        self.models = models
        self.credentialRefEnvDefault = credentialRefEnvDefault
    }

    private enum CodingKeys: String, CodingKey {
        case id
        case displayName = "display_name"
        case baseURL = "base_url"
        case baseURLOverridable = "base_url_overridable"
        case baseURLRequiredOverride = "base_url_required_override"
        case auth
        case extraHeaders = "extra_headers"
        case dialect
        case dialectConfigurable = "dialect_configurable"
        case capabilities
        case models
        case credentialRefEnvDefault = "credential_ref_env_default"
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        displayName = try container.decode(String.self, forKey: .displayName)
        baseURL = try container.decodeIfPresent(URL.self, forKey: .baseURL)
        baseURLOverridable = try container.decodeIfPresent(Bool.self, forKey: .baseURLOverridable) ?? false
        baseURLRequiredOverride = try container.decodeIfPresent(Bool.self, forKey: .baseURLRequiredOverride) ?? false
        auth = try container.decode(SymairaProviderAuth.self, forKey: .auth)
        extraHeaders = try container.decodeIfPresent([String: String].self, forKey: .extraHeaders) ?? [:]
        dialect = try container.decode(SymairaProviderDialect.self, forKey: .dialect)
        dialectConfigurable = try container.decodeIfPresent(Bool.self, forKey: .dialectConfigurable) ?? false
        capabilities = try container.decode(SymairaProviderCapabilities.self, forKey: .capabilities)
        models = try container.decode(SymairaProviderModelsDescriptor.self, forKey: .models)
        credentialRefEnvDefault = try container.decodeIfPresent(String.self, forKey: .credentialRefEnvDefault)
    }
}

/// Errors raised while loading or validating the shared descriptor registry.
public enum SymairaProviderCatalogError: Error, LocalizedError, Sendable, Equatable {
    case missingResource
    case invalidData
    case unsupportedSchema(Int)
    case emptyCatalog
    case emptyProviderID
    case duplicateProviderID(String)

    public var errorDescription: String? {
        switch self {
        case .missingResource:
            return "The bundled LLM provider descriptor is missing."
        case .invalidData:
            return "The bundled LLM provider descriptor is invalid."
        case .unsupportedSchema(let version):
            return "Unsupported LLM provider descriptor schema version \(version)."
        case .emptyCatalog:
            return "The LLM provider descriptor contains no providers."
        case .emptyProviderID:
            return "An LLM provider descriptor has an empty id."
        case .duplicateProviderID(let id):
            return "The LLM provider descriptor contains duplicate id \(id)."
        }
    }
}

/// The shared descriptor registry consumed by provider UI and transport code.
public struct SymairaProviderCatalog: Sendable, Equatable {
    public let schemaVersion: Int
    public let providers: [SymairaProviderDescriptor]

    public init(schemaVersion: Int, providers: [SymairaProviderDescriptor]) throws {
        guard schemaVersion == 1 else {
            throw SymairaProviderCatalogError.unsupportedSchema(schemaVersion)
        }
        try Self.validate(providers)
        self.schemaVersion = schemaVersion
        self.providers = providers
    }

    /// The resource shipped with this SPM target. A missing resource is a packaging error.
    public static let bundled: SymairaProviderCatalog = {
        do {
            return try load()
        } catch {
            preconditionFailure("Unable to load SymairaProviderKit provider descriptors: \(error)")
        }
    }()

    /// Loads the descriptor shipped with this package.
    public static func load() throws -> SymairaProviderCatalog {
        try load(bundle: Bundle.module)
    }

    /// Loads the descriptor from a bundle, primarily useful for contract tests and hosts.
    public static func load(bundle: Bundle) throws -> SymairaProviderCatalog {
        guard let url = bundle.url(forResource: "llm_providers", withExtension: "json") else {
            throw SymairaProviderCatalogError.missingResource
        }
        do {
            return try SymairaProviderCatalog(data: Data(contentsOf: url))
        } catch let error as SymairaProviderCatalogError {
            throw error
        } catch {
            throw SymairaProviderCatalogError.invalidData
        }
    }

    /// Decodes the corekit descriptor fixture or a host-provided equivalent.
    public init(data: Data) throws {
        do {
            let resource = try JSONDecoder().decode(Resource.self, from: data)
            try self.init(schemaVersion: resource.schemaVersion, providers: resource.providers)
        } catch let error as SymairaProviderCatalogError {
            throw error
        } catch {
            throw SymairaProviderCatalogError.invalidData
        }
    }

    public func provider(id: String) -> SymairaProviderDescriptor? {
        providers.first { $0.id == id }
    }

    private static func validate(_ providers: [SymairaProviderDescriptor]) throws {
        guard !providers.isEmpty else {
            throw SymairaProviderCatalogError.emptyCatalog
        }
        var ids = Set<String>()
        for provider in providers {
            guard !provider.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                throw SymairaProviderCatalogError.emptyProviderID
            }
            guard ids.insert(provider.id).inserted else {
                throw SymairaProviderCatalogError.duplicateProviderID(provider.id)
            }
        }
    }

    private struct Resource: Decodable {
        let schemaVersion: Int
        let providers: [SymairaProviderDescriptor]

        private enum CodingKeys: String, CodingKey {
            case schemaVersion = "schema_version"
            case providers
        }
    }
}

/// A normalized model entry returned by a provider's discovery endpoint.
public struct SymairaProviderModel: Codable, Sendable, Equatable, Identifiable {
    public let id: String
    public let contextWindow: Int?

    public init(id: String, contextWindow: Int? = nil) {
        self.id = id
        self.contextWindow = contextWindow
    }

    public var displayName: String { id }

    private enum CodingKeys: String, CodingKey {
        case id
        case contextWindow = "context_window"
    }
}
