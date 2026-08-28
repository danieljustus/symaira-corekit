import Foundation
import Security
import XCTest
@testable import SymairaKeychain

/// The data-protection keychain (`kSecUseDataProtectionKeychain: true`, used
/// throughout `SymairaKeychain`) requires a `keychain-access-groups`
/// entitlement. An ad-hoc `swift test` binary does not carry one, so every
/// actual keychain operation here fails with `errSecMissingEntitlement`
/// (-34018) — this is true for the pre-existing save/read/delete API too,
/// which is why no test target existed for this module before. Signed app
/// test targets (the real Symaira clients) do carry the entitlement and
/// exercise these paths for real; here we skip rather than fail so CI on an
/// unsigned runner stays green without lying about what it verified.
///
/// Note: `XCTAssertTrue(try expr())` swallows a thrown error into a regular
/// assertion failure rather than propagating it, so every throwing call below
/// is bound to a local `let` first and asserted on separately — that keeps the
/// throw visible to `skippingMissingEntitlement`.
final class SymairaKeychainTests: XCTestCase {
    private func makeKeychain(_ testName: String = #function) -> SymairaKeychain {
        // Namespaced per test to avoid collisions if tests run concurrently.
        SymairaKeychain(app: "symairakeychain-tests-\(testName)")
    }

    private func skippingMissingEntitlement(_ body: () throws -> Void) throws {
        do {
            try body()
        } catch SymairaKeychainError.saveFailed(errSecMissingEntitlement),
                SymairaKeychainError.readFailed(errSecMissingEntitlement) {
            throw XCTSkip(
                "Data-protection keychain entitlement unavailable in this test environment (errSecMissingEntitlement); requires a signed app/test target with keychain-access-groups."
            )
        }
    }

    func testSaveReadDeleteRoundTripWithoutAccessControl() throws {
        let kc = makeKeychain()
        defer { kc.delete(key: "token") }

        try skippingMissingEntitlement {
            let saved = try kc.save("s3cr3t", key: "token")
            XCTAssertTrue(saved)
            let read = try kc.read(key: "token")
            XCTAssertEqual(read, "s3cr3t")
            XCTAssertTrue(kc.delete(key: "token"))
            let afterDelete = try kc.read(key: "token")
            XCTAssertNil(afterDelete)
        }
    }

    func testSaveOverwritesExistingItem() throws {
        let kc = makeKeychain()
        defer { kc.delete(key: "token") }

        try skippingMissingEntitlement {
            try kc.save("first", key: "token")
            try kc.save("second", key: "token")
            let read = try kc.read(key: "token")
            XCTAssertEqual(read, "second")
        }
    }

    /// Adding an access-control-gated item never prompts for authentication —
    /// only a subsequent read does — so this would be safe to run unattended
    /// in CI if the entitlement were present.
    func testSaveWithDevicePasscodeAccessControlDoesNotThrow() throws {
        let kc = makeKeychain()
        defer { kc.delete(key: "guarded") }

        try skippingMissingEntitlement {
            let saved = try kc.save("guarded-value", key: "guarded", accessControl: .devicePasscode)
            XCTAssertTrue(saved)
        }
    }

    /// Same rationale as above: `.biometryCurrentSet` only gates reads.
    func testSaveWithBiometryCurrentSetAccessControlDoesNotThrow() throws {
        let kc = makeKeychain()
        defer { kc.delete(key: "biometric") }

        try skippingMissingEntitlement {
            let saved = try kc.save("biometric-value", key: "biometric", accessControl: .biometryCurrentSet)
            XCTAssertTrue(saved)
        }
    }

    func testRequireUserPresenceTrueIsEquivalentToDevicePasscode() throws {
        let kc = makeKeychain()
        defer { kc.delete(key: "legacy-api") }

        try skippingMissingEntitlement {
            let saved = try kc.save("legacy-value", key: "legacy-api", requireUserPresence: true)
            XCTAssertTrue(saved)
        }
    }

    /// This does not touch the keychain at all — it only asserts that the
    /// two access-control policies build distinct `SecAccessControl` flag
    /// sets — so it runs unconditionally, entitlement or not.
    func testAccessControlFlagsDifferBetweenPasscodeAndBiometry() {
        XCTAssertNil(SymairaKeychainAccessControl.none.secAccessControlFlags)
        XCTAssertNotNil(SymairaKeychainAccessControl.devicePasscode.secAccessControlFlags)
        XCTAssertNotNil(SymairaKeychainAccessControl.biometryCurrentSet.secAccessControlFlags)
        XCTAssertNotEqual(
            SymairaKeychainAccessControl.devicePasscode.secAccessControlFlags,
            SymairaKeychainAccessControl.biometryCurrentSet.secAccessControlFlags
        )
    }

