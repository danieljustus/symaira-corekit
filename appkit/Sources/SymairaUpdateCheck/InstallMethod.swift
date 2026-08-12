import Foundation

// MARK: - Install method detection

/// Describes how a binary or app bundle was installed, determining whether
/// self-update is safe (Swift port of corekit/installmethod).
public enum InstallMethod: String, Sendable, Equatable, CaseIterable {
    /// Downloaded directly from a GitHub release. Self-update is safe.
    case directDownload = "direct-download"
    /// Installed via Homebrew. Users should update with "brew upgrade".
    case homebrew
    /// Installed via "go install".
    case goInstall = "go-install"
    /// Installed via a system package manager (APT, YUM, etc.).
    case packageManager = "package-manager"
    /// Compiled locally from source.
    case buildFromSource = "build-from-source"
    /// Installation method could not be determined.
    case unknown
}

#if os(macOS)
// MARK: - InstallMethodDetector

/// Internal install-method detection used by `UpdateApplier`
/// (Swift port of corekit/installmethod.Detect).
enum InstallMethodDetector {

    /// Detect how a binary or app was installed at the given path.
    /// Swift port of corekit/installmethod.Detect.
    static func detect(at binaryPath: String) -> InstallMethod {
        guard !binaryPath.isEmpty else { return .unknown }

        // Check the original path against known patterns FIRST.
        // Symlink resolution follows: a user-facing path like
        // /usr/local/bin/foo must be classified as directDownload
        // even if the file is a symlink into a Homebrew Cellar.
        let originalAbs = URL(fileURLWithPath: binaryPath).standardized.path
        if let method = detectFromPath(originalAbs) { return method }

        // Resolve symlinks (throws for nonexistent paths).
        let realPath: String
        if let resolved = try? FileManager.default
            .destinationOfSymbolicLink(atPath: binaryPath) {
            realPath = resolved
        } else {
            realPath = binaryPath
        }

        // Normalize to absolute path.
        let absPath = URL(fileURLWithPath: realPath).standardized.path

        // Check env vars.
        if let method = detectFromEnv(absPath) { return method }

        // Check Cellar receipts.
        if absPath.contains("/Cellar/") { return .homebrew }

        // Check writability.
        return detectFromWritability(absPath)
    }

    /// Returns true only for `directDownload`.
    static func isSelfUpdateSupported(_ method: InstallMethod) -> Bool {
        return method == .directDownload || method == .unknown
    }

    /// Returns actionable upgrade instructions for the given method.
    static func guidance(for method: InstallMethod, binaryName: String) -> String {
        switch method {
        case .directDownload:
            return "Re-run the quick install script or download the latest release from GitHub"
        case .homebrew:
            return "Update via Homebrew: brew update && brew upgrade \(binaryName)"
        case .goInstall:
            return "Update via Go: go install github.com/danieljustus/\(binaryName)@latest"
        case .packageManager:
            return "Update via your system package manager"
        case .buildFromSource:
            return "Rebuild from source: git pull && swift build"
        case .unknown:
            return "Unable to determine installation method. Reinstall from the GitHub releases page"
        }
    }

    // MARK: - Detection helpers

    private static func detectFromEnv(_ absPath: String) -> InstallMethod? {
        if let prefix = ProcessInfo.processInfo.environment["HOMEBREW_PREFIX"] {
            let resolved = (try? FileManager.default
                .destinationOfSymbolicLink(atPath: prefix)) ?? prefix
            if absPath.hasPrefix(resolved) {
                return .homebrew
            }
        }

        if let gopath = ProcessInfo.processInfo.environment["GOPATH"] {
            let resolved = (try? FileManager.default
                .destinationOfSymbolicLink(atPath: gopath)) ?? gopath
            let binDir = resolved + "/bin"
            if absPath.hasPrefix(binDir) {
                return .goInstall
            }
        }

        if let gomodcache = ProcessInfo.processInfo.environment["GOMODCACHE"] {
            let resolved = (try? FileManager.default
                .destinationOfSymbolicLink(atPath: gomodcache)) ?? gomodcache
            if absPath.hasPrefix(resolved) {
                return .goInstall
            }
        }

        return nil
    }

    private static func detectFromPath(_ absPath: String) -> InstallMethod? {
        if absPath.contains("/opt/homebrew/") { return .homebrew }
        if absPath.contains("/usr/local/Cellar/") { return .homebrew }
        if absPath.contains("/.linuxbrew/") { return .homebrew }
        if absPath.hasPrefix("/usr/bin/") { return .packageManager }
        if absPath.hasPrefix("/usr/local/bin/") { return .directDownload }

#if !os(iOS) && !os(tvOS) && !os(watchOS)
        let home = FileManager.default.homeDirectoryForCurrentUser.path
#else
        let home = NSHomeDirectory()
#endif

        // GOPATH/bin.
        if let gopath = ProcessInfo.processInfo.environment["GOPATH"] {
            let resolved = (try? FileManager.default
                .destinationOfSymbolicLink(atPath: gopath)) ?? gopath
            let binDir = resolved + "/"
            if absPath.hasPrefix(binDir) { return .goInstall }
        }

        // ~/go/bin.
        let goBin = home + "/go/bin/"
        if absPath.hasPrefix(goBin) { return .goInstall }

        // User-writable directories → direct download.
        let userBins = [
            home + "/bin/",
            home + "/.local/bin/",
            home + "/.cargo/bin/",
        ]
        for dir in userBins {
            if absPath.hasPrefix(dir) { return .directDownload }
        }

        return nil
    }

    private static func detectFromWritability(_ absPath: String) -> InstallMethod {
#if os(Windows)
        return .buildFromSource
#else
        let dir = (absPath as NSString).deletingLastPathComponent
        guard let attrs = try? FileManager.default.attributesOfItem(atPath: dir),
              let permissions = attrs[.posixPermissions] as? Int else {
            return .unknown
        }

        // Check if user has write permission on the directory.
        if permissions & 0o200 != 0 {
            return .directDownload
        }

        // Check if group/other write is allowed (less strict).
        if permissions & 0o022 != 0 {
            return .directDownload
        }

        return .buildFromSource
#endif
    }
}
#endif
