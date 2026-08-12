import XCTest
@testable import SymairaUpdateCheck

final class AutoUpdatePreferenceStoreTests: XCTestCase {
    private var suitesToCleanUp: [(UserDefaults, String)] = []

    override func tearDown() {
        for (defaults, suiteName) in suitesToCleanUp {
            defaults.removePersistentDomain(forName: suiteName)
        }
        suitesToCleanUp = []
        super.tearDown()
    }

    /// Creates an isolated `UserDefaults` suite for a single test and
    /// removes its persistent domain when the test finishes.
    private func makeDefaults() -> UserDefaults {
        let suiteName = "appkit-autoprefs-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        suitesToCleanUp.append((defaults, suiteName))
        return defaults
    }

    func testAutoCheckEnabledRoundTrips() {
        let defaults = makeDefaults()
        var store = UserDefaultsAutoUpdatePreferenceStore(keyPrefix: "com.test.app", defaults: defaults)

        XCTAssertFalse(store.autoCheckEnabled)
        store.autoCheckEnabled = true
        XCTAssertTrue(store.autoCheckEnabled)
        store.autoCheckEnabled = false
        XCTAssertFalse(store.autoCheckEnabled)
    }

    func testAutoInstallEnabledRoundTrips() {
        let defaults = makeDefaults()
        var store = UserDefaultsAutoUpdatePreferenceStore(keyPrefix: "com.test.app", defaults: defaults)

        XCTAssertFalse(store.autoInstallEnabled)
        store.autoInstallEnabled = true
        XCTAssertTrue(store.autoInstallEnabled)
        store.autoInstallEnabled = false
        XCTAssertFalse(store.autoInstallEnabled)
    }

    func testPreferencesAreStoredUnderPrefixedKeys() {
        let defaults = makeDefaults()
        let prefix = "com.test.app"
        var store = UserDefaultsAutoUpdatePreferenceStore(keyPrefix: prefix, defaults: defaults)

        store.autoCheckEnabled = true
        store.autoInstallEnabled = true

        XCTAssertTrue(defaults.bool(forKey: "\(prefix).autoCheckEnabled"))
        XCTAssertTrue(defaults.bool(forKey: "\(prefix).autoInstallEnabled"))
    }

    func testDifferentKeyPrefixesAreIsolated() {
        let defaults = makeDefaults()
        var store = UserDefaultsAutoUpdatePreferenceStore(keyPrefix: "com.test.app", defaults: defaults)
        let other = UserDefaultsAutoUpdatePreferenceStore(keyPrefix: "com.test.other", defaults: defaults)

        store.autoCheckEnabled = true
        store.autoInstallEnabled = true

        XCTAssertFalse(other.autoCheckEnabled)
        XCTAssertFalse(other.autoInstallEnabled)
    }
}