    // MARK: - Entitlement-independent behavior

    func testErrorDescriptionIncludesOSStatusCode() {
        XCTAssertEqual(
            SymairaKeychainError.saveFailed(errSecDuplicateItem).errorDescription,
            "Keychain save failed (OSStatus -25299)."
        )
        XCTAssertEqual(
            SymairaKeychainError.readFailed(errSecItemNotFound).errorDescription,
            "Keychain read failed (OSStatus -25300)."
        )
    }

    func testServiceNamesAreDerivedFromAppAndPreservedVerbatim() {
        XCTAssertEqual(SymairaKeychain(app: "symseek").service, "dev.symaira.symseek")
        XCTAssertEqual(
            SymairaKeychain(service: "com.symaira.memory").service,
            "com.symaira.memory",
            "the escape-hatch initializer must keep legacy service names verbatim"
        )
    }

    /// Portable contract for `read(key:)`: in an entitled environment reading
    /// an unknown key returns `nil` after the legacy-migration fallback; on an
    /// unsigned test binary the data-protection keychain rejects the query
    /// outright with `readFailed(errSecMissingEntitlement)`. Both outcomes are
    /// valid — anything else is a regression.
    func testReadOfUnknownKeySucceedsOrFailsWithMissingEntitlement() throws {
        let kc = makeKeychain()

        do {
            let value = try kc.read(key: "portable-unknown-key-probe")
            XCTAssertNil(value, "an unknown key must read back as nil when the keychain is reachable")
        } catch SymairaKeychainError.readFailed(let status) where status == errSecMissingEntitlement {
            // Unsigned test binary without keychain-access-groups: expected.
        }
    }

    /// `delete(key:)` is best-effort by design — it reports its outcome as a
    /// `Bool` instead of throwing, whatever the entitlement state reports.
    func testDeleteReportsOutcomeInsteadOfThrowing() {
        let kc = makeKeychain()
        // Must complete without throwing regardless of entitlement state;
        // the result legitimately differs between signed and unsigned runs.
        let deleted = kc.delete(key: "delete-probe-no-such-item")
        #if DEBUG_ENTITLED_KEYCHAIN
        XCTAssertTrue(deleted)
        #else
        _ = deleted
        #endif
    }

    // MARK: - Non-destructive saves

    func testExistingItemIsUpdatedWithoutDeletingIt() throws {
        let backend = InMemoryKeychainBackend(value: Data("old".utf8), attributes: [
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ])
        let kc = SymairaKeychain(service: "test", backend: backend)

        let saved = try kc.save("new", key: "token")

        XCTAssertTrue(saved)
        XCTAssertEqual(backend.value, Data("new".utf8))
        XCTAssertEqual(backend.updateCount, 1)
        XCTAssertEqual(backend.deleteCount, 0)
        XCTAssertEqual(backend.addCount, 0)
    }

    func testFailedAccessControlReplacementRestoresPreviousValue() {
        let backend = InMemoryKeychainBackend(
            value: Data("old".utf8),
            attributes: [kSecAttrAccessControl as String: "old-access-control"]
        )
        backend.failNextAdd = true
        let kc = SymairaKeychain(service: "test", backend: backend)

        do {
            _ = try kc.save("new", key: "token", accessControl: .none)
            XCTFail("expected replacement add to fail")
        } catch SymairaKeychainError.saveFailed(let status) {
            XCTAssertEqual(status, errSecIO)
        } catch {
            XCTFail("unexpected error: \(error)")
        }

        XCTAssertEqual(backend.value, Data("old".utf8))
        XCTAssertEqual(backend.deleteCount, 1)
        XCTAssertEqual(backend.addCount, 2, "failed replacement plus restoration")
    }

    // MARK: - Bounded reads

    func testBoundedReadReturnsNilWhenKeychainDoesNotAnswer() throws {
        let backend = BlockingReadBackend()
        let kc = SymairaKeychain(service: "test", backend: backend)

        let value = try kc.read(key: "token", timeout: 0.01)

        XCTAssertNil(value)
        XCTAssertEqual(backend.started.wait(timeout: .now() + 1), .success)
        backend.release.signal()
        XCTAssertEqual(backend.finished.wait(timeout: .now() + 1), .success)
    }

