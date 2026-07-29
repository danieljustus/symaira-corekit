import XCTest
import CryptoKit
@testable import SymairaUpdateCheck

// MARK: - SHA256 helper

private func sha256Hex(_ data: Data) -> String {
    let digest = SHA256.hash(data: data)
    return digest.compactMap { String(format: "%02x", $0) }.joined()
}

// MARK: - Stub HTTP client

/// An HTTP client stub that maps URL path components to responses.
private final class StubUpdateHTTPClient: UpdateHTTPClient, @unchecked Sendable {
    var responses: [String: (Data, Int)] = [:]

    func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        guard let url = request.url else {
            throw URLError(.badURL)
        }
        let path = url.path
        guard let (body, status) = responses[path] else {
            let response = HTTPURLResponse(
                url: url,
                statusCode: 404,
                httpVersion: nil,
                headerFields: nil
            )!
            return (Data(), response)
        }
        let response = HTTPURLResponse(
            url: url,
            statusCode: status,
            httpVersion: nil,
            headerFields: ["Content-Length": "\(body.count)"]
        )!
        return (body, response)
    }

    func setResponse(path: String, body: Data, status: Int = 200) {
        responses[path] = (body, status)
    }
}

// MARK: - Test helpers

/// A sendable box for capturing values inside progress callbacks.
private final class ProgressBox: @unchecked Sendable {
    var lastWritten: Int64 = -1
}

private func makeRelease(
    assetName: String = "mytool_darwin_arm64",
    assetURL: String,
    checksumsURL: String? = nil,
    checksumsBody: String? = nil
) -> ReleaseInfo {
    let assets: [Asset] = [
        Asset(name: assetName, browserDownloadURL: assetURL, size: 0)
    ]
    // Add a checksums asset that won't be selected by selectAsset (it gets skipped).
    // The real checksums asset is handled separately.
    return ReleaseInfo(tagName: "v1.2.0", htmlURL: "https://github.com/example/releases/tag/v1.2.0", assets: assets)
}

// MARK: - UpdateApplierTests

final class UpdateApplierTests: XCTestCase {

    // MARK: - Successful download + verify

    func testSuccessfulDownloadAndVerify() async throws {
        let assetBody = Data("fake-binary-content".utf8)
        let expectedSum = sha256Hex(assetBody)

        let client = StubUpdateHTTPClient()
        // checksums.txt
        let checksumsText = "\(expectedSum)  mytool_darwin_arm64\n"
        client.setResponse(path: "/checksums.txt", body: Data(checksumsText.utf8))
        // the binary asset
        client.setResponse(path: "/asset", body: assetBody)

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/asset", size: Int64(assetBody.count)),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client
        )

        let result = try await applier.apply(release: release)
        defer { try? FileManager.default.removeItem(at: result) }

