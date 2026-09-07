import Foundation
#if canImport(CryptoKit)
import CryptoKit
#else
import Crypto
#endif

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

    private enum CodingKeys: String, CodingKey {
        case name
        case browserDownloadURL = "browser_download_url"
        case size
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
    case draftRelease
    case prereleaseRelease
    case invalidReleaseTag(String)
}

/// GitHub release checker (Swift port of corekit/updatecheck).
///
/// Returns nil when the current version is up to date or is not a stable
/// semver (dev builds). Malformed latest-release tags are surfaced as errors.
/// Results are cached on disk with a TTL. Callers should run optional checks
/// off startup-critical paths and decide how to present surfaced failures.
public struct UpdateChecker: Sendable {
    public static let defaultAPITimeout: TimeInterval = 3

    public let owner: String
    public let repo: String
    public let cacheTTL: TimeInterval

    private let client: UpdateHTTPClient
    let cacheDirectory: URL

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
        let platformCache = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        let defaultCache = platformCache.appendingPathComponent("symaira/updatecheck", isDirectory: true)
        self.cacheDirectory = cacheDirectory ?? defaultCache
    }

    /// Check for a newer stable release. `force` bypasses the disk cache.
    public func check(currentVersion: String, force: Bool = false) async throws -> ReleaseInfo? {
        guard let current = StableVersion(currentVersion) else {
            return nil
        }

        let latest: LatestRelease
        let latestVersion: StableVersion
        if !force, let cached = readCache(), let cachedVersion = StableVersion(cached.tagName) {
            latest = cached
            latestVersion = cachedVersion
        } else {
            latest = try await fetchLatest()
            guard let fetchedVersion = StableVersion(latest.tagName) else {
                throw UpdateCheckError.invalidReleaseTag(latest.tagName)
            }
            latestVersion = fetchedVersion
            writeCache(latest)
        }

        guard latestVersion > current else {
            return nil
        }

        // V0-major gap: mirrors corekit's Checker.Check. A pre-v1.0 consumer
        // should not suddenly be offered a v1.0+ release before the
        // ecosystem has decided it's ready for that jump. Applies to both
        // the cache-hit and freshly-fetched paths above, since they both
        // funnel through this one comparison.
        if current.major == 0 && latestVersion.major > 0 {
            return nil
        }

        return ReleaseInfo(tagName: latest.tagName, htmlURL: latest.htmlURL, assets: latest.assets)
    }

    // MARK: - GitHub API

    private struct LatestRelease: Codable {
        let tagName: String
        let htmlURL: String
        let assets: [Asset]
        var fetchedAt: Date?

        private enum CodingKeys: String, CodingKey {
            case tagName
            case htmlURL
            case assets
            case fetchedAt
        }

        init(tagName: String, htmlURL: String, assets: [Asset], fetchedAt: Date?) {
            self.tagName = tagName
            self.htmlURL = htmlURL
            self.assets = assets
            self.fetchedAt = fetchedAt
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            tagName = try container.decode(String.self, forKey: .tagName)
            htmlURL = try container.decode(String.self, forKey: .htmlURL)
            assets = try container.decodeIfPresent([Asset].self, forKey: .assets) ?? []
            fetchedAt = try container.decodeIfPresent(Date.self, forKey: .fetchedAt)
        }
    }

    private func fetchLatest() async throws -> LatestRelease {
        let url = URL(string: "https://api.github.com/repos/\(owner)/\(repo)/releases/latest")!
        var request = URLRequest(url: url, timeoutInterval: Self.defaultAPITimeout)
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")

        let (data, response) = try await client.data(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw UpdateCheckError.httpStatus(http.statusCode)
        }

        struct GitHubRelease: Decodable {
            let draft: Bool
            let prerelease: Bool
            let tagName: String
            let htmlURL: String
            let assets: [Asset]

            enum CodingKeys: String, CodingKey {
                case draft
                case prerelease
                case tagName = "tag_name"
                case htmlURL = "html_url"
                case assets
            }

            init(from decoder: Decoder) throws {
                let container = try decoder.container(keyedBy: CodingKeys.self)
                draft = try container.decodeIfPresent(Bool.self, forKey: .draft) ?? false
                prerelease = try container.decodeIfPresent(Bool.self, forKey: .prerelease) ?? false
                tagName = try container.decode(String.self, forKey: .tagName)
                htmlURL = try container.decode(String.self, forKey: .htmlURL)
                assets = try container.decodeIfPresent([Asset].self, forKey: .assets) ?? []
            }
        }
        let decoder = JSONDecoder()
        guard let release = try? decoder.decode(GitHubRelease.self, from: data) else {
            throw UpdateCheckError.decodeFailed
        }
        if release.draft {
            throw UpdateCheckError.draftRelease
        }
        if release.prerelease {
            throw UpdateCheckError.prereleaseRelease
        }
        return LatestRelease(
            tagName: release.tagName,
            htmlURL: release.htmlURL,
            assets: release.assets,
            fetchedAt: Date()
        )
    }

    // MARK: - Disk cache

    var cacheFile: URL {
        let identity = Data("\(owner)\0\(repo)".utf8)
        let digest = SHA256.hash(data: identity).map { String(format: "%02x", $0) }.joined()
        return cacheDirectory.appendingPathComponent("\(digest).json")
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
