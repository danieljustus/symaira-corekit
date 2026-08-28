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

/// Internal seam for deterministic failure-path tests. The system implementation
/// below is the only production implementation; all security operations still
/// go through this interface so tests do not need an entitled keychain.
protocol _SymairaKeychainBackend: Sendable {
    func copyMatching(_ query: [String: Any]) -> (OSStatus, Any?)
    func add(_ query: [String: Any]) -> OSStatus
    func update(_ query: [String: Any], attributes: [String: Any]) -> OSStatus
    func delete(_ query: [String: Any]) -> OSStatus
}

private final class SystemSymairaKeychainBackend: _SymairaKeychainBackend, @unchecked Sendable {
    func copyMatching(_ query: [String: Any]) -> (OSStatus, Any?) {
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        return (status, item)
    }

    func add(_ query: [String: Any]) -> OSStatus {
        SecItemAdd(query as CFDictionary, nil)
    }

    func update(_ query: [String: Any], attributes: [String: Any]) -> OSStatus {
        SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
    }

    func delete(_ query: [String: Any]) -> OSStatus {
        SecItemDelete(query as CFDictionary)
    }
}

private final class ReadResultBox: @unchecked Sendable {
    let lock = NSLock()
    var value: Result<String?, Error>?
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
    private let backend: any _SymairaKeychainBackend

    /// A single serial queue bounds the number of potentially wedged
    /// `securityd` workers to one for the whole process. A timed-out operation
    /// cannot be cancelled, so a concurrent queue would strand one worker per
    /// caller forever.
    private static let boundedReadQueue = DispatchQueue(
        label: "dev.symaira.keychain.bounded-read",
        qos: .userInitiated
    )

    /// Namespaced service for a Symaira app, e.g. `SymairaKeychain(app: "symseek")`
    /// → service `dev.symaira.symseek`.
    public init(app: String) {
        self.init(service: "dev.symaira.\(app)")
    }

    /// Escape hatch for migrating existing items stored under legacy service
    /// names (e.g. `com.symaira.memory`).
    public init(service: String) {
        self.service = service
        self.backend = SystemSymairaKeychainBackend()
    }

