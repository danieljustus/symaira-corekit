import Foundation

/// A workspace-safe provider selection. It contains references, never secret values.
public struct SymairaWorkspaceConfig: Codable, Equatable, Sendable {
    public var providerID: String
    public var baseURLOverride: URL?
    public var model: String?
    public var credentialReference: String?

    public init(
        providerID: String,
        baseURLOverride: URL? = nil,
        model: String? = nil,
        credentialReference: String? = nil
    ) {
        self.providerID = providerID
        self.baseURLOverride = baseURLOverride
        self.model = model
        self.credentialReference = credentialReference
    }

    /// Converts persisted workspace state into a validated runtime configuration.
    public func providerConfiguration(
        in catalog: SymairaProviderCatalog = .bundled
    ) throws -> SymairaProviderConfiguration {
        guard let descriptor = catalog.provider(id: providerID) else {
            throw SymairaProviderErrorMapper.invalidConfiguration("The selected provider is not in the shared catalog.")
        }
        return SymairaProviderConfiguration(
            descriptor: descriptor,
            baseURLOverride: baseURLOverride,
            credentialReference: credentialReference,
            model: model
        )
    }
}

/// An in-memory credential value paired with its non-secret provider reference.
/// Persist references, not this value.
public struct SymairaProviderCredential: Equatable, Sendable {
    public let providerID: String
    public let value: String?
    public let reference: String?

    public init(providerID: String, value: String?, reference: String? = nil) {
        self.providerID = providerID
        self.value = value
        self.reference = reference
    }

    public var isConfigured: Bool {
        guard let value else { return false }
        return !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}

/// The provider store used by SwiftUI hosts and non-view settings flows.
@MainActor
public final class SymairaProviderStore {
    public let catalog: SymairaProviderCatalog
    public let credentialStore: SymairaProviderCredentialStore

    private let credentialResolver: SymairaCredentialResolver
    private let httpClient: any SymairaProviderHTTPClient

    public private(set) var providerID: String
    public var baseURLText: String
    public var model: String
    public private(set) var discoveredModels: [SymairaProviderModel] = []
    public private(set) var connectionState: SymairaConnectionState = .idle

    public init(
        providerID: String? = nil,
        catalog: SymairaProviderCatalog = .bundled,
        credentialStore: SymairaProviderCredentialStore = .init(),
        credentialResolver: SymairaCredentialResolver = .init(),
        httpClient: any SymairaProviderHTTPClient = SymairaURLSessionHTTPClient()
    ) {
        self.catalog = catalog
        self.credentialStore = credentialStore
        self.credentialResolver = credentialResolver
        self.httpClient = httpClient
        let initialID = providerID.flatMap { catalog.provider(id: $0)?.id } ?? catalog.providers[0].id
        let descriptor = catalog.provider(id: initialID) ?? catalog.providers[0]
        self.providerID = descriptor.id
        self.baseURLText = descriptor.baseURL?.absoluteString ?? ""
        self.model = descriptor.models.defaultModel ?? ""
    }

    public var descriptor: SymairaProviderDescriptor {
        catalog.provider(id: providerID) ?? catalog.providers[0]
    }

    public func selectProvider(id: String) {
        guard let next = catalog.provider(id: id) else { return }
        providerID = next.id
        baseURLText = next.baseURL?.absoluteString ?? ""
        model = next.models.defaultModel ?? ""
        discoveredModels = []
        connectionState = .idle
    }

    public func credential() throws -> SymairaProviderCredential {
        let reference = credentialStore.reference(for: providerID)
        return SymairaProviderCredential(
            providerID: providerID,
            value: try credentialStore.credential(for: providerID),
            reference: reference
        )
    }

    public func saveCredential(_ value: String) throws {
        try credentialStore.save(value, for: providerID)
    }

    public func workspaceConfig() -> SymairaWorkspaceConfig {
        let trimmedBaseURL = baseURLText.trimmingCharacters(in: .whitespacesAndNewlines)
        let enteredBaseURL = trimmedBaseURL.isEmpty ? nil : URL(string: trimmedBaseURL)
        let baseURLOverride = enteredBaseURL?.absoluteString == descriptor.baseURL?.absoluteString
            ? nil
            : enteredBaseURL
        return SymairaWorkspaceConfig(
            providerID: providerID,
            baseURLOverride: baseURLOverride,
            model: model.isEmpty ? nil : model,
            credentialReference: (try? credentialStore.credential(for: providerID)) != nil
                ? credentialStore.reference(for: providerID)
                : nil
        )
    }

    public func refreshModels() async throws -> [SymairaProviderModel] {
        let client = try makeClient()
        let models = try await client.discoverModels()
        discoveredModels = models
        if model.isEmpty, let first = models.first {
            model = first.id
        }
        return models
    }

    public func testConnection() async throws -> SymairaConnectionResult {
        connectionState = .testing
        do {
            let result = try await client().testConnection()
            connectionState = .connected(result)
            return result
        } catch {
            let providerError = (error as? SymairaProviderError)
                ?? SymairaProviderErrorMapper.transport(error)
            connectionState = .failed(providerError.localizedDescription)
            throw providerError
        }
    }

    private func client() throws -> SymairaProviderClient {
        try SymairaProviderClient(
            configuration: makeConfiguration(),
            credentialResolver: credentialResolver,
            httpClient: httpClient
        )
    }

    private func makeClient() throws -> SymairaProviderClient {
        try client()
    }

    private func makeConfiguration() throws -> SymairaProviderConfiguration {
        let trimmedBaseURL = baseURLText.trimmingCharacters(in: .whitespacesAndNewlines)
        let baseURLOverride: URL?
        if trimmedBaseURL.isEmpty {
            baseURLOverride = nil
        } else if let url = URL(string: trimmedBaseURL), ["http", "https"].contains(url.scheme?.lowercased()) {
            baseURLOverride = url
        } else {
            throw SymairaProviderErrorMapper.invalidConfiguration("The provider endpoint is not a valid HTTP or HTTPS URL.")
        }
        let storedCredential = try? credentialStore.credential(for: providerID)
        return SymairaProviderConfiguration(
            descriptor: descriptor,
            baseURLOverride: baseURLOverride == descriptor.baseURL ? nil : baseURLOverride,
            credentialReference: storedCredential != nil ? credentialStore.reference(for: providerID) : nil,
            model: model.isEmpty ? nil : model
        )
    }
}

public enum SymairaConnectionState: Equatable, Sendable {
    case idle
    case testing
    case connected(SymairaConnectionResult)
    case failed(String)
}
