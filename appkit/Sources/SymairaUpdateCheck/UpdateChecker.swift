import Foundation

/// A downloadable release asset (binary, checksums, etc.).
public struct Asset: Sendable, Equatable, Codable {
    public let name: String
    public let browserDownloadURL: String
    public let size: Int64

    public init(name: String, browserDownloadURL: String, size: Int64) {
        self.name = name
        self.browserDownloadURL = browserDownloadURL
        self.size = size
    }
}

/// An available newer release on GitHub.
public struct ReleaseInfo: Sendable, Equatable, Codable {
    public let tagName: String
    public let htmlURL: String
    public let assets: [Asset]

    public init(tagName: String, htmlURL: String, assets: [Asset] = []) {
        self.tagName = tagName
        self.htmlURL = htmlURL
        self.assets = assets
    }
}

/// Injectable HTTP transport so tests can stub GitHub responses
/// (Swift port of corekit/updatecheck's `httpDoer`).
public protocol UpdateHTTPClient: Sendable {
    func data(for request: URLRequest) async throws -> (Data, URLResponse)
}

extension URLSession: UpdateHTTPClient {}

public enum UpdateCheckError: Error, Sendable {
    case httpStatus(Int)
    case decodeFailed
}

/// Never-blocking GitHub release checker (Swift port of corekit/updatecheck).
///
/// Returns nil when the current version is up to date, when it is not a
/// stable semver (dev builds), or when the latest tag cannot be parsed.
/// Results are cached on disk with a TTL so app launches stay cheap.
public struct UpdateChecker: Sendable {
    public let owner: String
    public let repo: String
    public let cacheTTL: TimeInterval

    private let client: UpdateHTTPClient
    private let cacheDirectory: URL

    public init(
        owner: String,
        repo: String,
        client: UpdateHTTPClient = URLSession.shared,
        cacheTTL: TimeInterval = 24 * 60 * 60,
        cacheDirectory: URL? = nil
    ) {
        self.owner = owner
        self.repo = repo
        self.client = client
        self.cacheTTL = cacheTTL
#if os(iOS) || os(tvOS) || os(watchOS)
        let defaultCache: URL = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first!
#else
        let defaultCache: URL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".cache/symaira-appkit", isDirectory: true)
#endif
        self.cacheDirectory = cacheDirectory ?? defaultCache
    }

    /// Check for a newer stable release. `force` bypasses the disk cache.
    public func check(currentVersion: String, force: Bool = false) async throws -> ReleaseInfo? {
        guard let current = StableVersion(currentVersion) else {
            return nil
        }

        let latest: LatestRelease
        if !force, let cached = readCache() {
            latest = cached
        } else {
            latest = try await fetchLatest()
            writeCache(latest)
        }

        guard let latestVersion = StableVersion(latest.tagName), latestVersion > current else {
            return nil
        }
        return ReleaseInfo(tagName: latest.tagName, htmlURL: latest.htmlURL)
    }

    // MARK: - GitHub API

    private struct LatestRelease: Codable {
        let tagName: String
        let htmlURL: String
        var fetchedAt: Date?
    }

    private func fetchLatest() async throws -> LatestRelease {
        let url = URL(string: "https://api.github.com/repos/\(owner)/\(repo)/releases/latest")!
        var request = URLRequest(url: url, timeoutInterval: 10)
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")

        let (data, response) = try await client.data(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw UpdateCheckError.httpStatus(http.statusCode)
        }

        struct GitHubRelease: Decodable {
            let tagName: String
            let htmlUrl: String
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let release = try? decoder.decode(GitHubRelease.self, from: data) else {
            throw UpdateCheckError.decodeFailed
        }
        return LatestRelease(tagName: release.tagName, htmlURL: release.htmlUrl, fetchedAt: Date())
    }

    // MARK: - Disk cache

    private var cacheFile: URL {
        cacheDirectory.appendingPathComponent("\(owner)-\(repo).json")
    }

    private func readCache() -> LatestRelease? {
        guard let data = try? Data(contentsOf: cacheFile),
              let entry = try? JSONDecoder().decode(LatestRelease.self, from: data),
              let fetchedAt = entry.fetchedAt,
              Date().timeIntervalSince(fetchedAt) < cacheTTL
        else { return nil }
        return entry
    }

    private func writeCache(_ entry: LatestRelease) {
        try? FileManager.default.createDirectory(at: cacheDirectory, withIntermediateDirectories: true)
        if let data = try? JSONEncoder().encode(entry) {
            try? data.write(to: cacheFile, options: .atomic)
        }
    }
}