    /// Internal initializer used by entitlement-independent tests.
    init(service: String, backend: any _SymairaKeychainBackend) {
        self.service = service
        self.backend = backend
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
    /// high-value secrets. In that case the query carries a
    /// `kSecAttrAccessControl` object instead of `kSecAttrAccessible`.
    ///
    /// The default (`requireUserPresence: false`) keeps the historical behavior:
    /// items are stored with `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`.
    @discardableResult
    public func save(_ value: String, key: String, requireUserPresence: Bool) throws -> Bool {
        try save(value, key: key, accessControl: requireUserPresence ? .devicePasscode : .none)
    }

    /// Saves a value to the keychain under the given access control.
    ///
    /// An existing item with the same access-control policy is updated in
    /// place, so a failed update cannot erase the previous value. Changing the
    /// policy requires replacing the item; in that case the old item is read
    /// first and restored if the replacement add fails.
    @discardableResult
    public func save(_ value: String, key: String, accessControl: SymairaKeychainAccessControl) throws -> Bool {
        let material = try makeSaveMaterial(value: value, accessControl: accessControl)
        let identityQuery = baseQuery(key: key)
        guard let existing = try existingItem(key: key) else {
            let addStatus = backend.add(material.addQuery(key: key, service: service))
            guard addStatus == errSecSuccess else {
                throw SymairaKeychainError.saveFailed(addStatus)
            }
            return true
        }

        if accessControlChanged(existingAttributes: existing.attributes, requested: material.accessControl) {
            try replaceExistingItem(
                key: key,
                oldData: existing.data,
                oldAttributes: existing.attributes,
                material: material
            )
        } else {
            let updateStatus = backend.update(
                identityQuery,
                attributes: [kSecValueData as String: material.data]
            )
            guard updateStatus == errSecSuccess else {
                _ = backend.update(
                    identityQuery,
                    attributes: [kSecValueData as String: existing.data]
                )
                throw SymairaKeychainError.saveFailed(updateStatus)
            }
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

        let (status, item) = backend.copyMatching(query)
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
        let box = ReadResultBox()
        let semaphore = DispatchSemaphore(value: 0)

        Self.boundedReadQueue.async {
            let result = Result { try self.read(key: key) }
            box.lock.lock()
            box.value = result
            box.lock.unlock()
            semaphore.signal()
        }

        guard semaphore.wait(timeout: .now() + timeout) == .success else {
            return nil
        }
        box.lock.lock()
        defer { box.lock.unlock() }
        return try box.value?.get()
    }

    /// Saves a value and verifies the write with a bounded read-back. A
    /// successful `SecItemAdd` does not guarantee that this binary can read
    /// the item back (for example, an ACL can be bound to another signing
    /// identity), so verification surfaces that failure immediately.
    ///
    /// - Parameter timeout: Maximum number of seconds to wait for the read-back.
    /// - Throws: `SymairaKeychainError.verificationFailed` when the read-back
    ///   returns a different value, no value, or times out.
    @discardableResult
    public func saveVerified(
        _ value: String,
        key: String,
        timeout: TimeInterval = 5
    ) throws -> Bool {
        let previous = try existingItem(key: key)
        try save(value, key: key)

        do {
            let readBack = try read(key: key, timeout: timeout)
            guard readBack == value else {
                throw SymairaKeychainError.verificationFailed
            }
        } catch {
            restoreAfterFailedVerification(key: key, previous: previous)
            throw error
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

        let (legacyStatus, legacyItem) = backend.copyMatching(legacyQuery)
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
        _ = backend.delete(legacyQuery)

        return value
    }

    @discardableResult
    public func delete(key: String) -> Bool {
        backend.delete(baseQuery(key: key)) == errSecSuccess
    }

    private struct SaveMaterial {
        let data: Data
        let accessControl: SecAccessControl?

        func addQuery(key: String, service: String) -> [String: Any] {
            var query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service,
                kSecAttrAccount as String: key,
                kSecValueData as String: data,
                kSecUseDataProtectionKeychain as String: true,
                kSecAttrSynchronizable as String: false,
            ]
            if let accessControl {
                query[kSecAttrAccessControl as String] = accessControl
            } else {
                query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            }
            return query
        }
    }

    private func makeSaveMaterial(
        value: String,
        accessControl: SymairaKeychainAccessControl
    ) throws -> SaveMaterial {
        if let flags = accessControl.secAccessControlFlags {
            var accessError: Unmanaged<CFError>?
            guard let control = SecAccessControlCreateWithFlags(
                nil,
                kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
                flags,
                &accessError
            ) else {
                let status = accessError.map {
                    OSStatus(CFErrorGetCode($0.takeRetainedValue()))
                } ?? errSecParam
                throw SymairaKeychainError.saveFailed(status)
            }
            return SaveMaterial(data: Data(value.utf8), accessControl: control)
        }
        return SaveMaterial(data: Data(value.utf8), accessControl: nil)
    }

    private func baseQuery(key: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecUseDataProtectionKeychain as String: true,
            kSecAttrSynchronizable as String: false,
        ]
    }

    private struct ExistingItem {
        let data: Data
        let attributes: [String: Any]
    }

    private func existingItem(key: String) throws -> ExistingItem? {
        var query = baseQuery(key: key)
        query[kSecReturnAttributes as String] = true
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        let (status, item) = backend.copyMatching(query)
        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess,
              let attributes = item as? [String: Any],
              let data = attributes[kSecValueData as String] as? Data else {
            throw SymairaKeychainError.saveFailed(status)
        }
        return ExistingItem(data: data, attributes: attributes)
    }

    private func accessControlChanged(
        existingAttributes: [String: Any],
        requested: SecAccessControl?
    ) -> Bool {
        let existing = existingAttributes[kSecAttrAccessControl as String]
        guard let requested else {
            return existing != nil
        }
        let existingObject = existing as AnyObject
        guard CFGetTypeID(existingObject) == SecAccessControlGetTypeID() else {
            return true
        }
        return !CFEqual(existingObject, requested)
    }

    private func restoreAfterFailedVerification(
        key: String,
        previous: ExistingItem?
    ) {
        guard let previous else {
            _ = backend.delete(baseQuery(key: key))
            return
        }

        if previous.attributes[kSecAttrAccessControl as String] != nil {
            _ = backend.delete(baseQuery(key: key))
            _ = backend.add(restorationQuery(key: key, data: previous.data, attributes: previous.attributes))
        } else {
            _ = backend.update(
                baseQuery(key: key),
                attributes: [kSecValueData as String: previous.data]
            )
        }
    }

    private func replaceExistingItem(
        key: String,
        oldData: Data,
        oldAttributes: [String: Any],
        material: SaveMaterial
    ) throws {
        let identityQuery = baseQuery(key: key)
        let deleteStatus = backend.delete(identityQuery)
        guard deleteStatus == errSecSuccess else {
            throw SymairaKeychainError.saveFailed(deleteStatus)
        }

        let addStatus = backend.add(material.addQuery(key: key, service: service))
        guard addStatus == errSecSuccess else {
            // The previous value is restored best-effort before reporting the
            // failed save. This keeps a failed policy change non-destructive.
            _ = backend.add(restorationQuery(key: key, data: oldData, attributes: oldAttributes))
            throw SymairaKeychainError.saveFailed(addStatus)
        }
    }

    private func restorationQuery(
        key: String,
        data: Data,
        attributes: [String: Any]
    ) -> [String: Any] {
        var query = baseQuery(key: key)
        query[kSecValueData as String] = data
        if let accessControl = attributes[kSecAttrAccessControl as String] {
            query[kSecAttrAccessControl as String] = accessControl
        } else if let accessible = attributes[kSecAttrAccessible as String] {
            query[kSecAttrAccessible as String] = accessible
        }
        return query
    }
}
