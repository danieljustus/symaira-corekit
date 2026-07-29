import Foundation

/// The status of an update check.
public enum AppUpdateStatus: Equatable, Sendable {
    case unknown
    case upToDate
    case available(ReleaseInfo)
    case skipped(ReleaseInfo)
    /// Download and installation is in progress. `progress` ranges from 0.0 to 1.0.
    case installing(progress: Double)
    /// The updated app bundle has been installed and is ready for relaunch.
    case readyToRelaunch
    case error(String)
}

/// Persists which release versions the user dismissed, so they are not re-prompted for them.
public protocol SkippedVersionStore: Sendable {
    func skippedTag() -> String?
    func setSkippedTag(_ tag: String?)
}

/// A UserDefaults-backed skipped-version store with a configurable key.
///
/// Each app that uses `AppUpdateChecker` should use its own key so that
/// skipped versions are tracked per app and never leak between apps.
///
/// SymDesk backward-compatible key: `"com.symaira.desktop.updateSkippedTag"`
public struct UserDefaultsSkippedVersionStore: SkippedVersionStore, @unchecked Sendable {
    private let key: String
    private let defaults: UserDefaults

    public init(key: String, defaults: UserDefaults = .standard) {
        self.key = key
        self.defaults = defaults
    }

    public func skippedTag() -> String? {
        defaults.string(forKey: key)
    }

    public func setSkippedTag(_ tag: String?) {
        if let tag {
            defaults.set(tag, forKey: key)
        } else {
            defaults.removeObject(forKey: key)
        }
    }
}

// MARK: - Auto-update preference store

/// Persists user preferences for automatic update checking and installation.
public protocol AutoUpdatePreferenceStore: Sendable {
    /// Whether to automatically check for updates on app launch.
    var autoCheckEnabled: Bool { get set }
    /// Whether to automatically install found updates (requires autoCheckEnabled).
    var autoInstallEnabled: Bool { get set }
}

/// A UserDefaults-backed auto-update preference store with a configurable key prefix.
///
/// Each app should use its own key prefix so preferences are tracked per app.
/// Example key: `"com.symaira.desktop"` → stores `com.symaira.desktop.autoCheckEnabled`
/// and `com.symaira.desktop.autoInstallEnabled`.
public struct UserDefaultsAutoUpdatePreferenceStore: AutoUpdatePreferenceStore, @unchecked Sendable {
    private let keyPrefix: String
    private let defaults: UserDefaults

    public init(keyPrefix: String, defaults: UserDefaults = .standard) {
        self.keyPrefix = keyPrefix
        self.defaults = defaults
    }

    public var autoCheckEnabled: Bool {
        get { defaults.bool(forKey: "\(keyPrefix).autoCheckEnabled") }
        set { defaults.set(newValue, forKey: "\(keyPrefix).autoCheckEnabled") }
    }

    public var autoInstallEnabled: Bool {
        get { defaults.bool(forKey: "\(keyPrefix).autoInstallEnabled") }
        set { defaults.set(newValue, forKey: "\(keyPrefix).autoInstallEnabled") }
    }
}

/// Checks for a newer release and gates re-prompting for a version the user already skipped.
///
/// This is the high-level, `@MainActor`-bound checker that combines the
/// low-level `UpdateChecker` with a `SkippedVersionStore`. It is designed
/// to be used as an `ObservableObject` in SwiftUI views.
@MainActor
public final class AppUpdateChecker: ObservableObject {
    @Published public private(set) var status: AppUpdateStatus = .unknown

    private let checker: UpdateChecker
    private let store: SkippedVersionStore
    private let currentVersion: () -> String

    public init(
        checker: UpdateChecker,
        store: SkippedVersionStore,
        currentVersion: @escaping () -> String,
        autoPrefs: AutoUpdatePreferenceStore? = nil
    ) {
        self.checker = checker
        self.store = store
        self.currentVersion = currentVersion
        self.autoPrefs = autoPrefs
    }

    /// Check for a newer release. `force` bypasses both the disk cache and the skip gate.
    public func checkForUpdate(force: Bool = false) async {
        do {
            guard let release = try await checker.check(currentVersion: currentVersion(), force: force) else {
                status = .upToDate
                return
            }
            if !force, store.skippedTag() == release.tagName {
                status = .skipped(release)
            } else {
                status = .available(release)
            }
        } catch {
            status = .error(String(describing: error))
        }
    }

    /// Dismiss a specific release so the user is not re-prompted for it.
    public func skip(_ release: ReleaseInfo) {
        store.setSkippedTag(release.tagName)
        status = .skipped(release)
    }

    // MARK: - Auto-update

    private let autoPrefs: AutoUpdatePreferenceStore?

    /// Call this on app launch. If auto-update preferences are configured
    /// and enabled, it runs a check (respecting the disk cache — no forced fetch).
    /// If auto-install is also enabled and an update is found, installation begins.
    public func checkOnLaunchIfEnabled() async {
        guard let prefs = autoPrefs, prefs.autoCheckEnabled else { return }
        await checkForUpdate(force: false)
        if prefs.autoInstallEnabled, case .available = status {
            // Installation is handled by the consumer; we just surface the
            // available release. The consumer can call install() on UpdateApplier.
        }
    }
}
