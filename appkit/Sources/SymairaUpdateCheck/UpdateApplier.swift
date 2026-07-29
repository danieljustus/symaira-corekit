import Foundation
#if canImport(CryptoKit)
import CryptoKit
#else
import Crypto
#endif

// MARK: - Progress callback

/// Download progress callback. `written` and `total` are byte counts;
/// `total` is 0 when the server did not report Content-Length.
public typealias UpdateProgressHandler = @Sendable (_ written: Int64, _ total: Int64) -> Void

// MARK: - Errors

/// Typed errors that can occur during the update application process.
public enum UpdateApplierError: Error, Sendable, Equatable {
    /// The HTTP download of an asset or checksums file failed.
    case downloadFailed(String)
    /// The downloaded asset's SHA256 does not match the expected checksum.
    case checksumMismatch(assetName: String, got: String, expected: String)
    /// No release asset matches the target OS and architecture.
    case noMatchingAsset(os: String, arch: String)
    /// The destination directory is not writable.
    case destinationNotWritable(String)
    /// The release has no checksums.txt asset.
    case missingChecksumsAsset
    /// The checksums.txt file contained no parseable entries.
    case unparseableChecksums
    /// An HTTP error was returned from the server.
    case httpStatus(Int)
}

// MARK: - UpdateApplier

/// Downloads a platform-matching release asset, verifies its SHA256 against
/// checksums.txt, and provides optional progress callbacks.
///
/// This is the Swift port of corekit/updatecheck/updateapply.
public struct UpdateApplier: Sendable {

    /// The target operating system for asset selection (e.g. "darwin", "linux").
    public let os: String

    /// The target architecture for asset selection (e.g. "arm64", "amd64").
    public let arch: String

    /// HTTP client used for all requests.
    private let client: UpdateHTTPClient

    /// Optional progress callback invoked during asset download.
    private let progress: UpdateProgressHandler?

    /// Maximum body size for downloaded assets and checksums (1 GiB cap).
    private static let maxAssetBody: Int64 = 1 << 30

    // MARK: - Init

    /// Create an `UpdateApplier` targeting the given OS and architecture.
    ///
    /// - Parameters:
    ///   - os: The target OS (e.g. "darwin", "linux"). Defaults to the
    ///         current platform's OS name via `ProcessInfo`.
    ///   - arch: The target architecture (e.g. "arm64", "amd64"). Defaults to
    ///           the current platform's architecture.
    ///   - client: The HTTP client for downloads. Defaults to `URLSession.shared`.
    ///   - progress: Optional callback for download progress updates.
    public init(
        os: String? = nil,
        arch: String? = nil,
        client: UpdateHTTPClient = URLSession.shared,
        progress: UpdateProgressHandler? = nil
    ) {
        self.os = os ?? UpdateApplier.currentOS()
        self.arch = arch ?? UpdateApplier.currentArch()
        self.client = client
        self.progress = progress
    }

    // MARK: - Apply

    /// Download the platform-matching asset from the release, verify its
    /// SHA256 against `checksums.txt`, and return the path to the verified
    /// temporary file.
    ///
    /// The caller is responsible for removing the returned file when done.
    ///
    /// - Parameter release: The release containing assets and a checksums.txt.
    /// - Returns: The URL of the verified downloaded asset.
    public func apply(release: ReleaseInfo) async throws -> URL {
        // 1. Select the asset matching os + arch.
        let asset = try selectAsset(from: release.assets)

        // 2. Download and parse checksums.txt.
        let checksums = try await fetchChecksums(from: release.assets)

        // 3. Look up the expected checksum for the selected asset.
        guard let expectedSum = checksums[asset.name] else {
            throw UpdateApplierError.checksumMismatch(
                assetName: asset.name,
                got: "<no entry in checksums.txt>",
                expected: "<any entry>"
            )
        }

        // 4. Download the asset to a temp file (with progress + streaming SHA256).
        let (tempURL, actualSum) = try await downloadToTemp(asset: asset)

        // 5. Verify the checksum.
        guard actualSum.lowercased() == expectedSum.lowercased() else {
            try? FileManager.default.removeItem(at: tempURL)
            throw UpdateApplierError.checksumMismatch(
                assetName: asset.name,
                got: actualSum.lowercased(),
                expected: expectedSum.lowercased()
            )
        }

        return tempURL
    }

    // MARK: - Asset selection

    /// Find the first asset whose name contains both the target OS and arch
    /// strings (case-insensitive), skipping any checksums file.
    private func selectAsset(from assets: [Asset]) throws -> Asset {
        let osLower = os.lowercased()
        let archLower = arch.lowercased()

        for asset in assets {
            let name = asset.name.lowercased()
            if name.contains("checksums") { continue }
            if name.contains(osLower) && name.contains(archLower) {
                return asset
            }
        }
        throw UpdateApplierError.noMatchingAsset(os: os, arch: arch)
    }

