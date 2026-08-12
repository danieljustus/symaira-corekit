import Foundation

#if os(macOS)
// MARK: - ChecksumManifest

/// Internal parser for GoReleaser-style checksums.txt manifests.
enum ChecksumManifest {

    /// Locate the checksums asset in a release's assets. Prefers the exact
    /// name "checksums.txt" (GoReleaser convention), falling back to any
    /// asset containing "checksums" in its name.
    static func locateAsset(in assets: [Asset]) throws -> Asset {
        guard let checksumAsset = assets.first(where: {
            $0.name == "checksums.txt"
        }) ?? assets.first(where: {
            $0.name.lowercased().contains("checksums")
        }) else {
            throw UpdateApplierError.missingChecksumsAsset
        }
        return checksumAsset
    }

    /// Parse checksums.txt content into a `[filename: sha256hex]` dictionary.
    /// Lines are "<sha256hex>  <filename>" (goreleaser format); malformed
    /// lines are skipped.
    static func parse(_ text: String) -> [String: String] {
        var sums: [String: String] = [:]
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
        return sums
    }
}
#endif
