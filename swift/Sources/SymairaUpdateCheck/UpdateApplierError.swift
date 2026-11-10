import Foundation

#if os(macOS)
// MARK: - Errors

/// Typed errors that can occur during the update application process.
public enum UpdateApplierError: Error, LocalizedError, Sendable, Equatable {
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
    /// Cosign signature verification failed. The associated value is a
    /// bounded, user-facing message.
    case cosignVerificationFailed(String)
    /// `cosign verify-blob` failed. The associated value is the **full**,
    /// unbounded raw stderr (capped only by the subprocess output limit)
    /// and is intended for diagnostics/logging, **not** for user-facing
    /// UI. Retrieve it via `cosignDiagnosticStderr`; the user-facing
    /// `errorDescription` shows only a bounded first-line sample.
    case cosignVerificationFailedDiagnostic(String)
    /// A subprocess spawned during the update timed out and was terminated
    /// (AGENTS.md loose-coupling rule: subprocess execution must always
    /// have a timeout).
    case subprocessTimeout(String)
}

// MARK: - LocalizedError + diagnostics

extension UpdateApplierError {
    /// The full, raw `cosign verify-blob` stderr for the
    /// `cosignVerificationFailedDiagnostic` case. Never bounded, never
    /// redacted — use for logging/diagnostics, not for UI. Mirrors
    /// `CLIRunnerError.fullStderr`.
    public var cosignDiagnosticStderr: String? {
        guard case .cosignVerificationFailedDiagnostic(let stderr) = self else { return nil }
        return stderr
    }

    /// User-facing description. For `cosignVerificationFailedDiagnostic`
    /// only a bounded, redacted first-line sample of stderr is shown
    /// (mirrors `CLIRunnerError.errorDescription`); every other case
    /// surfaces its existing message.
    public var errorDescription: String? {
        switch self {
        case .downloadFailed(let message):
            return message
        case .checksumMismatch(let assetName, let got, let expected):
            return "Checksum mismatch for \(assetName): got \(got), expected \(expected)."
        case .noMatchingAsset(let os, let arch):
            return "No release asset matches \(os)/\(arch)."
        case .destinationNotWritable(let message):
            return message
        case .missingChecksumsAsset:
            return "The release has no checksums.txt asset."
        case .unparseableChecksums:
            return "The checksums.txt file contained no parseable entries."
        case .httpStatus(let code):
            return "HTTP error \(code)."
        case .unsupportedInstallMethod(_, let guidance):
            return guidance
        case .applicationsNotWritable:
            return "/Applications is not writable."
        case .dmgMountFailed(let message):
            return message
        case .appBundleNotFound:
            return "No .app bundle was found inside the archive."
        case .appBundleCopyFailed(let message):
            return message
        case .cosignVerificationFailed(let message):
            return message
        case .cosignVerificationFailedDiagnostic(let stderr):
            return "cosign verify-blob failed: \(Self.boundedUserFacingSample(stderr))"
        case .subprocessTimeout(let command):
            return "Subprocess timed out: \(command)."
        }
    }

    /// Returns a redacted, length-bounded version of raw subprocess stderr
    /// suitable for a user-facing error message (mirrors
    /// `CLIRunnerError.redactedForUser`):
    /// - PEM blocks and obvious secret shapes are replaced with `[REDACTED]`;
    /// - only the first line is kept;
    /// - the result is truncated to `maxBytes` UTF-8 bytes (never splitting
    ///   a multi-byte codepoint), with an ellipsis when truncated.
    static func boundedUserFacingSample(_ raw: String, maxBytes: Int = 200) -> String {
        var redacted = raw

        // 1. Redact PEM blocks (multiline — must happen before splitting to
        //    first line, otherwise BEGIN/END markers span lines).
        let pemPattern = #"-----BEGIN [A-Z ]+-----[A-Za-z0-9+/=.\s]+?-----END [A-Z ]+-----"#
        if let regex = try? NSRegularExpression(pattern: pemPattern, options: [.dotMatchesLineSeparators]) {
            redacted = regex.stringByReplacingMatches(
                in: redacted,
                range: NSRange(redacted.startIndex..., in: redacted),
                withTemplate: "[REDACTED]"
            )
        }

        // 2. Keep only the first line for the user-facing message.
        if let firstLine = redacted.split(separator: "\n", omittingEmptySubsequences: false).first {
            redacted = String(firstLine)
        }

        // 3. Long base64-like tokens (40+ chars of base64 alphabet).
        let b64Pattern = #"[A-Za-z0-9+/=]{40,}"#
        if let regex = try? NSRegularExpression(pattern: b64Pattern, options: []) {
            redacted = regex.stringByReplacingMatches(
                in: redacted,
                range: NSRange(redacted.startIndex..., in: redacted),
                withTemplate: "[REDACTED]"
            )
        }

        // 4. Long hex strings (32+ hex chars).
        let hexPattern = #"\b[0-9a-fA-F]{32,}\b"#
        if let regex = try? NSRegularExpression(pattern: hexPattern, options: []) {
            redacted = regex.stringByReplacingMatches(
                in: redacted,
                range: NSRange(redacted.startIndex..., in: redacted),
                withTemplate: "[REDACTED]"
            )
        }

        // 5. Key-prefixed secrets: KEY=..., token: ..., secret=..., etc.
        let keyValuePattern = #"(?:api[_-]?key|apikey|secret|token|password|passwd|credential|auth)\s*[=:]\s*\S{8,}"#
        if let regex = try? NSRegularExpression(pattern: keyValuePattern, options: [.caseInsensitive]) {
            redacted = regex.stringByReplacingMatches(
                in: redacted,
                range: NSRange(redacted.startIndex..., in: redacted),
                withTemplate: "[REDACTED]"
            )
        }

        // 6. Truncate to maxBytes (UTF-8). Walk character by character so
        //    we never split a multi-byte codepoint.
        var byteCount = 0
        var result = ""
        for ch in redacted {
            let chBytes = String(ch).utf8.count
            if byteCount + chBytes > maxBytes { break }
            result.append(ch)
            byteCount += chBytes
        }
        if byteCount < redacted.utf8.count {
            result += "…"
        }
        return result
    }
}
#endif