        let downloaded = try Data(contentsOf: result)
        XCTAssertEqual(downloaded, assetBody, "downloaded file should match asset body")
    }

    // MARK: - Progress callback

    func testProgressCallbackIsInvoked() async throws {
        let assetBody = Data("progress-test-binary".utf8)
        let expectedSum = sha256Hex(assetBody)
        let checksumsText = "\(expectedSum)  mytool_darwin_arm64\n"

        let client = StubUpdateHTTPClient()
        client.setResponse(path: "/checksums.txt", body: Data(checksumsText.utf8))
        client.setResponse(path: "/asset", body: assetBody)

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/asset", size: Int64(assetBody.count)),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        let progressExpectation = expectation(description: "progress called at least once")
        let box = ProgressBox()

        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client,
            progress: { written, total in
                box.lastWritten = written
                progressExpectation.fulfill()
            }
        )

        let result = try await applier.apply(release: release)
        defer { try? FileManager.default.removeItem(at: result) }

        await fulfillment(of: [progressExpectation], timeout: 2.0)
        XCTAssertEqual(box.lastWritten, Int64(assetBody.count), "progress should report final written bytes")
    }

    // MARK: - Checksum mismatch

    func testChecksumMismatchThrowsError() async throws {
        let assetBody = Data("real-binary-content".utf8)
        let wrongChecksum = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

        let client = StubUpdateHTTPClient()
        client.setResponse(path: "/checksums.txt", body: Data("\(wrongChecksum)  mytool_darwin_arm64\n".utf8))
        client.setResponse(path: "/asset", body: assetBody)

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/asset", size: Int64(assetBody.count)),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client
        )

        do {
            _ = try await applier.apply(release: release)
            XCTFail("expected checksumMismatch error")
        } catch UpdateApplierError.checksumMismatch(let assetName, let got, let expected) {
            XCTAssertEqual(assetName, "mytool_darwin_arm64")
            XCTAssertNotEqual(got, expected, "got and expected checksums should differ")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - Missing checksums asset

    func testMissingChecksumsAssetThrowsError() async throws {
        let client = StubUpdateHTTPClient()
        client.setResponse(path: "/asset", body: Data("some-binary".utf8))

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/asset", size: 0),
                // No checksums.txt asset
            ]
        )

        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client
        )

        do {
            _ = try await applier.apply(release: release)
            XCTFail("expected missingChecksumsAsset error")
        } catch UpdateApplierError.missingChecksumsAsset {
            // expected
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - Missing platform asset

    func testNoMatchingAssetThrowsError() async throws {
        let client = StubUpdateHTTPClient()

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_linux_amd64", browserDownloadURL: "https://example.com/asset", size: 0),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        // Target darwin/arm64 but only linux/amd64 assets exist.
        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client
        )

        do {
            _ = try await applier.apply(release: release)
            XCTFail("expected noMatchingAsset error")
        } catch UpdateApplierError.noMatchingAsset(let os, let arch) {
            XCTAssertEqual(os, "darwin")
            XCTAssertEqual(arch, "arm64")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - Unparseable checksums

    func testUnparseableChecksumsThrowsError() async throws {
        let assetBody = Data("fake-binary-content".utf8)
        let client = StubUpdateHTTPClient()
        // checksums.txt with no valid lines
        client.setResponse(path: "/checksums.txt", body: Data("not a valid checksums file\n".utf8))
        client.setResponse(path: "/asset", body: assetBody)

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/asset", size: Int64(assetBody.count)),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client
        )

        do {
            _ = try await applier.apply(release: release)
            XCTFail("expected unparseableChecksums error")
        } catch UpdateApplierError.unparseableChecksums {
            // expected
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - Checksums has no entry for selected asset

    func testChecksumEntryMissingForAsset() async throws {
        let assetBody = Data("fake-binary-content".utf8)
        let expectedSum = sha256Hex(assetBody)
        // checksums.txt lists a different asset.
        let checksumsText = "\(expectedSum)  some_other_asset\n"
        let client = StubUpdateHTTPClient()
        client.setResponse(path: "/checksums.txt", body: Data(checksumsText.utf8))
        client.setResponse(path: "/asset", body: assetBody)

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/asset", size: Int64(assetBody.count)),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client
        )

        do {
            _ = try await applier.apply(release: release)
            XCTFail("expected checksumMismatch (missing entry) error")
        } catch UpdateApplierError.checksumMismatch {
            // expected — no checksum entry for the selected asset
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - HTTP error on asset download

    func testHTTPErrorOnAssetDownload() async throws {
        let client = StubUpdateHTTPClient()
        // checksums is fine
        let checksumsText = "abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abc1  mytool_darwin_arm64\n"
        client.setResponse(path: "/checksums.txt", body: Data(checksumsText.utf8))
        // asset returns 500
        client.setResponse(path: "/asset", body: Data(), status: 500)

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/asset", size: 0),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client
        )

        do {
            _ = try await applier.apply(release: release)
            XCTFail("expected httpStatus error")
        } catch UpdateApplierError.httpStatus(let code) {
            XCTAssertEqual(code, 500)
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - selectAsset skips checksums files

    func testSelectAssetSkipsChecksumsFile() async throws {
        let assetBody = Data("binary".utf8)
        let expectedSum = sha256Hex(assetBody)
        let checksumsText = "\(expectedSum)  mytool_darwin_arm64\n"

        let client = StubUpdateHTTPClient()
        client.setResponse(path: "/checksums.txt", body: Data(checksumsText.utf8))
        client.setResponse(path: "/binary", body: assetBody)

        // Put checksums-like asset first, then the real asset.
        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64_checksums.txt", browserDownloadURL: "https://example.com/other", size: 0),
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/binary", size: Int64(assetBody.count)),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client
        )

        let result = try await applier.apply(release: release)
        defer { try? FileManager.default.removeItem(at: result) }

        let downloaded = try Data(contentsOf: result)
        XCTAssertEqual(downloaded, assetBody)
    }

    // MARK: - Invalid URL

    func testInvalidURLThrowsDownloadFailed() async throws {
        let client = StubUpdateHTTPClient()
        // checksums is fine
        let checksumsText = "abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abc1  mytool_darwin_arm64\n"
        client.setResponse(path: "/checksums.txt", body: Data(checksumsText.utf8))

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                // Empty URL string that fails URL(string:) parsing.
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "", size: 0),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client
        )

        do {
            _ = try await applier.apply(release: release)
            XCTFail("expected downloadFailed error")
        } catch UpdateApplierError.downloadFailed {
            // expected
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - Default OS/arch

    func testDefaultOSArchUsesCurrentPlatform() {
        let applier = UpdateApplier()

        // On macOS arm64 build machine:
#if os(macOS)
        XCTAssertEqual(applier.os, "darwin")
#elseif os(Linux)
        XCTAssertEqual(applier.os, "linux")
#endif

#if arch(arm64)
        XCTAssertEqual(applier.arch, "arm64")
#elseif arch(x86_64)
        XCTAssertEqual(applier.arch, "amd64")
#endif
    }
}
