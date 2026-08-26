import XCTest
@testable import SymairaUpdateCheck

/// Asserts `SymairaUpdateCheck` against `contracts/update_check_invariants.json`,
/// vendored from `symaira-corekit` (see `contracts/README.md`). This is the
/// Swift half of the shared Go<->Swift update-check contract documented in
/// corekit's `docs/cross-language-conventions.md`.
final class UpdateCheckContractFixtureTests: XCTestCase {
    private struct Fixture: Decodable {
        let cacheTTLHours: Int
        let prereleaseAndBuildMetadataRejected: Bool
        let prereleaseAndBuildMetadataMarkers: [String]
        let v0MajorGapSuppressed: Bool
        let defaultAPITimeoutSeconds: Int

        enum CodingKeys: String, CodingKey {
            case cacheTTLHours = "cache_ttl_hours"
            case prereleaseAndBuildMetadataRejected = "prerelease_and_build_metadata_rejected"
            case prereleaseAndBuildMetadataMarkers = "prerelease_and_build_metadata_markers"
            case v0MajorGapSuppressed = "v0_major_gap_suppressed"
            case defaultAPITimeoutSeconds = "default_api_timeout_seconds"
        }
    }

    private func loadFixture() throws -> Fixture {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // ContractFixtureTests.swift
            .deletingLastPathComponent() // SymairaUpdateCheckTests
            .deletingLastPathComponent() // Tests
            .appendingPathComponent("contracts/update_check_invariants.json")
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(Fixture.self, from: data)
    }

    func testDefaultCacheTTLMatchesFixture() throws {
        let fixture = try loadFixture()
        let checker = UpdateChecker(owner: "danieljustus", repo: "x")
        XCTAssertEqual(checker.cacheTTL, TimeInterval(fixture.cacheTTLHours * 60 * 60))
    }

    func testPrereleaseAndBuildMetadataRejectedPerFixture() throws {
        let fixture = try loadFixture()
        guard fixture.prereleaseAndBuildMetadataRejected else {
            throw XCTSkip("fixture does not claim prerelease rejection")
        }

        for marker in fixture.prereleaseAndBuildMetadataMarkers {
            let raw = "1.2.3\(marker)extra"
            XCTAssertNil(StableVersion(raw), "StableVersion(\"\(raw)\") should be rejected per fixture marker \"\(marker)\"")
        }
        XCTAssertNotNil(StableVersion("1.2.3"), "a plain stable version should still parse")
    }

    /// KNOWN DIVERGENCE — tracked in danieljustus/symaira-appkit#116.
    ///
    /// corekit's `Checker.Check` suppresses offering a release when
    /// `current.major == 0 && latest.major > 0` (see corekit's
    /// `updatecheck.go`). `UpdateChecker.check` has no equivalent check, so
    /// this currently fails. Per danieljustus/symaira-appkit#105's scope,
    /// a fixture-revealed divergence is fixed in its own issue with its own
    /// reasoning, not silently patched here or hidden by bending the
    /// fixture — hence `XCTExpectFailure` instead of a passing assertion.
    /// Remove the `XCTExpectFailure` wrapper once #116 lands; if this
    /// unexpectedly *passes* in the meantime, that's your signal #116 is
    /// already fixed.
    func testV0MajorGapSuppressedPerFixture() async throws {
        let fixture = try loadFixture()
        guard fixture.v0MajorGapSuppressed else {
            throw XCTSkip("fixture does not claim v0-major gap suppression")
        }

        let cacheDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("appkit-contract-v0gap-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: cacheDir) }

        let body = #"{"tag_name":"v1.0.0","html_url":"https://github.com/danieljustus/x/releases/tag/v1.0.0"}"#
        let client = FixtureStubHTTPClient(body: body, status: 200)
        let checker = UpdateChecker(owner: "danieljustus", repo: "x", client: client, cacheDirectory: cacheDir)

        // The async fetch itself doesn't fail today — only the assertion
        // below does, since `check` wrongly returns the v1.0.0 release. Keep
        // the await outside XCTExpectFailure to avoid Swift's ambiguity
        // between its sync- and async-closure overloads.
        let release = try await checker.check(currentVersion: "v0.9.0")

        XCTExpectFailure("known divergence from the documented contract — see danieljustus/symaira-appkit#116") {
            XCTAssertNil(release, "a v0.x consumer should not be offered a v1.0.0+ release")
        }
    }
}

private struct FixtureStubHTTPClient: UpdateHTTPClient {
    let body: String
    let status: Int

    func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: status,
            httpVersion: nil,
            headerFields: nil
        )!
        return (Data(body.utf8), response)
    }
}
