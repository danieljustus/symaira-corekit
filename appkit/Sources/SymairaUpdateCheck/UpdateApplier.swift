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

// MARK: - Asset type detection

/// The type of a release asset, used to decide how to install it.
public enum AssetType: Sendable, Equatable {
    /// A standalone binary executable (.tar.gz, raw binary, etc.).
    case binary
    /// A .app bundle inside a DMG disk image.
    case appBundleDMG
    /// A .app bundle inside a ZIP archive.
    case appBundleZip
    /// Asset type could not be determined from the filename.
    case unknown
}

// MARK: - Cosign verification

/// Protocol for verifying Cosign keyless signatures on release checksums.
/// Apps provide an implementation (e.g. shelling out to the cosign CLI);
/// tests stub it for fast verification without requiring cosign installed.
public protocol CosignVerifier: Sendable {
    /// Fetch the cosign signature file for the given release tag.
    func fetchSignature(tag: String) async throws -> Data
    /// Fetch the cosign certificate file for the given release tag.
    func fetchCertificate(tag: String) async throws -> Data
    /// Verify a cosign signature on the given content.
    func verifySignature(content: Data, signature: Data, certificate: Data) async throws
}

/// Configuration for Cosign keyless signature verification.
/// When non-nil on an `UpdateApplier`, the checksums.txt is verified
/// against its cosign signature before any downloaded asset is trusted.
///
/// Swift port of corekit/updatecheck/cosign.Config.
public struct CosignConfig: Sendable {
    /// The GitHub repository slug (e.g. "danieljustus/symaira-vault").
    public let repo: String

    /// The artifact name used in signature filenames
    /// (e.g. "symvault" → "symvault_1.0.0_checksums.txt.sig").
    public let binaryName: String

    /// Base URL for downloading cosign artifacts. Defaults to
    /// "https://github.com/{repo}/releases/download" when empty.
    public let downloadBaseURL: String

    /// The certificate identity regexp passed to cosign verify-blob.
    /// Defaults to a pattern matching the release workflow of `repo` when empty.
    public let identityRegexp: String

    /// The verifier implementation. Handles both fetching artifacts
    /// and verifying signatures.
    public let verifier: CosignVerifier

    public init(
        repo: String,
        binaryName: String,
        downloadBaseURL: String = "",
        identityRegexp: String = "",
        verifier: CosignVerifier? = nil
    ) {
        self.repo = repo
        self.binaryName = binaryName
        self.downloadBaseURL = downloadBaseURL
        self.identityRegexp = identityRegexp
        self.verifier = verifier ?? CosignCLIVerifier(
            repo: repo,
            binaryName: binaryName,
            downloadBaseURL: downloadBaseURL,
            identityRegexp: identityRegexp
        )
    }

    /// Returns the identity regexp, defaulting to a GitHub Actions release workflow pattern.
    public func identityRegexpOrDefault() -> String {
        if !identityRegexp.isEmpty { return identityRegexp }
        return #"https://github\.com/\#(repo)/\.github/workflows/release\.yml@refs/tags/v.*"#
    }

    /// Returns the download base URL, defaulting to the GitHub releases download path.
    public func downloadBaseURLOrDefault() -> String {
        if !downloadBaseURL.isEmpty { return downloadBaseURL }
        return "https://github.com/\(repo)/releases/download"
    }

    /// The signature filename for the given tag (e.g. "symvault_1.0.0_checksums.txt.sig").
    public func signatureFileName(tag: String) -> String {
        let v = tag.replacingOccurrences(of: "v", with: "", options: .anchored)
        return "\(binaryName)_\(v)_checksums.txt.sig"
    }

    /// The certificate filename for the given tag (e.g. "symvault_1.0.0_checksums.txt.pem").
    public func certificateFileName(tag: String) -> String {
        let v = tag.replacingOccurrences(of: "v", with: "", options: .anchored)
        return "\(binaryName)_\(v)_checksums.txt.pem"
    }

