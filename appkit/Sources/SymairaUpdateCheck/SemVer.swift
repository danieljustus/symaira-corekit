import Foundation

/// Stable semantic version (no prerelease/build metadata), mirroring
/// corekit/updatecheck's `stableVersion` semantics: prerelease or otherwise
/// unparseable versions are rejected, so dev builds never see update nags.
public struct StableVersion: Sendable, Equatable, Comparable, CustomStringConvertible {
    public let major: Int
    public let minor: Int
    public let patch: Int

    public init?(_ raw: String) {
        var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.hasPrefix("v") || text.hasPrefix("V") {
            text = String(text.dropFirst())
        }
        // Reject prerelease/build metadata outright.
        guard !text.contains("-"), !text.contains("+") else { return nil }

        let parts = text.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 3,
              let major = Int(parts[0]),
              let minor = Int(parts[1]),
              let patch = Int(parts[2]),
              major >= 0, minor >= 0, patch >= 0
        else { return nil }

        self.major = major
        self.minor = minor
        self.patch = patch
    }

    public var description: String { "v\(major).\(minor).\(patch)" }

    public static func < (lhs: StableVersion, rhs: StableVersion) -> Bool {
        if lhs.major != rhs.major { return lhs.major < rhs.major }
        if lhs.minor != rhs.minor { return lhs.minor < rhs.minor }
        return lhs.patch < rhs.patch
    }
}
