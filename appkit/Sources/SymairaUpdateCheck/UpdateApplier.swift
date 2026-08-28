import Foundation

// MARK: - Progress callback

/// Download progress callback. `written` and `total` are byte counts;
/// `total` is 0 when the server did not report Content-Length.
public typealias UpdateProgressHandler = @Sendable (_ written: Int64, _ total: Int64) -> Void

#if os(macOS)
// MARK: - UpdateApplier

/// Downloads a platform-matching release asset, verifies its SHA256 against
/// checksums.txt, and provides optional progress callbacks. Supports both
/// raw binary and .app bundle (DMG/ZIP) releases.
///
/// Optional hardening (all disabled by default):
/// - Install method detection (`checkInstallMethod`): rejects Homebrew installs.
/// - Cosign verification (`cosignConfig`): verifies checksums.txt signature.
///
/// This is the Swift port of corekit/updatecheck/updateapply.
///
/// `UpdateApplier` is a thin orchestrator: downloads stream through
/// `AssetDownloader`, checksums.txt is parsed by `ChecksumManifest`, cosign
/// verification runs through `CosignVerification`, DMG/ZIP installation
/// delegates to `AppInstaller`, and install-method detection to
/// `InstallMethodDetector`.
public struct UpdateApplier: Sendable {

    /// The target operating system for asset selection (e.g. "darwin", "linux").
    public let os: String

    /// The target architecture for asset selection (e.g. "arm64", "amd64").
    public let arch: String

    /// HTTP client used for all requests.
    private let client: UpdateHTTPClient

    /// Optional progress callback invoked during asset download.
    private let progress: UpdateProgressHandler?

    /// When true, detects the installation method of the target binary
    /// and rejects self-update for Homebrew-managed binaries.
    public let checkInstallMethod: Bool

    /// Display name used in install-method guidance messages. Defaults to
    /// the asset name when empty.
    public let binaryName: String?

    /// When non-nil, enables Cosign keyless signature verification of
    /// checksums.txt before any downloaded asset is trusted.
    public let cosignConfig: CosignConfig?

    /// Maximum body size for downloaded assets and checksums (1 GiB cap).
    private static let maxAssetBody: Int64 = 1 << 30

    /// Size cap enforced on a single downloaded asset body, checked against
    /// the advertised `Content-Length` before the body is read and again as
    /// the running byte count crosses it mid-stream. Internal so tests can
    /// exercise the streaming size guard without allocating 1 GiB bodies;
    /// defaults to `maxAssetBody` (1 GiB).
    internal var maxBodySize: Int64 = UpdateApplier.maxAssetBody

    /// The downloader used for all asset and checksums downloads. Rebuilt on
    /// demand so a mutated `maxBodySize` is always honored.
    private var downloader: AssetDownloader {
        AssetDownloader(client: client, progress: progress, maxBodySize: maxBodySize)
    }

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
    ///   - checkInstallMethod: When true, detects Homebrew-managed installs and
    ///         rejects self-update for them. Defaults to false.
    ///   - binaryName: Display name for install-method guidance messages.
    ///         Defaults to nil (uses asset name).
    ///   - cosignConfig: When non-nil, enables Cosign keyless signature
    ///         verification of checksums.txt. Defaults to nil (disabled).
    public init(
        os: String? = nil,
        arch: String? = nil,
        client: UpdateHTTPClient = URLSession.shared,
        progress: UpdateProgressHandler? = nil,
        checkInstallMethod: Bool = false,
        binaryName: String? = nil,
        cosignConfig: CosignConfig? = nil
    ) {
        self.os = os ?? UpdateApplier.currentOS()
        self.arch = arch ?? UpdateApplier.currentArch()
        self.client = client
        self.progress = progress
        self.checkInstallMethod = checkInstallMethod
        self.binaryName = binaryName
        self.cosignConfig = cosignConfig
    }

    // MARK: - Apply (binary path)

    /// Download the platform-matching asset from the release, verify its
    /// SHA256 against `checksums.txt`, and return the path to the verified
    /// temporary file.
    ///
    /// The caller is responsible for removing the returned file when done.
    ///
    /// - Parameter release: The release containing assets and a checksums.txt.
    /// - Returns: The URL of the verified downloaded asset.
    public func apply(release: ReleaseInfo, targetPath: String? = nil) async throws -> URL {
        try await verifyAndDownload(release: release, targetPath: targetPath).tempURL
    }

    // MARK: - Apply (bundle install)

    /// Download the platform-matching asset and, if it is a .app bundle
    /// (DMG or ZIP), install it to `/Applications`. Returns the path
    /// to the installed .app bundle.
    ///
    /// For DMG assets, the disk image is mounted via `hdiutil`, the .app
    /// is copied to `/Applications`, and the image is unmounted.
    ///
    /// For ZIP assets, the archive is extracted, the .app is located, and
    /// copied to `/Applications`.
    ///
    /// Raw binaries are downloaded to a temp file (same as `apply(release:)`).
    ///
    /// - Parameters:
    ///   - release: The release containing assets and a checksums.txt.
    ///   - targetPath: Optional path to the running binary for install-method
    ///         detection. Only used when `checkInstallMethod` is true.
    /// - Returns: The URL of the installed artifact (temp file for binaries,
    ///         `/Applications/AppName.app` for bundles).
    public func applyBundle(release: ReleaseInfo, targetPath: String? = nil) async throws -> URL {
        let verified = try await verifyAndDownload(release: release, targetPath: targetPath)

        switch detectAssetType(name: verified.asset.name) {
        case .appBundleDMG:
            return try await AppInstaller.installDMG(at: verified.tempURL, assetName: verified.asset.name)
        case .appBundleZip:
            return try await AppInstaller.installZip(at: verified.tempURL, assetName: verified.asset.name)
        case .binary, .unknown:
            return verified.tempURL
        }
    }