    func testBoundedReadsUseAtMostOneStrandedWorker() throws {
        let backend = BlockingReadBackend()
        let kc = SymairaKeychain(service: "test", backend: backend)
        let firstFinished = DispatchSemaphore(value: 0)

        DispatchQueue.global().async {
            _ = try? kc.read(key: "first", timeout: 0.01)
            firstFinished.signal()
        }

        XCTAssertEqual(backend.started.wait(timeout: .now() + 1), .success)
        let secondValue = try kc.read(key: "second", timeout: 0.01)
        XCTAssertNil(secondValue)
        XCTAssertEqual(firstFinished.wait(timeout: .now() + 1), .success)
        XCTAssertEqual(backend.maxActiveReads, 1)

        backend.release.signal()
        backend.release.signal()
        XCTAssertEqual(backend.finished.wait(timeout: .now() + 1), .success)
        XCTAssertEqual(backend.finished.wait(timeout: .now() + 1), .success)
    }

    func testSaveVerifiedFailsWhenBoundedReadTimesOut() throws {
        let backend = BlockingReadBackend()
        let kc = SymairaKeychain(service: "test", backend: backend)

        do {
            _ = try kc.saveVerified("value", key: "token", timeout: 0.01)
            XCTFail("expected verification to fail after a bounded read timeout")
        } catch SymairaKeychainError.verificationFailed {
            // Expected: the bounded read returns nil on timeout.
        }

        XCTAssertEqual(backend.started.wait(timeout: .now() + 1), .success)
        backend.release.signal()
        XCTAssertEqual(backend.finished.wait(timeout: .now() + 1), .success)
    }
}

private final class InMemoryKeychainBackend: _SymairaKeychainBackend, @unchecked Sendable {
    var value: Data?
    var attributes: [String: Any]
    var failNextAdd = false
    private(set) var addCount = 0
    private(set) var updateCount = 0
    private(set) var deleteCount = 0

    init(value: Data?, attributes: [String: Any]) {
        self.value = value
        self.attributes = attributes
    }

    func copyMatching(_ query: [String: Any]) -> (OSStatus, Any?) {
        guard let value else { return (errSecItemNotFound, nil) }
        if query[kSecReturnAttributes as String] as? Bool == true {
            var item = attributes
            item[kSecValueData as String] = value
            return (errSecSuccess, item)
        }
        return (errSecSuccess, value)
    }

    func add(_ query: [String: Any]) -> OSStatus {
        addCount += 1
        if failNextAdd {
            failNextAdd = false
            return errSecIO
        }
        value = query[kSecValueData as String] as? Data
        attributes = query.filter { key, _ in
            key != kSecValueData as String
        }
        return errSecSuccess
    }

    func update(_ query: [String: Any], attributes: [String: Any]) -> OSStatus {
        guard value != nil else { return errSecItemNotFound }
        updateCount += 1
        value = attributes[kSecValueData as String] as? Data
        return errSecSuccess
    }

    func delete(_ query: [String: Any]) -> OSStatus {
        guard value != nil else { return errSecItemNotFound }
        deleteCount += 1
        value = nil
        return errSecSuccess
    }
}

private final class BlockingReadBackend: _SymairaKeychainBackend, @unchecked Sendable {
    let started = DispatchSemaphore(value: 0)
    let release = DispatchSemaphore(value: 0)
    let finished = DispatchSemaphore(value: 0)
    private let lock = NSLock()
    private var activeReads = 0
    private(set) var maxActiveReads = 0

    func copyMatching(_ query: [String: Any]) -> (OSStatus, Any?) {
        let isBoundedRead = query[kSecUseDataProtectionKeychain as String] != nil
            && query[kSecReturnAttributes as String] == nil
        guard isBoundedRead else { return (errSecItemNotFound, nil) }

        lock.lock()
        activeReads += 1
        maxActiveReads = max(maxActiveReads, activeReads)
        lock.unlock()
        started.signal()
        release.wait()
        lock.lock()
        activeReads -= 1
        lock.unlock()
        finished.signal()
        return (errSecItemNotFound, nil)
    }

    func add(_ query: [String: Any]) -> OSStatus {
        errSecSuccess
    }

    func update(_ query: [String: Any], attributes: [String: Any]) -> OSStatus {
        errSecSuccess
    }

    func delete(_ query: [String: Any]) -> OSStatus {
        errSecSuccess
    }
}
