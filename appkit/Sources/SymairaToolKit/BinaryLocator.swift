import Foundation

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
public struct BinaryLocator: Sendable {
    public var userOverride: URL?
    public var searchPATH: String
    public var extraDirectories: [String]
    private let bundleResourceURL: URL?
    private let executableDirectory: URL?

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
    }

    public func locate(_ binaryName: String) -> Located? {
        let fm = FileManager.default

        if let userOverride, fm.isExecutableFile(atPath: userOverride.path) {
            return Located(url: userOverride, source: .userOverride)
        }

        if let bundleResourceURL {
            let candidate = bundleResourceURL.appendingPathComponent(binaryName)
            if fm.isExecutableFile(atPath: candidate.path) {
                return Located(url: candidate, source: .bundle)
            }
        }

        if let executableDirectory {
            let candidate = executableDirectory.appendingPathComponent(binaryName)
            if fm.isExecutableFile(atPath: candidate.path) {
                return Located(url: candidate, source: .executableDirectory)
            }
        }

        for dir in searchPATH.split(separator: ":") where !dir.isEmpty {
            let candidate = URL(fileURLWithPath: String(dir)).appendingPathComponent(binaryName)
            if fm.isExecutableFile(atPath: candidate.path) {
                return Located(url: candidate, source: .path)
            }
        }

        for dir in extraDirectories {
            let candidate = URL(fileURLWithPath: dir).appendingPathComponent(binaryName)
            if fm.isExecutableFile(atPath: candidate.path) {
                return Located(url: candidate, source: .extraDirectory)
            }
        }

        return nil
    }
}