    private struct VerifiedAsset: Sendable {
        let asset: Asset
        let tempURL: URL
    }

    /// Select, verify, download, and hash one release asset. Both public apply
    /// entry points use this exact pipeline so checksum, cosign, and install
    /// method checks cannot drift between binary and bundle updates.
    private func verifyAndDownload(release: ReleaseInfo, targetPath: String?) async throws -> VerifiedAsset {
        let asset = try selectAsset(from: release.assets)

        if checkInstallMethod, let path = targetPath {
            let method = UpdateApplier.detectInstallMethod(at: path)
            guard UpdateApplier.isSelfUpdateSupported(method) else {
                let guidance = UpdateApplier.guidance(for: method, binaryName: binaryName ?? asset.name)
                throw UpdateApplierError.unsupportedInstallMethod(method, guidance: guidance)
            }
        }

        let (rawChecksums, checksums) = try await fetchChecksums(from: release.assets)
        if let cosign = cosignConfig {
            try await CosignVerification(config: cosign).verify(rawChecksums: rawChecksums, tag: release.tagName)
        }

        guard let expectedSum = checksums[asset.name] else {
            throw UpdateApplierError.checksumMismatch(
                assetName: asset.name,
                got: "<no entry in checksums.txt>",
                expected: "<any entry>"
            )
        }

        let (tempURL, actualSum) = try await downloader.downloadToTemp(asset: asset)
        guard actualSum.lowercased() == expectedSum.lowercased() else {
            try? FileManager.default.removeItem(at: tempURL)
            throw UpdateApplierError.checksumMismatch(
                assetName: asset.name,
                got: actualSum.lowercased(),
                expected: expectedSum.lowercased()
            )
        }

        return VerifiedAsset(asset: asset, tempURL: tempURL)
    }

    // MARK: - Asset type detection

    /// Detect the asset type from the filename.
    ///
    /// - `.dmg` files are treated as app bundle DMGs.
    /// - `.zip` files are treated as app bundle ZIPs.
    /// - Everything else is treated as a raw binary.
    public func detectAssetType(name: String) -> AssetType {
        let lower = name.lowercased()
        if lower.hasSuffix(".dmg") {
            return .appBundleDMG
        }
        if lower.hasSuffix(".zip") {
            return .appBundleZip
        }
        return .binary
    }

    // MARK: - Installation (delegates to AppInstaller)

    /// Mount a DMG, copy the .app bundle to /Applications, and unmount.
    /// Uses `hdiutil` for mount/unmount operations.
    public func installDMG(at dmgURL: URL, assetName: String) async throws -> URL {
        try await AppInstaller.installDMG(at: dmgURL, assetName: assetName)
    }

    /// Extract a ZIP archive, find the .app bundle, and copy it to /Applications.
    public func installZip(at zipURL: URL, assetName: String) async throws -> URL {
        try await AppInstaller.installZip(at: zipURL, assetName: assetName)
    }

    /// Recursively search for a .app bundle in a directory.
    public func findAppBundle(in directory: URL) -> URL? {
        AppInstaller.findAppBundle(in: directory)
    }

    /// Represents a mounted DMG volume.
    public struct DMGMountResult: Sendable {
        /// The mount point directory (e.g. "/Volumes/MyApp").
        public let mountPoint: URL
        /// The device identifier (e.g. "/dev/disk3s1").
        public let device: String
    }

    // MARK: - Install method detection (delegates to InstallMethodDetector)

    /// Detect how a binary or app was installed at the given path.
    /// Swift port of corekit/installmethod.Detect.
    public static func detectInstallMethod(at binaryPath: String) -> InstallMethod {
        InstallMethodDetector.detect(at: binaryPath)
    }

    /// Returns true only for `directDownload`.
    public static func isSelfUpdateSupported(_ method: InstallMethod) -> Bool {
        InstallMethodDetector.isSelfUpdateSupported(method)
    }

    /// Returns actionable upgrade instructions for the given method.
    public static func guidance(for method: InstallMethod, binaryName: String) -> String {
        InstallMethodDetector.guidance(for: method, binaryName: binaryName)
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
    /// Returns both the raw bytes (for cosign verification) and the parsed map.
    private func fetchChecksums(from assets: [Asset]) async throws -> (Data, [String: String]) {
        // Locate the checksums asset and download it.
        let checksumAsset = try ChecksumManifest.locateAsset(in: assets)
        let (body, _, _) = try await downloader.download(asset: checksumAsset)

        // Parse: lines are "<sha256hex>  <filename>" (goreleaser format).
        let sums = ChecksumManifest.parse(String(decoding: body, as: UTF8.self))

        guard !sums.isEmpty else {
            throw UpdateApplierError.unparseableChecksums
        }
        return (body, sums)
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
#endif
