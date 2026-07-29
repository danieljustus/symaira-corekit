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
        currentVersion: @escaping () -> String
    ) {
        self.checker = checker
        self.store = store
        self.currentVersion = currentVersion
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
}
