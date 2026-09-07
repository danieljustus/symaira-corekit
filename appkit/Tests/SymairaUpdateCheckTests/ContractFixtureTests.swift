import XCTest
@testable import SymairaUpdateCheck

/// Asserts `SymairaUpdateCheck` against `contracts/update_check_invariants.json`,
/// vendored from `symaira-corekit` (see `contracts/README.md`). This is the
/// Swift half of the shared Go<->Swift update-check contract documented in
/// corekit's `docs/cross-language-conventions.md`.
final class UpdateCheckContractFixtureTests: XCTestCase {
    private struct Fixture: Decodable {
        let cacheTTLHours: Int
        let cacheScope: String
        let cacheStorage: String
        let prereleaseAndBuildMetadataRejected: Bool
        let prereleaseAndBuildMetadataMarkers: [String]
        let apiDraftAndPrereleaseRejected: Bool
        let apiInvalidTagRejected: Bool
        let v0MajorGapSuppressed: Bool
        let checkFailureBehavior: String
        let defaultAPITimeoutSeconds: Int

        enum CodingKeys: String, CodingKey {
            case cacheTTLHours = "cache_ttl_hours"
            case cacheScope = "cache_scope"
            case cacheStorage = "cache_storage"
            case prereleaseAndBuildMetadataRejected = "prerelease_and_build_metadata_rejected"
            case prereleaseAndBuildMetadataMarkers = "prerelease_and_build_metadata_markers"
            case apiDraftAndPrereleaseRejected = "api_draft_and_prerelease_rejected"
            case apiInvalidTagRejected = "api_invalid_tag_rejected"
            case v0MajorGapSuppressed = "v0_major_gap_suppressed"
            case checkFailureBehavior = "check_failure_behavior"
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

        let platformCache = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        XCTAssertEqual(
            checker.cacheDirectory,
            platformCache.appendingPathComponent("symaira/updatecheck", isDirectory: true)
        )
    }

