import Foundation
import SymairaKeychain

/// Compatibility name for the extracted terminal API. The implementation remains the shared keychain.
public typealias SymairaKeyStore = SymairaKeychain

/// A typed reference to a credential without carrying the credential itself.
public enum SymairaCredentialReference: Sendable, Equatable {
    case symvault(path: String)
    case keychain(service: String, account: String)
    case environment(variable: String)

    public init(rawValue: String) throws {
        guard let url = URL(string: rawValue), let scheme = url.scheme?.lowercased() else {
            throw SymairaCredentialReferenceError.invalidReference
        }

        switch scheme {
        case "symvault", "vault":
            let path = ([url.host].compactMap { $0 } + url.path
                .split(separator: "/")
                .map(String.init)).joined(separator: "/")
            guard !path.isEmpty, url.query == nil, url.fragment == nil else {
                throw SymairaCredentialReferenceError.invalidReference
            }
            self = .symvault(path: path)
        case "keychain":
            let service = url.host ?? ""
            let account = url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            guard !service.isEmpty, !account.isEmpty, url.query == nil, url.fragment == nil else {
                throw SymairaCredentialReferenceError.invalidReference
            }
            self = .keychain(service: service, account: account)
        case "env":
            let variable = url.host ?? url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            guard Self.isValidEnvironmentName(variable), url.query == nil, url.fragment == nil else {
                throw SymairaCredentialReferenceError.invalidReference
            }
            self = .environment(variable: variable)
        default:
            throw SymairaCredentialReferenceError.unsupportedScheme(scheme)
        }
    }

    public var rawValue: String {
        switch self {
        case .symvault(let path):
            return "symvault://\(path)"
        case .keychain(let service, let account):
            return "keychain://\(service)/\(account)"
        case .environment(let variable):
            return "env://\(variable)"
        }
    }

    private static func isValidEnvironmentName(_ value: String) -> Bool {
        guard !value.isEmpty else { return false }
        return value.allSatisfy { $0.isLetter || $0.isNumber || $0 == "_" }
    }
}

public enum SymairaCredentialReferenceError: Error, LocalizedError, Sendable, Equatable {
    case invalidReference
    case unsupportedScheme(String)
    case vaultResolutionUnavailable

    public var errorDescription: String? {
        switch self {
        case .invalidReference:
            return "The credential reference is invalid."
        case .unsupportedScheme(let scheme):
            return "The credential reference scheme \(scheme) is not supported."
        case .vaultResolutionUnavailable:
            return "No resolver was provided for the SymVault credential reference."
        }
    }
}

/// Resolves references lazily. Resolved secret values never appear in errors or logs.
public struct SymairaCredentialResolver: Sendable {
    private let keychain: SymairaKeychain
    private let environment: [String: String]
    private let vaultResolver: (@Sendable (String) async throws -> String?)?

    public init(
        keychain: SymairaKeychain = SymairaKeychain(app: "provider"),
        environment: [String: String] = ProcessInfo.processInfo.environment,
        vaultResolver: (@Sendable (String) async throws -> String?)? = nil
    ) {
        self.keychain = keychain
        self.environment = environment
        self.vaultResolver = vaultResolver
    }

    public func resolve(_ reference: String?) async throws -> String? {
        guard let reference, !reference.isEmpty else { return nil }
        return try await resolve(try SymairaCredentialReference(rawValue: reference))
    }

    public func resolve(_ reference: SymairaCredentialReference) async throws -> String? {
        switch reference {
        case .environment(let variable):
            return environment[variable]?.nilIfEmpty
        case .keychain(let service, let account):
            return try keychainForService(service).read(key: account)?.nilIfEmpty
        case .symvault(let path):
            guard let vaultResolver else {
                throw SymairaCredentialReferenceError.vaultResolutionUnavailable
            }
            return try await vaultResolver(path)?.nilIfEmpty
        }
    }

    private func keychainForService(_ service: String) -> SymairaKeychain {
        SymairaKeychain(service: service)
    }
}

/// Keychain-backed credential storage used by provider settings UI and hosts.
public struct SymairaProviderCredentialStore: Sendable {
    public let keychain: SymairaKeychain

    public init(keychain: SymairaKeychain = SymairaKeychain(app: "provider")) {
        self.keychain = keychain
    }

    public func credential(for providerID: String) throws -> String? {
        try keychain.read(key: account(for: providerID))
    }

    @discardableResult
    public func save(_ value: String, for providerID: String) throws -> Bool {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return keychain.delete(key: account(for: providerID))
        }
        // Verified save: read-back catches signing-identity ACL mismatches
        // on locally built unsigned apps instead of silently losing the key.
        _ = try keychain.saveVerified(trimmed, key: account(for: providerID))
        return true
    }

    @discardableResult
    public func delete(for providerID: String) -> Bool {
        keychain.delete(key: account(for: providerID))
    }

    public func reference(for providerID: String) -> String {
        "keychain://\(keychain.service)/\(account(for: providerID))"
    }

    public func account(for providerID: String) -> String {
        "\(providerID)-api-key"
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