    /// Fetch the cosign signature for a release tag. Delegates to the verifier.
    public func fetchSignature(tag: String) async throws -> Data {
        return try await verifier.fetchSignature(tag: tag)
    }

    /// Fetch the cosign certificate for a release tag. Delegates to the verifier.
    public func fetchCertificate(tag: String) async throws -> Data {
        return try await verifier.fetchCertificate(tag: tag)
    }

    /// Verify a cosign signature on the given checksums content.
    public func verifySignature(content: Data, signature: Data, certificate: Data) async throws {
        try await verifier.verifySignature(content: content, signature: signature, certificate: certificate)
    }
}

/// Default `CosignVerifier` implementation that shells out to the `cosign` CLI.
/// Falls back gracefully with a clear error when cosign is not installed.
#if os(macOS)
public struct CosignCLIVerifier: CosignVerifier, Sendable {
    /// The GitHub repository slug.
    public let repo: String
    /// The artifact name.
    public let binaryName: String
    /// Base URL for downloading cosign artifacts.
    public let downloadBaseURL: String
    /// The certificate identity regexp.
    public let identityRegexp: String
    /// HTTP client for fetching artifacts.
    private let httpClient: UpdateHTTPClient

    /// The OIDC issuer for cosign keyless signatures.
    public static let oidcIssuer = "https://token.actions.githubusercontent.com"

    public init(
        repo: String,
        binaryName: String,
        downloadBaseURL: String = "",
        identityRegexp: String = "",
        httpClient: UpdateHTTPClient = URLSession.shared
    ) {
        self.repo = repo
        self.binaryName = binaryName
        self.downloadBaseURL = downloadBaseURL
        self.identityRegexp = identityRegexp
        self.httpClient = httpClient
    }

    private func downloadBaseURLOrDefault() -> String {
        if !downloadBaseURL.isEmpty { return downloadBaseURL }
        return "https://github.com/\(repo)/releases/download"
    }

    private func signatureFileName(tag: String) -> String {
        let v = tag.replacingOccurrences(of: "v", with: "", options: .anchored)
        return "\(binaryName)_\(v)_checksums.txt.sig"
    }

    private func certificateFileName(tag: String) -> String {
        let v = tag.replacingOccurrences(of: "v", with: "", options: .anchored)
        return "\(binaryName)_\(v)_checksums.txt.pem"
    }

    public func fetchSignature(tag: String) async throws -> Data {
        return try await fetchArtifact(tag: tag, fileName: signatureFileName(tag:), label: "signature")
    }

    public func fetchCertificate(tag: String) async throws -> Data {
        return try await fetchArtifact(tag: tag, fileName: certificateFileName(tag:), label: "certificate")
    }

    private func fetchArtifact(tag: String, fileName: (String) -> String, label: String) async throws -> Data {
        let v = tag.replacingOccurrences(of: "v", with: "", options: .anchored)
        guard !v.isEmpty else {
            throw UpdateApplierError.cosignVerificationFailed("Version must not be empty")
        }

        let name = fileName(tag)
        let base = downloadBaseURLOrDefault()
        let urlString = "\(base)/v\(v)/\(name)"

        guard let url = URL(string: urlString),
              url.scheme == "https" else {
            throw UpdateApplierError.cosignVerificationFailed(
                "Cosign \(label) URL must use HTTPS, got \(urlString)"
            )
        }

        var request = URLRequest(url: url, timeoutInterval: 30)
        request.httpMethod = "GET"

        let (data, response) = try await httpClient.data(for: request)

        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw UpdateApplierError.cosignVerificationFailed(
                "Fetch cosign \(label): HTTP \(http.statusCode)"
            )
        }

