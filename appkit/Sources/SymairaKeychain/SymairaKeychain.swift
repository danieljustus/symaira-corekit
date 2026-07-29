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
/// Items are stored in the **data-protection keychain** with
/// `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` and iCloud sync
/// disabled. On first read, existing legacy items (stored without these
/// attributes) are migrated automatically to the hardened storage.
///
/// - Important: Items are **device-only** and do not synchronize via iCloud.
///   Consuming apps must not rely on cross-device keychain availability.
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
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
            kSecUseDataProtectionKeychain as String: true,
            kSecAttrSynchronizable as String: false,
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
            kSecUseDataProtectionKeychain as String: true,
            kSecAttrSynchronizable as String: false,
        ]

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)

        guard status == errSecSuccess, let data = item as? Data else {
            if status == errSecItemNotFound {
                // One-shot fallback: try legacy query and migrate on hit.
                return try legacyReadAndMigrate(key: key)
            }
            throw SymairaKeychainError.readFailed(status)
        }

        return String(data: data, encoding: .utf8)
    }

    /// One-shot legacy read with automatic migration to the hardened keychain.
    private func legacyReadAndMigrate(key: String) throws -> String? {
        let legacyQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]

        var legacyItem: CFTypeRef?
        let legacyStatus = SecItemCopyMatching(legacyQuery as CFDictionary, &legacyItem)

        guard legacyStatus == errSecSuccess, let legacyData = legacyItem as? Data else {
            if legacyStatus == errSecItemNotFound { return nil }
            throw SymairaKeychainError.readFailed(legacyStatus)
        }

        guard let value = String(data: legacyData, encoding: .utf8) else {
            return nil
        }

        // Migrate: re-save under the hardened attributes.
        try save(value, key: key)

        // Clean up the legacy item.
        SecItemDelete(legacyQuery as CFDictionary)

        return value
    }

    @discardableResult
    public func delete(key: String) -> Bool {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecUseDataProtectionKeychain as String: true,
            kSecAttrSynchronizable as String: false,
        ]
        return SecItemDelete(query as CFDictionary) == errSecSuccess
    }
}
