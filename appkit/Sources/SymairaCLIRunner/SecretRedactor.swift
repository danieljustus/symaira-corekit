import Foundation

/// Redacts credentials from errors, diagnostics and host-provided log output.
public enum SymairaSecretRedactor {
    /// The single placeholder used by every Symaira redaction entry point.
    public static let placeholder = "[REDACTED]"

    private static let patterns: [NSRegularExpression] = [
        #"-----BEGIN [A-Z ]+-----[A-Za-z0-9+/=.\s]+?-----END [A-Z ]+-----"#,
        #"(sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{8,}|xox[baprs]-[A-Za-z0-9-]{8,}|AIza[0-9A-Za-z_-]{20,}|sk_live_[A-Za-z0-9]{10,}|(?:AKIA|ASIA)[0-9A-Z]{16})"#,
        #"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"#,
        #"[A-Za-z0-9+/=]{40,}"#,
        #"\b[0-9a-fA-F]{32,}\b"#,
        #"(?i)(authorization|bearer|api[_-]?key|token|secret|password|passwd|credential|auth)\s*[:=]\s*(\"[^\"]+\"|'[^']+'|\S{8,})"#,
        #"(?i)\bbearer\s+[A-Za-z0-9._-]{12,}"#,
        #"«redacted:[^»]*»"#,
    ].compactMap { try? NSRegularExpression(pattern: $0) }

    /// Redacts obvious credential shapes in `text`.
    public static func redact(
        _ text: String,
        maxBytes: Int? = nil,
        firstLineOnly: Bool = false
    ) -> String {
        var result = text
        for pattern in patterns {
            result = pattern.stringByReplacingMatches(
                in: result,
                range: NSRange(result.startIndex..., in: result),
                withTemplate: placeholder
            )
        }

        if firstLineOnly {
            result = result.split(separator: "\n", omittingEmptySubsequences: false).first.map(String.init) ?? result
        }

        guard let maxBytes else { return result }
        return bounded(result, maxBytes: maxBytes)
    }

    private static func bounded(_ text: String, maxBytes: Int) -> String {
        guard maxBytes > 0 else { return text.isEmpty ? "" : "…" }

        var byteCount = 0
        var result = ""
        for character in text {
            let characterBytes = String(character).utf8.count
            if byteCount + characterBytes > maxBytes { break }
            result.append(character)
            byteCount += characterBytes
        }
        if byteCount < text.utf8.count {
            result += "…"
        }
        return result
    }
}