        return data
    }

    public func verifySignature(content: Data, signature: Data, certificate: Data) async throws {
        // Check if cosign CLI is available.
        let which = Process()
        which.executableURL = URL(fileURLWithPath: "/usr/bin/which")
        which.arguments = ["cosign"]

        let whichPipe = Pipe()
        which.standardOutput = whichPipe
        try? which.run()
        which.waitUntilExit()

        guard which.terminationStatus == 0 else {
            throw UpdateApplierError.cosignVerificationFailed(
                "cosign CLI not found — install cosign from https://docs.sigstore.dev to verify release signatures"
            )
        }

        // Write temp files.
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("cosign-verify-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: tempDir) }

        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)

        let contentPath = tempDir.appendingPathComponent("content").path
        let sigPath = tempDir.appendingPathComponent("signature.sig").path
        let certPath = tempDir.appendingPathComponent("certificate.pem").path

        try content.write(to: URL(fileURLWithPath: contentPath))
        try signature.write(to: URL(fileURLWithPath: sigPath))
        try certificate.write(to: URL(fileURLWithPath: certPath))

        // Run cosign verify-blob.
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = [
            "cosign", "verify-blob",
            "--certificate", certPath,
            "--signature", sigPath,
            "--certificate-identity-regexp", identityRegexp,
            "--certificate-oidc-issuer", CosignCLIVerifier.oidcIssuer,
            contentPath,
        ]

        let stderrPipe = Pipe()
        process.standardError = stderrPipe

        try process.run()
        process.waitUntilExit()

        guard process.terminationStatus == 0 else {
            let stderrData = try stderrPipe.fileHandleForReading.readToEnd() ?? Data()
            let stderrStr = String(decoding: stderrData, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
            throw UpdateApplierError.cosignVerificationFailed(
                "cosign verify-blob failed: \(stderrStr)"
            )
        }
    }
}
#endif

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
    /// Self-update is not supported for the detected install method.
    case unsupportedInstallMethod(InstallMethod, guidance: String)
    /// The asset is a .app bundle but installation required a writable /Applications.
    case applicationsNotWritable
    /// Failed to mount a DMG disk image.
    case dmgMountFailed(String)
    /// No .app bundle was found inside the DMG or ZIP archive.
    case appBundleNotFound
    /// Failed to copy the .app bundle to its destination.
    case appBundleCopyFailed(String)
    /// Cosign signature verification failed.
    case cosignVerificationFailed(String)
}

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
#if os(macOS)
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
        // 1. Select the asset matching os + arch.
        let asset = try selectAsset(from: release.assets)

        // 2. Optional install method detection.
        if checkInstallMethod, let path = targetPath {
            let method = UpdateApplier.detectInstallMethod(at: path)
            guard UpdateApplier.isSelfUpdateSupported(method) else {
                let guidance = UpdateApplier.guidance(for: method, binaryName: binaryName ?? asset.name)
                throw UpdateApplierError.unsupportedInstallMethod(method, guidance: guidance)
            }
        }

        // 3. Determine asset type.
        let assetType = detectAssetType(name: asset.name)

        // 4. Download and parse checksums.txt.
        let checksums = try await fetchChecksums(from: release.assets)

        // 4b. Optional cosign verification of checksums.
        if let cosign = cosignConfig {
            // Build the checksums data for verification.
            var checksumsData = ""
            for (name, sum) in checksums {
                checksumsData += "\(sum)  \(name)\n"
            }
            let sig = try await cosign.fetchSignature(tag: release.tagName)
            let cert = try await cosign.fetchCertificate(tag: release.tagName)
            try await cosign.verifySignature(
                content: Data(checksumsData.utf8),
                signature: sig,
                certificate: cert
            )
        }

        // 5. Look up the expected checksum for the selected asset.
        guard let expectedSum = checksums[asset.name] else {
            throw UpdateApplierError.checksumMismatch(
                assetName: asset.name,
                got: "<no entry in checksums.txt>",
                expected: "<any entry>"
            )
        }

        // 6. Download the asset to a temp file (with progress + streaming SHA256).
        let (tempURL, actualSum) = try await downloadToTemp(asset: asset)

        // 7. Verify the checksum.
        guard actualSum.lowercased() == expectedSum.lowercased() else {
            try? FileManager.default.removeItem(at: tempURL)
            throw UpdateApplierError.checksumMismatch(
                assetName: asset.name,
                got: actualSum.lowercased(),
                expected: expectedSum.lowercased()
            )
        }

        // 8. If it's a bundle, install it to /Applications.
        switch assetType {
        case .appBundleDMG:
            return try installDMG(at: tempURL, assetName: asset.name)
        case .appBundleZip:
            return try installZip(at: tempURL, assetName: asset.name)
        case .binary, .unknown:
            return tempURL
        }
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

    // MARK: - DMG installation

    /// Mount a DMG, copy the .app bundle to /Applications, and unmount.
    /// Uses `hdiutil` for mount/unmount operations.
    public func installDMG(at dmgURL: URL, assetName: String) throws -> URL {
        guard FileManager.default.isWritableFile(atPath: "/Applications") else {
            throw UpdateApplierError.applicationsNotWritable
        }

        // Mount the DMG.
        let mountResult = try mountDMG(at: dmgURL)
        defer {
            // Always try to unmount, even on error.
            _ = try? unmountDMG(at: mountResult.mountPoint)
        }

        // Find the .app bundle on the mounted volume.
        guard let appURL = findAppBundle(in: mountResult.mountPoint) else {
            throw UpdateApplierError.appBundleNotFound
        }

        let appName = appURL.lastPathComponent
        let destURL = URL(fileURLWithPath: "/Applications").appendingPathComponent(appName)

        // Remove existing .app if present (the running instance is already loaded).
        if FileManager.default.fileExists(atPath: destURL.path) {
            try? FileManager.default.removeItem(at: destURL)
        }

        // Copy the .app to /Applications.
        do {
            try FileManager.default.copyItem(at: appURL, to: destURL)
        } catch {
            throw UpdateApplierError.appBundleCopyFailed(
                "Failed to copy \(appURL.path) to \(destURL.path): \(error.localizedDescription)"
            )
        }

        // Remove quarantine attribute if present.
        _ = try? Process.run(
            URL(fileURLWithPath: "/usr/bin/xattr"),
            arguments: ["-d", "com.apple.quarantine", destURL.path]
        )

        return destURL
    }

    // MARK: - ZIP installation

    /// Extract a ZIP archive, find the .app bundle, and copy it to /Applications.
    public func installZip(at zipURL: URL, assetName: String) throws -> URL {
        guard FileManager.default.isWritableFile(atPath: "/Applications") else {
            throw UpdateApplierError.applicationsNotWritable
        }

        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("updateapply-zip-\(UUID().uuidString)")
        defer {
            try? FileManager.default.removeItem(at: tempDir)
        }

        // Create the temp extraction directory.
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)

        // Use `ditto` for ZIP extraction (more reliable than unzip for .app bundles).
        let dittoProcess = Process()
        dittoProcess.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        dittoProcess.arguments = ["-xk", zipURL.path, tempDir.path]
        try dittoProcess.run()
        dittoProcess.waitUntilExit()

        guard dittoProcess.terminationStatus == 0 else {
            throw UpdateApplierError.appBundleCopyFailed(
                "ditto extraction failed with exit code \(dittoProcess.terminationStatus)"
            )
        }

        // Find the .app bundle.
        guard let appURL = findAppBundle(in: tempDir) else {
            throw UpdateApplierError.appBundleNotFound
        }

        let appName = appURL.lastPathComponent
        let destURL = URL(fileURLWithPath: "/Applications").appendingPathComponent(appName)

        // Remove existing .app if present.
        if FileManager.default.fileExists(atPath: destURL.path) {
            try? FileManager.default.removeItem(at: destURL)
        }

        // Copy the .app to /Applications.
        do {
            try FileManager.default.copyItem(at: appURL, to: destURL)
        } catch {
            throw UpdateApplierError.appBundleCopyFailed(
                "Failed to copy \(appURL.path) to \(destURL.path): \(error.localizedDescription)"
            )
        }

        // Remove quarantine attribute.
        _ = try? Process.run(
            URL(fileURLWithPath: "/usr/bin/xattr"),
            arguments: ["-d", "com.apple.quarantine", destURL.path]
        )

        return destURL
    }

    // MARK: - DMG helpers

    /// Represents a mounted DMG volume.
    public struct DMGMountResult: Sendable {
        /// The mount point directory (e.g. "/Volumes/MyApp").
        public let mountPoint: URL
        /// The device identifier (e.g. "/dev/disk3s1").
        public let device: String
    }

    /// Mount a DMG using `hdiutil attach`.
    private func mountDMG(at dmgURL: URL) throws -> DMGMountResult {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/hdiutil")
        process.arguments = ["attach", "-nobrowse", "-readonly", "-plist", dmgURL.path]

        let pipe = Pipe()
        process.standardOutput = pipe

        try process.run()
        process.waitUntilExit()

        guard process.terminationStatus == 0 else {
            throw UpdateApplierError.dmgMountFailed(
                "hdiutil attach failed with exit code \(process.terminationStatus)"
            )
        }

        let data = try pipe.fileHandleForReading.readToEnd() ?? Data()
        let plist = try PropertyListSerialization.propertyList(from: data, options: [], format: nil)
        guard let dict = plist as? [String: Any],
              let entities = dict["system-entities"] as? [[String: Any]] else {
            throw UpdateApplierError.dmgMountFailed("Failed to parse hdiutil plist output")
        }

        // Find the mount point entity.
        for entity in entities {
            if let mountPoint = entity["mount-point"] as? String,
               let devEntry = entity["dev-entry"] as? String,
               !mountPoint.isEmpty {
                return DMGMountResult(
                    mountPoint: URL(fileURLWithPath: mountPoint),
                    device: devEntry
                )
            }
        }

        throw UpdateApplierError.dmgMountFailed("No mount point found in hdiutil output")
    }

    /// Unmount a DMG using `hdiutil detach`.
    private func unmountDMG(at mountPoint: URL) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/hdiutil")
        process.arguments = ["detach", mountPoint.path]
        try process.run()
        process.waitUntilExit()
    }

    /// Recursively search for a .app bundle in a directory.
    public func findAppBundle(in directory: URL) -> URL? {
        let enumerator = FileManager.default.enumerator(
            at: directory,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles, .skipsPackageDescendants]
        )

        while let url = enumerator?.nextObject() as? URL {
            if url.pathExtension.lowercased() == "app" {
                // Verify it's actually a bundle (has Contents/Info.plist).
                let infoPlist = url.appendingPathComponent("Contents/Info.plist")
                if FileManager.default.fileExists(atPath: infoPlist.path) {
                    return url
                }
            }
        }
        return nil
    }

    // MARK: - Install method detection

    /// Detect how a binary or app was installed at the given path.
    /// Swift port of corekit/installmethod.Detect.
    public static func detectInstallMethod(at binaryPath: String) -> InstallMethod {
        guard !binaryPath.isEmpty else { return .unknown }

        // Resolve symlinks.
        let realPath: String
        if let resolved = try? FileManager.default
            .destinationOfSymbolicLink(atPath: binaryPath) {
            realPath = resolved
        } else {
            realPath = binaryPath
        }

        // Normalize to absolute path.
        let absPath = URL(fileURLWithPath: realPath).standardized.path

        // Check env vars first.
        if let method = detectFromEnv(absPath) { return method }

        // Check path patterns.
        if let method = detectFromPath(absPath) { return method }

        // Check Cellar receipts.
        if absPath.contains("/Cellar/") { return .homebrew }

        // Check writability.
        return detectFromWritability(absPath)
    }

    /// Returns true only for `directDownload`.
    public static func isSelfUpdateSupported(_ method: InstallMethod) -> Bool {
        return method == .directDownload || method == .unknown
    }

    /// Returns actionable upgrade instructions for the given method.
    public static func guidance(for method: InstallMethod, binaryName: String) -> String {
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
#endif
