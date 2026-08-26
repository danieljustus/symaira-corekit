import Foundation
import Security

public enum SymairaKeychainError: Error, LocalizedError, Sendable {
    case saveFailed(OSStatus)
    case readFailed(OSStatus)
    /// The write succeeded at the SecItem level but the read-back did not
    /// return the stored value — the item may not be retrievable by this
    /// binary (signing-identity ACL mismatch on locally built apps).
    case verificationFailed

    public var errorDescription: String? {
        switch self {
        case .saveFailed(let status):
            return "Keychain save failed (OSStatus \(status))."
        case .readFailed(let status):
            return "Keychain read failed (OSStatus \(status))."
        case .verificationFailed:
            return "Keychain save succeeded but read-back failed — the credential may not be retrievable."
        }
    }
}

/// How strongly a stored item is bound to the device's local authentication state.
public enum SymairaKeychainAccessControl: Sendable, Equatable {
    /// No access control; item is readable once the device has been unlocked
    /// at least once since boot (`kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`).
    case none

    /// Requires the device passcode before the item can be read
    /// (`.devicePasscode`). Survives biometric enrollment changes.
    case devicePasscode

    /// Requires the currently enrolled biometrics (Touch ID / Face ID) before
    /// the item can be read (`.biometryCurrentSet`). Unlike `.devicePasscode`,
    /// this invalidates the item the moment the user adds, removes, or
    /// re-enrolls a fingerprint or face — appropriate for a credential
    /// manager that wants a stale enrollment to lock a secret out rather than
    /// silently keep accepting it.
    case biometryCurrentSet

    /// The `SecAccessControlCreateFlags` for this policy, or `nil` for `.none`
    /// (which uses a plain `kSecAttrAccessible` attribute instead).
    var secAccessControlFlags: SecAccessControlCreateFlags? {
        switch self {
        case .none:
            return nil
        case .devicePasscode:
            return .devicePasscode
        case .biometryCurrentSet:
            return .biometryCurrentSet
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
        try save(value, key: key, requireUserPresence: false)
    }

    /// Saves a value to the keychain, optionally requiring user presence before
    /// the stored item can be read.
    ///
    /// When `requireUserPresence` is `true`, the item is protected by an access
    /// control created with `SecAccessControlCreateWithFlags` using
    /// `kSecAccessControlDevicePasscode`. Such items prompt for authentication
    /// (e.g. the device passcode) before their data can be read — intended for
    /// high-value secrets. In that case the query carries a `kSecAttrAccessControl`
    /// object instead of `kSecAttrAccessible`.
    ///
    /// The default (`requireUserPresence: false`) keeps the historical behavior:
    /// items are stored with `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`.
    ///
    /// - Parameters:
    ///   - value: The string value to store.
    ///   - key: The account name under which the value is stored.
    ///   - requireUserPresence: When `true`, the stored item carries an access
    ///     control requiring the device passcode before the secret can be read.
    /// - Returns: `true` when the item was saved successfully.
    /// - Throws: `SymairaKeychainError.saveFailed` if the keychain rejects the
    ///   write or the access control cannot be created.
    @discardableResult
    public func save(_ value: String, key: String, requireUserPresence: Bool) throws -> Bool {
        try save(value, key: key, accessControl: requireUserPresence ? .devicePasscode : .none)
    }

    /// Saves a value to the keychain under the given access control.
    ///
    /// See `SymairaKeychainAccessControl` for what each case requires before
    /// the item can be read back. `.devicePasscode` and `.biometryCurrentSet`
    /// both carry a `kSecAttrAccessControl` object instead of a plain
    /// `kSecAttrAccessible` attribute; adding such an item never prompts the
    /// user (only a subsequent `read(key:)` does).
    ///
    /// - Parameters:
    ///   - value: The string value to store.
    ///   - key: The account name under which the value is stored.
    ///   - accessControl: The authentication requirement gating a future read.
    /// - Returns: `true` when the item was saved successfully.
    /// - Throws: `SymairaKeychainError.saveFailed` if the keychain rejects the
    ///   write or the access control cannot be created.
    @discardableResult
    public func save(_ value: String, key: String, accessControl: SymairaKeychainAccessControl) throws -> Bool {
        let data = Data(value.utf8)

        // Remove any existing item first to avoid errSecDuplicateItem.
        delete(key: key)

        var query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
            kSecUseDataProtectionKeychain as String: true,
            kSecAttrSynchronizable as String: false,
        ]

        if let flags = accessControl.secAccessControlFlags {
            var accessError: Unmanaged<CFError>?
            guard let control = SecAccessControlCreateWithFlags(
                nil,
                kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
                flags,
                &accessError
            ) else {
                let status = accessError.map { OSStatus(CFErrorGetCode($0.takeRetainedValue())) } ?? errSecParam
                throw SymairaKeychainError.saveFailed(status)
            }
            query[kSecAttrAccessControl as String] = control
        } else {
            query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        }

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

    /// Bounded keychain read for headless contexts.
    ///
    /// `SecItemCopyMatching` can block indefinitely on a securityd
    /// round-trip when there is no GUI session to service it — headless
    /// automation, a locked screen, or an SSH session (observed: 0% CPU,
    /// stuck in `mach_msg`). Callers that read credentials during catalog
    /// builds or CLI startup (where a hang is worse than "no credential")
    /// must use this bounded variant.
    ///
    /// - Returns: the stored value, `nil` when absent **or** when the
    ///   keychain did not answer within `timeout` seconds.
    public func read(key: String, timeout: TimeInterval) throws -> String? {
        let lock = NSLock()
        var storedResult: Result<String?, Error>?
        let semaphore = DispatchSemaphore(value: 0)

        DispatchQueue.global(qos: .userInitiated).async {
            let result = Result { try self.read(key: key) }
            lock.lock(); storedResult = result; lock.unlock()
            semaphore.signal()
        }

        guard semaphore.wait(timeout: .now() + timeout) == .success else {
            return nil
        }
        lock.lock()
        defer { lock.unlock() }
        return try storedResult?.get()
    }

    /// Saves a value and verifies the write with a read-back (issue #358
    /// pattern): a successful `SecItemAdd` does NOT guarantee the item is
    /// retrievable by this binary — on locally built unsigned apps the ACL
    /// can be bound to a signing identity that does not match on the next
    /// build. Verified saves surface that failure immediately instead of
    /// silently returning to an empty field.
    ///
    /// - Throws: `SymairaKeychainError.saveFailed` when the write **or the
    ///   read-back** fails.
    @discardableResult
    public func saveVerified(_ value: String, key: String) throws -> Bool {
        try save(value, key: key)
        let readBack = try read(key: key)
        guard readBack == value else {
            throw SymairaKeychainError.verificationFailed
        }
        return true
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