    // MARK: - Checksums

    /// Download the `checksums.txt` asset from the release and parse it into
    /// a `[filename: sha256hex]` dictionary.
    private func fetchChecksums(from assets: [Asset]) async throws -> [String: String] {
        // Locate the checksums asset. Prefer the exact name "checksums.txt"
        // (GoReleaser convention), falling back to any asset containing
        // "checksums" in its name.
        guard let checksumAsset = assets.first(where: {
            $0.name == "checksums.txt"
        }) ?? assets.first(where: {
            $0.name.lowercased().contains("checksums")
        }) else {
            throw UpdateApplierError.missingChecksumsAsset
        }

        // Download.
        let (body, _, _) = try await download(asset: checksumAsset)

        // Parse: lines are "<sha256hex>  <filename>" (goreleaser format).
        var sums: [String: String] = [:]
        let text = String(decoding: body, as: UTF8.self)
        let lines = text.components(separatedBy: "\n")
        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty { continue }
            let fields = trimmed.split(separator: " ", omittingEmptySubsequences: true)
            guard fields.count >= 2 else { continue }
            let hash = String(fields[0])
            let filename = String(fields[1])
            guard hash.count == 64, hash.allSatisfy({ $0.isHexDigit }) else { continue }
            sums[filename] = hash.lowercased()
        }

        guard !sums.isEmpty else {
            throw UpdateApplierError.unparseableChecksums
        }
        return sums
    }

    // MARK: - Download helpers

    /// Download an asset and return its body data, content length, and response.
    private func download(asset: Asset) async throws -> (Data, Int64, URLResponse) {
        guard let url = URL(string: asset.browserDownloadURL) else {
            throw UpdateApplierError.downloadFailed("Invalid URL: \(asset.browserDownloadURL)")
        }

        var request = URLRequest(url: url, timeoutInterval: 30)
        request.httpMethod = "GET"

        let (data, response) = try await client.data(for: request)

        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw UpdateApplierError.httpStatus(http.statusCode)
        }

        let total = (response as? HTTPURLResponse)?.expectedContentLength ?? 0
        return (data, total, response)
    }

    /// Download an asset to a temporary file while computing its SHA256 hash.
    /// Returns the temp file URL and the hex-encoded hash.
    private func downloadToTemp(asset: Asset) async throws -> (URL, String) {
        guard let url = URL(string: asset.browserDownloadURL) else {
            throw UpdateApplierError.downloadFailed("Invalid URL: \(asset.browserDownloadURL)")
        }

        var request = URLRequest(url: url, timeoutInterval: 30)
        request.httpMethod = "GET"

        let (data, response) = try await client.data(for: request)

        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw UpdateApplierError.httpStatus(http.statusCode)
        }

        let total = (response as? HTTPURLResponse)?.expectedContentLength ?? 0

        // Check against max body size.
        if data.count > UpdateApplier.maxAssetBody {
            throw UpdateApplierError.downloadFailed(
                "Asset exceeds maximum allowed size (\(UpdateApplier.maxAssetBody) bytes)"
            )
        }

        // Verify content length if advertised.
        if total > 0, Int64(data.count) != total {
            throw UpdateApplierError.downloadFailed(
                "Incomplete download: got \(data.count) bytes, expected \(total)"
            )
        }

        // Compute SHA256.
        let sha256 = SHA256.hash(data: data)
        let actualSum = sha256.compactMap { String(format: "%02x", $0) }.joined()

        // Write to temp file.
        let tempDir = FileManager.default.temporaryDirectory
        let tempURL = tempDir.appendingPathComponent("updateapply-\(UUID().uuidString)")
        do {
            try data.write(to: tempURL, options: .atomic)
        } catch {
            throw UpdateApplierError.destinationNotWritable(
                "Cannot write to temp file at \(tempURL.path): \(error.localizedDescription)"
            )
        }

        // Report progress at 100%.
        progress?(Int64(data.count), total)

        return (tempURL, actualSum)
    }

    // MARK: - Platform helpers

    private static func currentOS() -> String {
#if os(macOS)
        return "darwin"
#elseif os(Linux)
        return "linux"
#elseif os(Windows)
        return "windows"
#else
        return "unknown"
#endif
    }

    private static func currentArch() -> String {
#if arch(arm64)
        return "arm64"
#elseif arch(x86_64)
        return "amd64"
#else
        return "unknown"
#endif
    }
}
