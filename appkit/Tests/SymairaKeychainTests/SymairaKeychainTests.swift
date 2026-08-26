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
/// is bound to a local `let` first and asserted on separately — that keeps
/// the throw visible to `skippingMissingEntitlement`.
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
}
