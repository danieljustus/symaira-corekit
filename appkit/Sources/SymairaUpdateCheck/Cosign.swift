import Foundation

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

#if os(macOS)
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

    /// Returns the identity regexp, defaulting to a GitHub Actions release
    /// workflow pattern — mirrors `CosignConfig.identityRegexpOrDefault()`.
    func identityRegexpOrDefault() -> String {
        if !identityRegexp.isEmpty { return identityRegexp }
        return #"(?i)https://github\.com/\#(repo)/\.github/workflows/release\.yml@refs/tags/v.*"#
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
        // Resolve the identity regexp, falling back to the GitHub Actions
        // release workflow pattern when the caller left it empty.
        let resolvedRegexp = identityRegexpOrDefault()
        guard !resolvedRegexp.isEmpty else {
            throw UpdateApplierError.cosignVerificationFailed(
                "cosign certificate identity regexp must not be empty — configure CosignConfig.identityRegexp"
            )
        }

        // Resolve cosign from the process PATH. GUI-launched apps should
        // augment their environment (e.g. via CLIRunner.augmentedEnvironment)
        // before reaching this point so Homebrew-installed cosign is reachable.
        let envPath = ProcessInfo.processInfo.environment["PATH"] ?? ""
        let searchDirs = envPath.split(separator: ":").map(String.init)
        guard let cosignURL = searchDirs.lazy
            .map({ URL(fileURLWithPath: $0).appendingPathComponent("cosign") })
            .first(where: { FileManager.default.isExecutableFile(atPath: $0.path) })
        else {
            let searched = searchDirs.isEmpty ? "empty PATH" : searchDirs.joined(separator: ":")
            throw UpdateApplierError.cosignVerificationFailed(
                "cosign CLI not found — searched \(searched); install from https://docs.sigstore.dev"
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

        // Run cosign verify-blob (bounded — a hung network/GC stall cannot
        // block the update flow indefinitely).  Use the async subprocess
        // variant so the cooperative pool is not parked for the duration
        // of the cosign process (#94).
        let processResult = try await SubprocessRunner.runCheckedAsync(
            executable: cosignURL,
            arguments: [
                "--certificate", certPath,
                "--signature", sigPath,
                "--certificate-identity-regexp", resolvedRegexp,
                "--certificate-oidc-issuer", CosignCLIVerifier.oidcIssuer,
                contentPath,
            ]
        )

        guard processResult.exitCode == 0 else {
            // Full stderr goes to the dedicated diagnostic case so it stays
            // retrievable for logging, while the user-facing
            // `errorDescription` shows only a bounded first-line sample (#47).
            let stderrStr = String(decoding: processResult.stderr, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
            throw UpdateApplierError.cosignVerificationFailedDiagnostic(stderrStr)
        }
    }
}

// MARK: - CosignVerification

/// Internal helper that orchestrates cosign verification of a parsed
/// checksums manifest: fetches the signature and certificate for the
/// release tag and verifies them against the manifest content.
struct CosignVerification: Sendable {
    let config: CosignConfig

    /// Verify the cosign signature against the raw checksums bytes.
    /// The signature was created over the exact file content, so we must
    /// verify against those exact bytes — not a re-serialized dictionary
    /// whose key order may differ.
    func verify(rawChecksums: Data, tag: String) async throws {
        let sig = try await config.fetchSignature(tag: tag)
        let cert = try await config.fetchCertificate(tag: tag)
        try await config.verifySignature(
            content: rawChecksums,
            signature: sig,
            certificate: cert
        )
    }
}
#endif
