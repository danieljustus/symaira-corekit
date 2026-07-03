import Foundation
import Security

public enum SymairaKeychainError: Error, LocalizedError, Sendable {
    case saveFailed(OSStatus)
    case readFailed(OSStatus)

    public var errorDescription: String? {
        switch self {
        case .saveFailed(let status):
            return "Keychain save failed (OSStatus \(status))."
        case .readFailed(let status):
            return "Keychain read failed (OSStatus \(status))."
        }
    }
}

/// Keychain wrapper unifying the former memory/vibecoder helpers.
///
/// Items use `kSecAttrAccessibleAfterFirstUnlock` — appropriate for developer
/// tools that may run background work after the first unlock.
public struct SymairaKeychain: Sendable {
    public let service: String

    /// Namespaced service for a Symaira app, e.g. `SymairaKeychain(app: "symseek")`
    /// → service `dev.symaira.symseek`.
    public init(app: String) {
        self.service = "dev.symaira.\(app)"
    }

    /// Escape hatch for migrating existing items stored under legacy service
    /// names (e.g. `com.symaira.memory`).
    public init(service: String) {
        self.service = service
    }

    @discardableResult
    public func save(_ value: String, key: String) throws -> Bool {
        let data = Data(value.utf8)

        // Remove any existing item first to avoid errSecDuplicateItem.
        delete(key: key)

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
        ]

        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw SymairaKeychainError.saveFailed(status)
        }
        return true
    }

    public func read(key: String) throws -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)

        guard status == errSecSuccess, let data = item as? Data else {
            if status == errSecItemNotFound { return nil }
            throw SymairaKeychainError.readFailed(status)
        }

        return String(data: data, encoding: .utf8)
    }

    @discardableResult
    public func delete(key: String) -> Bool {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        return SecItemDelete(query as CFDictionary) == errSecSuccess
    }
}