    func testDefaultAPITimeoutMatchesFixture() async throws {
        let fixture = try loadFixture()
        let client = FixtureRecordingHTTPClient()
        let cacheDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("appkit-contract-timeout-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: cacheDir) }
        let checker = UpdateChecker(owner: "danieljustus", repo: "x", client: client, cacheDirectory: cacheDir)

        _ = try await checker.check(currentVersion: "v0.9.0")
        let timeout = await client.recordedTimeout()
        XCTAssertEqual(timeout, TimeInterval(fixture.defaultAPITimeoutSeconds))
    }

    func testPersistentCacheMatchesFixture() async throws {
        let fixture = try loadFixture()
        XCTAssertEqual(fixture.cacheScope, "cross_process_per_repository")
        XCTAssertEqual(fixture.cacheStorage, "platform_cache_directory")

        let cacheDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("appkit-contract-cache-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: cacheDir) }

        let body = #"{"tag_name":"v0.10.0","html_url":"https://github.com/danieljustus/x/releases/tag/v0.10.0"}"#
        let first = UpdateChecker(
            owner: "danieljustus",
            repo: "x",
            client: FixtureStubHTTPClient(body: body, status: 200),
            cacheDirectory: cacheDir
        )
        let fetched = try await first.check(currentVersion: "v0.9.0")
        XCTAssertEqual(fetched?.tagName, "v0.10.0")

        let second = UpdateChecker(
            owner: "danieljustus",
            repo: "x",
            client: FixtureFailingHTTPClient(),
            cacheDirectory: cacheDir
        )
        let cached = try await second.check(currentVersion: "v0.9.0")
        XCTAssertEqual(cached?.tagName, "v0.10.0")

        let collisionA = UpdateChecker(owner: "a-b", repo: "c", cacheDirectory: cacheDir)
        let collisionB = UpdateChecker(owner: "a", repo: "b-c", cacheDirectory: cacheDir)
        XCTAssertNotEqual(collisionA.cacheFile, collisionB.cacheFile)

        let hostile = UpdateChecker(owner: "../outside", repo: "../../escape", cacheDirectory: cacheDir)
        XCTAssertEqual(
            hostile.cacheFile.deletingLastPathComponent().standardizedFileURL.path,
            cacheDir.standardizedFileURL.path
        )
        let filename = hostile.cacheFile.deletingPathExtension().lastPathComponent
        XCTAssertEqual(filename.count, 64)
        XCTAssertTrue(filename.allSatisfy { $0.isHexDigit })
    }

    func testCheckFailuresAreSurfacedPerFixture() async throws {
        let fixture = try loadFixture()
        XCTAssertEqual(fixture.checkFailureBehavior, "surfaced_to_caller")
        let checker = UpdateChecker(
            owner: "danieljustus",
            repo: "x",
            client: FixtureFailingHTTPClient(),
            cacheDirectory: FileManager.default.temporaryDirectory
                .appendingPathComponent("appkit-contract-failure-\(UUID().uuidString)")
        )
        do {
            _ = try await checker.check(currentVersion: "v0.9.0")
            XCTFail("check failure was swallowed")
        } catch {
            // Expected: the shared contract surfaces check failures to the caller.
        }
    }

    func testDraftAndPrereleaseAPIResponsesRejectedPerFixture() async throws {
        let fixture = try loadFixture()
        guard fixture.apiDraftAndPrereleaseRejected else {
            throw XCTSkip("fixture does not require draft/prerelease API response rejection")
        }
        for (name, flag) in [("draft", "draft"), ("prerelease", "prerelease")] {
            let body = "{\"tag_name\":\"v0.10.0\",\"html_url\":\"https://example.com\",\"\(flag)\":true}"
            let cacheDir = FileManager.default.temporaryDirectory
                .appendingPathComponent("appkit-contract-\(name)-\(UUID().uuidString)")
            defer { try? FileManager.default.removeItem(at: cacheDir) }
            let checker = UpdateChecker(
                owner: "danieljustus",
                repo: "x",
                client: FixtureStubHTTPClient(body: body, status: 200),
                cacheDirectory: cacheDir
            )
            do {
                _ = try await checker.check(currentVersion: "v0.9.0")
                XCTFail("\(name) API response was accepted")
            } catch {
                // Expected.
            }
        }
    }

    func testInvalidAPIReleaseTagRejectedPerFixture() async throws {
        let fixture = try loadFixture()
        guard fixture.apiInvalidTagRejected else {
            throw XCTSkip("fixture does not require invalid API tag rejection")
        }
        let cacheDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("appkit-contract-invalid-tag-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: cacheDir) }
        let body = #"{"tag_name":"not-semver","html_url":"https://example.com"}"#
        let checker = UpdateChecker(
            owner: "danieljustus",
            repo: "x",
            client: FixtureStubHTTPClient(body: body, status: 200),
            cacheDirectory: cacheDir
        )
        do {
            _ = try await checker.check(currentVersion: "v0.9.0")
            XCTFail("invalid API release tag was accepted")
        } catch UpdateCheckError.invalidReleaseTag(let tag) {
            XCTAssertEqual(tag, "not-semver")
        } catch {
            XCTFail("unexpected invalid-tag error: \(error)")
        }

        if FileManager.default.fileExists(atPath: cacheDir.path) {
            let cachedFiles = try FileManager.default.contentsOfDirectory(atPath: cacheDir.path)
            XCTAssertTrue(cachedFiles.isEmpty, "invalid API response must not be cached")
        }

        let validBody = #"{"tag_name":"v0.10.0","html_url":"https://example.com"}"#
        let retry = UpdateChecker(
            owner: "danieljustus",
            repo: "x",
            client: FixtureStubHTTPClient(body: validBody, status: 200),
            cacheDirectory: cacheDir
        )
        let release = try await retry.check(currentVersion: "v0.9.0")
        XCTAssertEqual(release?.tagName, "v0.10.0")
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

    /// Fixed in danieljustus/symaira-appkit#116: `UpdateChecker.check` now
    /// mirrors corekit's `Checker.Check` v0-major-gap suppression.
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

        let release = try await checker.check(currentVersion: "v0.9.0")
        XCTAssertNil(release, "a v0.x consumer should not be offered a v1.0.0+ release")
    }

    /// Companion to the suppression test above: the v0-major-gap check must
    /// not swallow a normal same-major update.
    func testNormalV0UpdateStillOffered() async throws {
        let fixture = try loadFixture()
        guard fixture.v0MajorGapSuppressed else {
            throw XCTSkip("fixture does not claim v0-major gap suppression")
        }

        let cacheDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("appkit-contract-v0update-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: cacheDir) }

        let body = #"{"tag_name":"v0.10.0","html_url":"https://github.com/danieljustus/x/releases/tag/v0.10.0"}"#
        let client = FixtureStubHTTPClient(body: body, status: 200)
        let checker = UpdateChecker(owner: "danieljustus", repo: "x", client: client, cacheDirectory: cacheDir)

        let release = try await checker.check(currentVersion: "v0.9.0")
        XCTAssertEqual(release?.tagName, "v0.10.0", "a same-major v0.x -> v0.y update should still be offered")
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

private actor FixtureRecordingHTTPClient: UpdateHTTPClient {
    private var timeout: TimeInterval?

    func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        timeout = request.timeoutInterval
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: 200,
            httpVersion: nil,
            headerFields: nil
        )!
        let body = #"{"tag_name":"v0.10.0","html_url":"https://example.com"}"#
        return (Data(body.utf8), response)
    }

    func recordedTimeout() -> TimeInterval? {
        timeout
    }
}

private struct FixtureFailingHTTPClient: UpdateHTTPClient {
    struct UnexpectedRequest: Error {}

    func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        throw UnexpectedRequest()
    }
}
