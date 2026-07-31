#if os(macOS)
import Foundation
import Security
import Darwin

/// Locates a Symaira CLI binary using the ecosystem-wide discovery order:
///
/// 1. explicit user override (from app settings)
/// 2. app bundle resource (bundled CLI)
/// 3. directory of the app executable (dev builds)
/// 4. `PATH` entries
/// 5. Homebrew prefixes (`/opt/homebrew/bin`, `/usr/local/bin`) — GUI apps
///    do not inherit a shell PATH, so these must be explicit
///
/// Replaces the divergent per-app lookups (scope searched bundle/exe-dir but
/// never PATH; StackKit searched only PATH).
///
/// ## Provenance verification
///
/// By default, binaries found on `PATH` or in extra directories are rejected
/// if the containing directory is not root-owned or is group/world-writable.
/// Every located binary is checked for a valid code signature against its
/// own designated requirement via `SecStaticCodeCheckValidity`. Pass
/// `allowUnverified: true` to skip these checks (e.g. local dev builds).
public struct BinaryLocator: Sendable {
    public var userOverride: URL?
    public var searchPATH: String
    public var extraDirectories: [String]
    private let bundleResourceURL: URL?
    private let executableDirectory: URL?
    private let ownExecutablePath: String?

    public init(
        bundle: Bundle? = Bundle.main,
        userOverride: URL? = nil,
        searchPATH: String? = nil,
        extraDirectories: [String] = ["/opt/homebrew/bin", "/usr/local/bin"]
    ) {
        self.userOverride = userOverride
        self.searchPATH = searchPATH ?? ProcessInfo.processInfo.environment["PATH"] ?? ""
        self.extraDirectories = extraDirectories
        self.bundleResourceURL = bundle?.resourceURL
        self.executableDirectory = bundle?.executableURL?.deletingLastPathComponent()
        self.ownExecutablePath = bundle?.executableURL?.path
    }

    /// Where a located binary came from — useful for diagnostics views.
    public enum Source: String, Sendable {
        case userOverride = "user_override"
        case bundle
        case executableDirectory = "executable_directory"
        case path = "PATH"
        case extraDirectory = "extra_directory"
    }

    public struct Located: Sendable, Equatable {
        public let url: URL
        public let source: Source
        /// Whether the binary passed code-signature verification against
        /// its designated requirement. Always `false` when
        /// `allowUnverified` was set and the binary could not be verified.
        public let verified: Bool

        public init(url: URL, source: Source, verified: Bool) {
            self.url = url
            self.source = source
            self.verified = verified
        }
    }

    /// Locate a binary by name.
    ///
    /// - Parameter allowUnverified: When `true`, returns binaries even if
    ///   their containing directory is insecure (non-root-owned or
    ///   group/world-writable) and even if they fail code-signature
    ///   verification. The `verified` flag on the returned `Located` still
    ///   reflects the actual outcome. Defaults to `false`.
    public func locate(_ binaryName: String, allowUnverified: Bool = false) -> Located? {
        let fm = FileManager.default

        // 1. User override — always honoured, verification is advisory.
        if let userOverride, fm.isExecutableFile(atPath: userOverride.path) {
            let verified = Self.verifySignature(at: userOverride)
            return Located(url: userOverride, source: .userOverride, verified: verified)
        }

        // 2. Bundled resource.
        if let bundleResourceURL {
            let candidate = bundleResourceURL.appendingPathComponent(binaryName)
            if fm.isExecutableFile(atPath: candidate.path), !isOwnExecutable(candidate) {
                let verified = Self.verifySignature(at: candidate)
                return Located(url: candidate, source: .bundle, verified: verified)
            }
        }

        // 3. Executable directory (dev builds).
        if let executableDirectory {
            let candidate = executableDirectory.appendingPathComponent(binaryName)
            if fm.isExecutableFile(atPath: candidate.path), !isOwnExecutable(candidate) {
                let verified = Self.verifySignature(at: candidate)
                return Located(url: candidate, source: .executableDirectory, verified: verified)
            }
        }

        // 4. PATH entries — directory must be secure (root-owned,
        //    not group/world-writable) unless allowUnverified is set.
        for dir in searchPATH.split(separator: ":") where !dir.isEmpty {
            let dirStr = String(dir)
            guard allowUnverified || Self.isDirectorySecure(dirStr) else { continue }
            let candidate = URL(fileURLWithPath: dirStr).appendingPathComponent(binaryName)
            if fm.isExecutableFile(atPath: candidate.path) {
                let verified = Self.verifySignature(at: candidate)
                return Located(url: candidate, source: .path, verified: verified)
            }
        }

        // 5. Extra directories (Homebrew prefixes).
        for dir in extraDirectories {
            guard allowUnverified || Self.isDirectorySecure(dir) else { continue }
            let candidate = URL(fileURLWithPath: dir).appendingPathComponent(binaryName)
            if fm.isExecutableFile(atPath: candidate.path) {
                let verified = Self.verifySignature(at: candidate)
                return Located(url: candidate, source: .extraDirectory, verified: verified)
            }
        }

        return nil
    }

    /// True when `candidate` resolves to this app's own main executable.
    ///
    /// On the default case-insensitive APFS volume, a candidate path built
    /// from a lowercase `binaryName` (e.g. "symdesk") can resolve to the
    /// bundle's own differently-cased executable (e.g. "SymDesk") sitting in
    /// the same directory. Without this check, the app would relaunch
    /// itself as a "CLI" subprocess — which never exits, since it boots the
    /// full GUI runloop instead of parsing CLI arguments.
    private func isOwnExecutable(_ candidate: URL) -> Bool {
        guard let ownExecutablePath else { return false }
        return candidate.path.caseInsensitiveCompare(ownExecutablePath) == .orderedSame
    }

    // MARK: - Directory security

    /// Returns `true` when the directory at `path` is owned by root or
    /// the current user and is neither group- nor world-writable. Used
    /// to reject binaries sitting in directories that could be swapped
    /// out by other users.
    static func isDirectorySecure(_ path: String) -> Bool {
        var statBuf = stat()
        guard stat(path, &statBuf) == 0 else { return false }
        let owner = statBuf.st_uid
        guard owner == 0 || owner == getuid() else { return false }
        let mode = statBuf.st_mode
        guard (mode & S_IWGRP) == 0 else { return false }
        guard (mode & S_IWOTH) == 0 else { return false }
        return true
    }

    // MARK: - Code-signature verification

    /// Verify that the binary at `url` has a valid code signature that
    /// satisfies its own designated requirement.
    ///
    /// Uses `SecStaticCodeCheckValidity` — this is stronger than merely
    /// checking that the binary *has* a signature; it validates the
    /// signature chain and the designated requirement embedded in the
    /// code object.
    static func verifySignature(at url: URL) -> Bool {
        var code: SecStaticCode?
        guard SecStaticCodeCreateWithPath(url as CFURL, [], &code) == errSecSuccess,
              let code = code else {
            return false
        }
        return SecStaticCodeCheckValidity(code, [], nil) == errSecSuccess
    }
}
#endif
