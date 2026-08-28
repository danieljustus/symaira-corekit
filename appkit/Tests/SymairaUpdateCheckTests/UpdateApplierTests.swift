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
    /// Per-path Content-Length overrides used to simulate truncated
    /// downloads (the client normally reports the true body size).
    var contentLengthOverrides: [String: Int64] = [:]

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
        let contentLength = contentLengthOverrides[path] ?? Int64(body.count)
        let response = HTTPURLResponse(
            url: url,
            statusCode: status,
            httpVersion: nil,
            headerFields: ["Content-Length": "\(contentLength)"]
        )!
        return (body, response)
    }

    func setResponse(path: String, body: Data, status: Int = 200) {
        responses[path] = (body, status)
    }
}

// MARK: - Test helpers

/// A sendable box for capturing values inside progress callbacks.
final class ProgressBox: @unchecked Sendable {
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

// MARK: - Streaming stub HTTP client (#74)

/// A simple thread-safe counter for asserting chunk/progress counts.
final class CounterBox: @unchecked Sendable {
    var count = 0
}

/// Yields `data` in `chunkSize`-byte slices, counting each consumed slice.
struct SlicedByteStream: UpdateByteStream {
    private let data: Data
    private let chunkSize: Int
    private let counter: CounterBox

    init(data: Data, chunkSize: Int, counter: CounterBox) {
        self.data = data
        self.chunkSize = chunkSize
        self.counter = counter
    }

    struct Iterator: AsyncIteratorProtocol {
        private let data: Data
        private let chunkSize: Int
        private let counter: CounterBox
        private var offset = 0

        init(data: Data, chunkSize: Int, counter: CounterBox) {
            self.data = data
            self.chunkSize = chunkSize
            self.counter = counter
        }

        mutating func next() async throws -> Data? {
            guard offset < data.count else { return nil }
            let end = Swift.min(offset + chunkSize, data.count)
            let slice = data.subdata(in: offset..<end)
            offset = end
            counter.count += 1
            return slice
        }
    }

    func makeAsyncIterator() -> Iterator {
        Iterator(data: data, chunkSize: chunkSize, counter: counter)
    }
}

/// An HTTP client stub that implements the streaming seam, delivering bodies
/// as `chunkSize`-byte chunks and recording how many chunks the caller
/// consumed (to prove early rejection / mid-stream aborts).
final class StreamingStubUpdateHTTPClient: UpdateHTTPStreamingClient, @unchecked Sendable {
    var responses: [String: (Data, Int)] = [:]
    /// Per-path Content-Length overrides used to simulate servers that
    /// advertise a body size that differs from what they send.
    var contentLengthOverrides: [String: Int64] = [:]
    /// Chunk size used to slice bodies for streaming delivery.
    var chunkSize: Int = 16
    /// Number of chunks consumed by the caller.
    let consumedChunks = CounterBox()

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
        let contentLength = contentLengthOverrides[path] ?? Int64(body.count)
        let response = HTTPURLResponse(
            url: url,
            statusCode: status,
            httpVersion: nil,
            headerFields: ["Content-Length": "\(contentLength)"]
        )!
        return (body, response)
    }

    func stream(for request: URLRequest) async throws -> (any UpdateByteStream, URLResponse) {
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
            return (SlicedByteStream(data: Data(), chunkSize: chunkSize, counter: consumedChunks), response)
        }
        let contentLength = contentLengthOverrides[path] ?? Int64(body.count)
        let response = HTTPURLResponse(
            url: url,
            statusCode: status,
            httpVersion: nil,
            headerFields: ["Content-Length": "\(contentLength)"]
        )!
        return (SlicedByteStream(data: body, chunkSize: chunkSize, counter: consumedChunks), response)
    }

    func setResponse(path: String, body: Data, status: Int = 200) {
        responses[path] = (body, status)
    }
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

    // MARK: - Asset type detection

    func testDetectAssetTypeDMG() {
        let applier = UpdateApplier()
        XCTAssertEqual(applier.detectAssetType(name: "MyApp_darwin_arm64.dmg"), .appBundleDMG)
        XCTAssertEqual(applier.detectAssetType(name: "MyApp.DMG"), .appBundleDMG)
    }

    func testDetectAssetTypeZIP() {
        let applier = UpdateApplier()
        XCTAssertEqual(applier.detectAssetType(name: "MyApp_darwin_arm64.zip"), .appBundleZip)
        XCTAssertEqual(applier.detectAssetType(name: "MyApp.ZIP"), .appBundleZip)
    }

    func testDetectAssetTypeBinary() {
        let applier = UpdateApplier()
        XCTAssertEqual(applier.detectAssetType(name: "mytool_darwin_arm64"), .binary)
        XCTAssertEqual(applier.detectAssetType(name: "mytool_darwin_arm64.tar.gz"), .binary)
        XCTAssertEqual(applier.detectAssetType(name: "mytool"), .binary)
    }

    // MARK: - Install method detection (stubbed - no real filesystem manipulation)

    func testDetectInstallMethodEmptyPath() {
        let method = UpdateApplier.detectInstallMethod(at: "")
        XCTAssertEqual(method, .unknown)
    }

    func testDetectInstallMethodHomebrewByPath() {
        let method = UpdateApplier.detectInstallMethod(at: "/opt/homebrew/bin/symvault")
        XCTAssertEqual(method, .homebrew)
    }

    func testDetectInstallMethodHomebrewByCellar() {
        let method = UpdateApplier.detectInstallMethod(at: "/usr/local/Cellar/symvault/1.0.0/bin/symvault")
        XCTAssertEqual(method, .homebrew)
    }

    func testDetectInstallMethodDirectDownloadByPath() {
        let method = UpdateApplier.detectInstallMethod(at: "/usr/local/bin/symvault")
        XCTAssertEqual(method, .directDownload)
    }

    func testDetectInstallMethodPackageManager() {
        let method = UpdateApplier.detectInstallMethod(at: "/usr/bin/symvault")
        XCTAssertEqual(method, .packageManager)
    }

    func testDetectInstallMethodGoInstallByPath() {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let method = UpdateApplier.detectInstallMethod(at: "\(home)/go/bin/symvault")
        XCTAssertEqual(method, .goInstall)
    }

    func testDetectInstallMethodUserBin() {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let method = UpdateApplier.detectInstallMethod(at: "\(home)/bin/symvault")
        XCTAssertEqual(method, .directDownload)
    }

    func testDetectInstallMethodLocalBin() {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let method = UpdateApplier.detectInstallMethod(at: "\(home)/.local/bin/symvault")
        XCTAssertEqual(method, .directDownload)
    }

    // MARK: - Self-update support

    func testIsSelfUpdateSupported() {
        XCTAssertTrue(UpdateApplier.isSelfUpdateSupported(.directDownload))
        XCTAssertTrue(UpdateApplier.isSelfUpdateSupported(.unknown))
        XCTAssertFalse(UpdateApplier.isSelfUpdateSupported(.homebrew))
        XCTAssertFalse(UpdateApplier.isSelfUpdateSupported(.goInstall))
        XCTAssertFalse(UpdateApplier.isSelfUpdateSupported(.packageManager))
        XCTAssertFalse(UpdateApplier.isSelfUpdateSupported(.buildFromSource))
    }

    func testGuidanceForHomebrew() {
        let msg = UpdateApplier.guidance(for: .homebrew, binaryName: "symvault")
        XCTAssertTrue(msg.contains("brew upgrade"))
        XCTAssertTrue(msg.contains("symvault"))
    }

    func testGuidanceForGoInstall() {
        let msg = UpdateApplier.guidance(for: .goInstall, binaryName: "symvault")
        XCTAssertTrue(msg.contains("go install"))
        XCTAssertTrue(msg.contains("symvault"))
    }

    // MARK: - findAppBundle (with temp directory)

    func testFindAppBundleInTempDirectory() throws {
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("updateapply-test-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: tempDir) }

        // Create a fake .app structure.
        let appDir = tempDir.appendingPathComponent("MyApp.app")
        let contentsDir = appDir.appendingPathComponent("Contents")
        try FileManager.default.createDirectory(at: contentsDir, withIntermediateDirectories: true)

        // Add an Info.plist so it's recognized as a valid app bundle.
        let plistPath = contentsDir.appendingPathComponent("Info.plist")
        let plistContent = """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0"><dict><key>CFBundleName</key><string>MyApp</string></dict></plist>
        """
        try Data(plistContent.utf8).write(to: plistPath)

        let applier = UpdateApplier()
        let found = applier.findAppBundle(in: tempDir)
        XCTAssertNotNil(found)
        XCTAssertEqual(found?.lastPathComponent, "MyApp.app")
    }

    func testFindAppBundleReturnsNilWhenNoneExist() throws {
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("updateapply-test-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: tempDir) }

        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)

        // Create a file that looks like .app but has no Info.plist.
        let fakeApp = tempDir.appendingPathComponent("NotARealApp.app")
        try Data("fake".utf8).write(to: fakeApp)

        let applier = UpdateApplier()
        let found = applier.findAppBundle(in: tempDir)
        XCTAssertNil(found)
    }

    // MARK: - applyBundle with binary asset (same as apply)

    func testApplyBundleWithBinaryAsset() async throws {
        let assetBody = Data("fake-binary-content".utf8)
        let expectedSum = sha256Hex(assetBody)

        let client = StubUpdateHTTPClient()
        let checksumsText = "\(expectedSum)  mytool_darwin_arm64\n"
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

        let applier = UpdateApplier(os: "darwin", arch: "arm64", client: client)
        let result = try await applier.applyBundle(release: release)
        defer { try? FileManager.default.removeItem(at: result) }

        let downloaded = try Data(contentsOf: result)
        XCTAssertEqual(downloaded, assetBody, "binary asset downloaded via applyBundle should match")
    }

    // MARK: - UpdateChecker payload/cache to applyBundle (#126)

    func testCachedReleaseAssetsFeedApplyBundle() async throws {
        let cacheDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("updateapply-cache-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: cacheDirectory) }

        let assetBody = Data("cached-bundle-payload".utf8)
        let checksum = sha256Hex(assetBody)
        let client = StubUpdateHTTPClient()
        let payload = """
        {"tag_name":"v1.2.0","html_url":"https://github.com/example/releases/tag/v1.2.0","assets":[{"name":"mytool_darwin_arm64","browser_download_url":"https://example.com/asset","size":\(assetBody.count)},{"name":"checksums.txt","browser_download_url":"https://example.com/checksums.txt","size":80}]}
        """
        client.setResponse(path: "/repos/example/mytool/releases/latest", body: Data(payload.utf8))
        client.setResponse(path: "/checksums.txt", body: Data("\(checksum)  mytool_darwin_arm64\n".utf8))
        client.setResponse(path: "/asset", body: assetBody)

        let freshChecker = UpdateChecker(
            owner: "example",
            repo: "mytool",
            client: client,
            cacheDirectory: cacheDirectory
        )
        _ = try await freshChecker.check(currentVersion: "v1.0.0", force: true)

        let cachedChecker = UpdateChecker(
            owner: "example",
            repo: "mytool",
            client: client,
            cacheDirectory: cacheDirectory
        )
        let cachedResult = try await cachedChecker.check(currentVersion: "v1.0.0")
        let release = try XCTUnwrap(cachedResult)
        XCTAssertEqual(release.assets.first?.browserDownloadURL, "https://example.com/asset")
        XCTAssertEqual(release.assets.first?.size, Int64(assetBody.count))

        let applier = UpdateApplier(os: "darwin", arch: "arm64", client: client)
        let result = try await applier.applyBundle(release: release)
        defer { try? FileManager.default.removeItem(at: result) }
        XCTAssertEqual(try Data(contentsOf: result), assetBody)
    }

    // MARK: - Install method rejection (with stub client)

    func testApplyBundleRejectsHomebrewWhenCheckEnabled() async throws {
        let homebrewPath = "/opt/homebrew/bin/symvault"

        let assetBody = Data("binary".utf8)
        let expectedSum = sha256Hex(assetBody)

        let client = StubUpdateHTTPClient()
        let checksumsText = "\(expectedSum)  mytool_darwin_arm64\n"
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

        let applier = UpdateApplier(os: "darwin", arch: "arm64", client: client, checkInstallMethod: true, binaryName: "symvault")

        do {
            _ = try await applier.applyBundle(release: release, targetPath: homebrewPath)
            XCTFail("expected unsupportedInstallMethod error for Homebrew")
        } catch UpdateApplierError.unsupportedInstallMethod(let method, guidance: let guidance) {
            XCTAssertEqual(method, .homebrew)
            XCTAssertTrue(guidance.contains("brew"), "guidance should mention brew")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - Init defaults

    func testInitDefaults() {
        let applier = UpdateApplier()
        XCTAssertFalse(applier.checkInstallMethod, "checkInstallMethod should default to false")
        XCTAssertNil(applier.binaryName)
    }

    func testInitWithCustomValues() {
        let applier = UpdateApplier(
            os: "linux",
            arch: "amd64",
            checkInstallMethod: true,
            binaryName: "testtool"
        )
        XCTAssertEqual(applier.os, "linux")
        XCTAssertEqual(applier.arch, "amd64")
        XCTAssertTrue(applier.checkInstallMethod)
        XCTAssertEqual(applier.binaryName, "testtool")
    }

    // MARK: - CosignConfig

    func testCosignConfigFilenameGeneration() {
        let cfg = CosignConfig(
            repo: "danieljustus/symaira-vault",
            binaryName: "symvault"
        )
        XCTAssertEqual(cfg.signatureFileName(tag: "v1.0.0"), "symvault_1.0.0_checksums.txt.sig")
        XCTAssertEqual(cfg.signatureFileName(tag: "1.0.0"), "symvault_1.0.0_checksums.txt.sig")
        XCTAssertEqual(cfg.certificateFileName(tag: "v2.3.4"), "symvault_2.3.4_checksums.txt.pem")
    }

    func testCosignConfigDefaultURL() {
        let cfg = CosignConfig(
            repo: "danieljustus/symaira-vault",
            binaryName: "symvault"
        )
        XCTAssertEqual(cfg.downloadBaseURLOrDefault(), "https://github.com/danieljustus/symaira-vault/releases/download")
    }

    func testCosignConfigCustomURL() {
        let cfg = CosignConfig(
            repo: "danieljustus/symaira-vault",
            binaryName: "symvault",
            downloadBaseURL: "https://releases.example.com"
        )
        XCTAssertEqual(cfg.downloadBaseURLOrDefault(), "https://releases.example.com")
    }

    func testCosignConfigDefaultIdentityRegexpAgreesWithCLIVerifier() {
        let config = CosignConfig(
            repo: "danieljustus/symaira-vault",
            binaryName: "symvault"
        )
        let cliVerifier = CosignCLIVerifier(
            repo: "danieljustus/symaira-vault",
            binaryName: "symvault"
        )

        XCTAssertEqual(config.identityRegexpOrDefault(), cliVerifier.identityRegexpOrDefault())
        XCTAssertEqual(config.downloadBaseURLOrDefault(), cliVerifier.downloadBaseURLOrDefault())
        XCTAssertEqual(config.signatureFileName(tag: "v2.3.4"), cliVerifier.signatureFileName(tag: "v2.3.4"))
        XCTAssertEqual(config.certificateFileName(tag: "v2.3.4"), cliVerifier.certificateFileName(tag: "v2.3.4"))
    }

    func testCosignConfigCustomIdentityRegexp() {
        let cfg = CosignConfig(
            repo: "danieljustus/symaira-vault",
            binaryName: "symvault",
            identityRegexp: "custom-pattern"
        )
        XCTAssertEqual(cfg.identityRegexpOrDefault(), "custom-pattern")
    }

    func testCosignConfigInitDefaults() {
        let cfg = CosignConfig(
            repo: "danieljustus/symaira-vault",
            binaryName: "symvault"
        )
        XCTAssertEqual(cfg.repo, "danieljustus/symaira-vault")
        XCTAssertEqual(cfg.binaryName, "symvault")
        XCTAssertEqual(cfg.downloadBaseURL, "")
        XCTAssertEqual(cfg.identityRegexp, "")
    }

    // MARK: - CosignVerifier stubs

    /// A stub CosignVerifier that always succeeds.
    private final class StubPassingCosignVerifier: CosignVerifier, @unchecked Sendable {
        func fetchSignature(tag: String) async throws -> Data {
            return Data("stub-signature".utf8)
        }
        func fetchCertificate(tag: String) async throws -> Data {
            return Data("stub-certificate".utf8)
        }
        func verifySignature(content: Data, signature: Data, certificate: Data) async throws {
            // Always passes.
        }
    }

    /// A stub CosignVerifier that always fails.
    private final class StubFailingCosignVerifier: CosignVerifier, @unchecked Sendable {
        func fetchSignature(tag: String) async throws -> Data {
            return Data("stub-signature".utf8)
        }
        func fetchCertificate(tag: String) async throws -> Data {
            return Data("stub-certificate".utf8)
        }
        func verifySignature(content: Data, signature: Data, certificate: Data) async throws {
            throw UpdateApplierError.cosignVerificationFailed("stub verification failure")
        }
    }

    /// A stub CosignVerifier that fails on missing signature.
    private final class StubMissingSignatureVerifier: CosignVerifier, @unchecked Sendable {
        var failOnFetch = false
        func fetchSignature(tag: String) async throws -> Data {
            if failOnFetch {
                throw UpdateApplierError.cosignVerificationFailed("signature not found")
            }
            return Data("stub-signature".utf8)
        }
        func fetchCertificate(tag: String) async throws -> Data {
            return Data("stub-certificate".utf8)
        }
        func verifySignature(content: Data, signature: Data, certificate: Data) async throws {
            // passes
        }
    }

    // MARK: - Cosign: applyBundle with valid signature

    func testApplyBundleWithValidCosignSignature() async throws {
        let assetBody = Data("fake-binary-content".utf8)
        let expectedSum = sha256Hex(assetBody)

        let client = StubUpdateHTTPClient()
        let checksumsText = "\(expectedSum)  mytool_darwin_arm64\n"
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

        let cosignCfg = CosignConfig(
            repo: "danieljustus/symaira-vault",
            binaryName: "symvault",
            verifier: StubPassingCosignVerifier()
        )

        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client,
            cosignConfig: cosignCfg
        )

        let result = try await applier.applyBundle(release: release)
        defer { try? FileManager.default.removeItem(at: result) }

        let downloaded = try Data(contentsOf: result)
        XCTAssertEqual(downloaded, assetBody)
    }

    // MARK: - Cosign: applyBundle with invalid signature

    func testApplyBundleRejectsOnInvalidCosignSignature() async throws {
        let assetBody = Data("fake-binary-content".utf8)
        let expectedSum = sha256Hex(assetBody)

        let client = StubUpdateHTTPClient()
        let checksumsText = "\(expectedSum)  mytool_darwin_arm64\n"
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

        let cosignCfg = CosignConfig(
            repo: "danieljustus/symaira-vault",
            binaryName: "symvault",
            verifier: StubFailingCosignVerifier()
        )

        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client,
            cosignConfig: cosignCfg
        )

        do {
            _ = try await applier.applyBundle(release: release)
            XCTFail("expected cosignVerificationFailed error")
        } catch UpdateApplierError.cosignVerificationFailed {
            // expected
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - Cosign: apply(release:) uses the shared verification pipeline

    func testApplyRejectsOnInvalidCosignSignature() async throws {
        let assetBody = Data("fake-binary-content".utf8)
        let expectedSum = sha256Hex(assetBody)
        let client = StubUpdateHTTPClient()
        client.setResponse(path: "/checksums.txt", body: Data("\(expectedSum)  mytool_darwin_arm64\n".utf8))
        client.setResponse(path: "/asset", body: assetBody)

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/asset", size: Int64(assetBody.count)),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )
        let cosignConfig = CosignConfig(
            repo: "danieljustus/symaira-vault",
            binaryName: "symvault",
            verifier: StubFailingCosignVerifier()
        )
        let applier = UpdateApplier(os: "darwin", arch: "arm64", client: client, cosignConfig: cosignConfig)

        do {
            _ = try await applier.apply(release: release)
            XCTFail("expected cosignVerificationFailed error")
        } catch UpdateApplierError.cosignVerificationFailed {
            // expected
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - Install-method checks use the shared verification pipeline

    func testApplyRejectsHomebrewWhenCheckEnabled() async throws {
        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/asset", size: 0),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )
        let applier = UpdateApplier(os: "darwin", arch: "arm64", checkInstallMethod: true)

        do {
            _ = try await applier.apply(release: release, targetPath: "/opt/homebrew/bin/mytool")
            XCTFail("expected unsupportedInstallMethod error for Homebrew")
        } catch UpdateApplierError.unsupportedInstallMethod(let method, guidance: _) {
            XCTAssertEqual(method, .homebrew)
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - Cosign: applyBundle with missing signature

    func testApplyBundleRejectsOnMissingCosignSignature() async throws {
        let assetBody = Data("fake-binary-content".utf8)
        let expectedSum = sha256Hex(assetBody)

        let client = StubUpdateHTTPClient()
        let checksumsText = "\(expectedSum)  mytool_darwin_arm64\n"
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

        let verifier = StubMissingSignatureVerifier()
        verifier.failOnFetch = true

        let cosignCfg = CosignConfig(
            repo: "danieljustus/symaira-vault",
            binaryName: "symvault",
            verifier: verifier
        )

        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client,
            cosignConfig: cosignCfg
        )

        do {
            _ = try await applier.applyBundle(release: release)
            XCTFail("expected cosignVerificationFailed error for missing signature")
        } catch UpdateApplierError.cosignVerificationFailed {
            // expected
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - Cosign error: bounded user-facing description, full diagnostic stderr (#47)

    func testCosignVerifyFailureDescriptionIsBoundedAndDiagnosticKeepsFullStderr() {
        let firstLine = "cosign: error: signature verification failed: exit status 1"
        let tailMarker = "TAIL-SECRET-JUNK-SHOULD-NOT-APPEAR"
        let hugeStderr = firstLine + "\n" + String(repeating: "junk", count: 200_000) + tailMarker

        let error = UpdateApplierError.cosignVerificationFailedDiagnostic(hugeStderr)

        // User-facing description: bounded, first line only.
        let description = error.localizedDescription
        XCTAssertLessThan(
            description.utf8.count,
            300,
            "user-facing description must stay bounded, got \(description.utf8.count) bytes"
        )
        XCTAssertTrue(
            description.contains("cosign: error: signature verification failed"),
            "first line must be preserved in the user-facing description"
        )
        XCTAssertFalse(
            description.contains(tailMarker),
            "stderr tail must not leak into the user-facing description"
        )

        // Full diagnostic data is still retrievable from the diagnostic field.
        XCTAssertEqual(error.cosignDiagnosticStderr, hugeStderr)
        guard case .cosignVerificationFailedDiagnostic(let diagnostic) = error else {
            return XCTFail("expected cosignVerificationFailedDiagnostic case")
        }
        XCTAssertEqual(diagnostic, hugeStderr, "diagnostic associated value must carry the full stderr")
    }

    func testCosignVerificationFailedCaseShapeUnchangedAndBounded() {
        // Existing consumers pattern-match `.cosignVerificationFailed(String)`;
        // the case shape and its bounded message must keep working (#47).
        let error = UpdateApplierError.cosignVerificationFailed(
            "cosign CLI not found — install cosign from https://docs.sigstore.dev to verify release signatures"
        )
        guard case .cosignVerificationFailed(let message) = error else {
            return XCTFail("expected cosignVerificationFailed case")
        }
        XCTAssertFalse(message.isEmpty)
        XCTAssertEqual(error.localizedDescription, message)
        XCTAssertNil(error.cosignDiagnosticStderr, "no diagnostic stderr attached to the plain case")
    }

    func testCosignErrorBoundedSampleRedactsAndTruncates() {
        // PEM blocks are redacted before first-line extraction. The marker
        // is assembled from parts so no literal PEM header appears verbatim
        // in the source (this is a synthetic test payload, not a real key).
        let pemBody = "MIIBVwIBADANBgkqhkiG9w0BAQEFAASC"
        let pem = "-----BEGIN PRIVATE " + "KEY-----\n" + pemBody + "\n" + "-----END PRIVATE " + "KEY-----\n"
        XCTAssertEqual(UpdateApplierError.boundedUserFacingSample(pem), "[REDACTED]")

        // Key-prefixed secrets on the first line are redacted.
        XCTAssertEqual(
            UpdateApplierError.boundedUserFacingSample("token=abcdefghijklmnopqrstuvwxyz123456"),
            "[REDACTED]"
        )

        // Oversized output is truncated to maxBytes (plus ellipsis). Use a
        // non-base64 payload so the redaction rules do not swallow it first.
        let long = String(repeating: "a-b", count: 4_000)
        let bounded = UpdateApplierError.boundedUserFacingSample(long)
        XCTAssertLessThanOrEqual(bounded.utf8.count, 204, "bounded sample must stay within maxBytes plus ellipsis")
        XCTAssertEqual(bounded.count, 201, "bounded sample should be maxBytes characters plus an ellipsis")
        XCTAssertTrue(bounded.hasSuffix("…"), "truncated sample should end with an ellipsis")

        // Only the first line survives.
        let multiLine = "first line\nsecond line with secret=abcdef1234567890"
        let firstOnly = UpdateApplierError.boundedUserFacingSample(multiLine)
        XCTAssertTrue(firstOnly.hasPrefix("first line"))
        XCTAssertFalse(firstOnly.contains("second line"))
    }

    // MARK: - Subprocess timeouts (AGENTS.md loose-coupling rule)

    func testSubprocessRunnerNormalExit() throws {
        let result = try SubprocessRunner.run(
            executable: URL(fileURLWithPath: "/bin/echo"),
            arguments: ["hello"],
            timeout: 10
        )

        XCTAssertFalse(result.timedOut, "fast child must not be flagged as timed out")
        XCTAssertEqual(result.exitCode, 0)
        XCTAssertEqual(
            String(decoding: result.stdout, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines),
            "hello",
            "stdout must be captured via the concurrent drain"
        )
    }

    func testSubprocessRunnerTerminatesHangingChildOnTimeout() throws {
        let start = Date()
        let result = try SubprocessRunner.run(
            executable: URL(fileURLWithPath: "/bin/sleep"),
            arguments: ["60"],
            timeout: 1
        )
        let elapsed = Date().timeIntervalSince(start)

        XCTAssertTrue(result.timedOut, "hanging child must be flagged as timed out")
        XCTAssertLessThan(elapsed, 30, "bounded wait must return long before the child exits on its own")
        XCTAssertNotEqual(result.exitCode, 0, "terminated child must not report a clean exit")
    }

    func testSubprocessRunnerTimeoutSurfacesTypedError() throws {
        do {
            _ = try SubprocessRunner.runChecked(
                executable: URL(fileURLWithPath: "/bin/sleep"),
                arguments: ["60"],
                timeout: 1
            )
            XCTFail("expected subprocessTimeout error")
        } catch UpdateApplierError.subprocessTimeout(let command) {
            XCTAssertTrue(command.contains("sleep"), "timeout error should name the command, got: \(command)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - Cosign config nil (disabled) does not verify

    func testApplyBundleWithoutCosignConfigSkipsVerification() async throws {
        let assetBody = Data("fake-binary-content".utf8)
        let expectedSum = sha256Hex(assetBody)

        let client = StubUpdateHTTPClient()
        let checksumsText = "\(expectedSum)  mytool_darwin_arm64\n"
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

        // No cosignConfig (defaults to nil).
        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client
        )
        XCTAssertNil(applier.cosignConfig)

        let result = try await applier.applyBundle(release: release)
        defer { try? FileManager.default.removeItem(at: result) }

        let downloaded = try Data(contentsOf: result)
        XCTAssertEqual(downloaded, assetBody)
    }

    // MARK: - applyBundle error branches (#49)

    func testApplyBundleChecksumEntryMissingForAsset() async throws {
        let assetBody = Data("fake-binary-content".utf8)
        let expectedSum = sha256Hex(assetBody)
        // checksums.txt lists a different asset — the selected asset has no entry.
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

        let applier = UpdateApplier(os: "darwin", arch: "arm64", client: client)

        do {
            _ = try await applier.applyBundle(release: release)
            XCTFail("expected checksumMismatch (missing entry) error")
        } catch UpdateApplierError.checksumMismatch(let assetName, let got, _) {
            XCTAssertEqual(assetName, "mytool_darwin_arm64")
            XCTAssertTrue(got.contains("no entry"), "got should describe the missing entry, was: \(got)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testApplyBundleChecksumMismatchThrowsError() async throws {
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

        let applier = UpdateApplier(os: "darwin", arch: "arm64", client: client)

        do {
            _ = try await applier.applyBundle(release: release)
            XCTFail("expected checksumMismatch error")
        } catch UpdateApplierError.checksumMismatch(let assetName, let got, let expected) {
            XCTAssertEqual(assetName, "mytool_darwin_arm64")
            XCTAssertEqual(got, sha256Hex(assetBody), "got should be the downloaded body's real checksum")
            XCTAssertEqual(expected, wrongChecksum)
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testApplyBundleAllowsDirectDownloadWhenCheckEnabled() async throws {
        let assetBody = Data("binary".utf8)
        let expectedSum = sha256Hex(assetBody)

        let client = StubUpdateHTTPClient()
        let checksumsText = "\(expectedSum)  mytool_darwin_arm64\n"
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

        // /usr/local/bin is classified directDownload without touching the filesystem.
        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client,
            checkInstallMethod: true,
            binaryName: "symvault"
        )

        let result = try await applier.applyBundle(release: release, targetPath: "/usr/local/bin/symvault")
        defer { try? FileManager.default.removeItem(at: result) }

        XCTAssertEqual(try Data(contentsOf: result), assetBody, "supported install method must proceed to download")
    }

    // MARK: - Download failure branches (#49)

    func testIncompleteDownloadThrowsDownloadFailed() async throws {
        let client = StubUpdateHTTPClient()
        let checksumsText = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef  mytool_darwin_arm64\n"
        client.setResponse(path: "/checksums.txt", body: Data(checksumsText.utf8))
        client.setResponse(path: "/asset", body: Data("short-body".utf8))
        // Server advertises more bytes than it sends.
        client.contentLengthOverrides["/asset"] = 1_000_000

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/asset", size: 0),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        let applier = UpdateApplier(os: "darwin", arch: "arm64", client: client)

        do {
            _ = try await applier.apply(release: release)
            XCTFail("expected downloadFailed error for truncated body")
        } catch UpdateApplierError.downloadFailed(let message) {
            XCTAssertTrue(message.contains("Incomplete download"), "unexpected message: \(message)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testAssetExceedsMaxBodySizeThrowsDownloadFailed() async throws {
        let client = StubUpdateHTTPClient()
        let checksumsText = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef  mytool_darwin_arm64\n"
        client.setResponse(path: "/checksums.txt", body: Data(checksumsText.utf8))
        // Just over the 1 GiB cap — the download must be rejected before hashing.
        client.setResponse(path: "/asset", body: Data(repeating: 0x61, count: (1 << 30) + 1))

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/asset", size: 0),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        let applier = UpdateApplier(os: "darwin", arch: "arm64", client: client)

        do {
            _ = try await applier.apply(release: release)
            XCTFail("expected downloadFailed error for oversized asset")
        } catch UpdateApplierError.downloadFailed(let message) {
            XCTAssertTrue(message.contains("maximum allowed size"), "unexpected message: \(message)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - Install method writability heuristics (#49)

    func testDetectInstallMethodWritabilityHeuristics() throws {
        let tempRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("updateapply-writability-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: tempRoot) }
        try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)

        // Read-only directory → no self-update.
        let readOnly = tempRoot.appendingPathComponent("readonly")
        try FileManager.default.createDirectory(at: readOnly, withIntermediateDirectories: true)
        try FileManager.default.setAttributes([.posixPermissions: 0o444], ofItemAtPath: readOnly.path)
        XCTAssertEqual(
            UpdateApplier.detectInstallMethod(at: readOnly.appendingPathComponent("tool").path),
            .buildFromSource,
            "read-only directory must be classified buildFromSource"
        )

        // Group/other-writable without owner write → user can still update.
        let groupWritable = tempRoot.appendingPathComponent("groupwritable")
        try FileManager.default.createDirectory(at: groupWritable, withIntermediateDirectories: true)
        try FileManager.default.setAttributes([.posixPermissions: 0o577], ofItemAtPath: groupWritable.path)
        XCTAssertEqual(
            UpdateApplier.detectInstallMethod(at: groupWritable.appendingPathComponent("tool").path),
            .directDownload,
            "group/other-writable directory must be classified directDownload"
        )

        // Owner-writable → direct download.
        let ownerWritable = tempRoot.appendingPathComponent("ownerwritable")
        try FileManager.default.createDirectory(at: ownerWritable, withIntermediateDirectories: true)
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: ownerWritable.path)
        XCTAssertEqual(
            UpdateApplier.detectInstallMethod(at: ownerWritable.appendingPathComponent("tool").path),
            .directDownload,
            "owner-writable directory must be classified directDownload"
        )

        // Nonexistent directory → undeterminable.
        XCTAssertEqual(
            UpdateApplier.detectInstallMethod(at: tempRoot.appendingPathComponent("missing/bin/tool").path),
            .unknown
        )
    }

    // MARK: - Guidance for every install method (#49)

    func testGuidanceForAllInstallMethods() {
        XCTAssertTrue(UpdateApplier.guidance(for: .directDownload, binaryName: "t").contains("GitHub"))
        XCTAssertTrue(UpdateApplier.guidance(for: .homebrew, binaryName: "t").contains("brew upgrade"))
        XCTAssertTrue(UpdateApplier.guidance(for: .goInstall, binaryName: "t").contains("go install"))
        XCTAssertTrue(UpdateApplier.guidance(for: .packageManager, binaryName: "t").contains("package manager"))
        XCTAssertTrue(UpdateApplier.guidance(for: .buildFromSource, binaryName: "t").contains("swift build"))
        XCTAssertTrue(UpdateApplier.guidance(for: .unknown, binaryName: "t").contains("Unable to determine"))
    }

    // MARK: - errorDescription for every error case (#49)

    func testErrorDescriptionForAllCases() {
        let cases: [(UpdateApplierError, String)] = [
            (.downloadFailed("boom"), "boom"),
            (.checksumMismatch(assetName: "a", got: "g", expected: "e"), "Checksum mismatch for a: got g, expected e."),
            (.noMatchingAsset(os: "os", arch: "arch"), "No release asset matches os/arch."),
            (.destinationNotWritable("d"), "d"),
            (.missingChecksumsAsset, "The release has no checksums.txt asset."),
            (.unparseableChecksums, "The checksums.txt file contained no parseable entries."),
            (.httpStatus(503), "HTTP error 503."),
            (.unsupportedInstallMethod(.homebrew, guidance: "g"), "g"),
            (.applicationsNotWritable, "/Applications is not writable."),
            (.dmgMountFailed("m"), "m"),
            (.appBundleNotFound, "No .app bundle was found inside the archive."),
            (.appBundleCopyFailed("c"), "c"),
            (.cosignVerificationFailed("v"), "v"),
            (.subprocessTimeout("cmd"), "Subprocess timed out: cmd."),
        ]
        for (error, expected) in cases {
            XCTAssertEqual(error.localizedDescription, expected, "unexpected description for \(error)")
        }
    }

    // MARK: - CosignConfig delegation (#49)

    func testCosignConfigDelegatesFetchAndVerifyToVerifier() async throws {
        let verifier = StubPassingCosignVerifier()
        let cfg = CosignConfig(repo: "danieljustus/symaira-vault", binaryName: "symvault", verifier: verifier)

        let sig = try await cfg.fetchSignature(tag: "v1.0.0")
        XCTAssertEqual(sig, Data("stub-signature".utf8), "fetchSignature must delegate to the verifier")

        let cert = try await cfg.fetchCertificate(tag: "v1.0.0")
        XCTAssertEqual(cert, Data("stub-certificate".utf8), "fetchCertificate must delegate to the verifier")

        // verifySignature delegation must not throw with a passing verifier.
        try await cfg.verifySignature(content: Data("c".utf8), signature: Data("s".utf8), certificate: Data("c".utf8))
    }

    // MARK: - CosignCLIVerifier artifact fetching (#49)

    func testCosignCLIVerifierFetchSignatureSuccess() async throws {
        let client = StubUpdateHTTPClient()
        client.setResponse(path: "/danieljustus/symaira-vault/releases/download/v1.2.0/symvault_1.2.0_checksums.txt.sig", body: Data("sig-bytes".utf8))
        client.setResponse(path: "/danieljustus/symaira-vault/releases/download/v1.2.0/symvault_1.2.0_checksums.txt.pem", body: Data("cert-bytes".utf8))

        let verifier = CosignCLIVerifier(
            repo: "danieljustus/symaira-vault",
            binaryName: "symvault",
            httpClient: client
        )

        let sig = try await verifier.fetchSignature(tag: "v1.2.0")
        XCTAssertEqual(sig, Data("sig-bytes".utf8))
        let cert = try await verifier.fetchCertificate(tag: "v1.2.0")
        XCTAssertEqual(cert, Data("cert-bytes".utf8))
    }

    func testCosignCLIVerifierFetchArtifactHTTPError() async throws {
        let client = StubUpdateHTTPClient() // no response registered → stub returns 404
        let verifier = CosignCLIVerifier(repo: "danieljustus/symaira-vault", binaryName: "symvault", httpClient: client)

        do {
            _ = try await verifier.fetchSignature(tag: "v1.2.0")
            XCTFail("expected cosignVerificationFailed for HTTP 404")
        } catch UpdateApplierError.cosignVerificationFailed(let message) {
            XCTAssertTrue(message.contains("HTTP 404"), "unexpected message: \(message)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testCosignCLIVerifierFetchArtifactEmptyVersionThrows() async throws {
        let verifier = CosignCLIVerifier(repo: "danieljustus/symaira-vault", binaryName: "symvault")

        do {
            _ = try await verifier.fetchSignature(tag: "v") // strips to an empty version
            XCTFail("expected cosignVerificationFailed for empty version")
        } catch UpdateApplierError.cosignVerificationFailed(let message) {
            XCTAssertTrue(message.contains("Version must not be empty"), "unexpected message: \(message)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testCosignCLIVerifierFetchArtifactRejectsNonHTTPS() async throws {
        let verifier = CosignCLIVerifier(
            repo: "danieljustus/symaira-vault",
            binaryName: "symvault",
            downloadBaseURL: "http://insecure.example.com"
        )

        do {
            _ = try await verifier.fetchSignature(tag: "v1.2.0")
            XCTFail("expected cosignVerificationFailed for non-HTTPS URL")
        } catch UpdateApplierError.cosignVerificationFailed(let message) {
            XCTAssertTrue(message.contains("must use HTTPS"), "unexpected message: \(message)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - CosignCLIVerifier verifySignature branches (#49)

    func testCosignCLIVerifierMissingCLIThrowsBoundedError() async throws {
        // Restrict PATH so `/usr/bin/which cosign` fails, deterministically
        // exercising the missing-CLI branch whether or not cosign is
        // installed on this machine. Subprocesses inherit the process
        // environment; the original PATH is restored afterwards.
        let originalPATH = ProcessInfo.processInfo.environment["PATH"] ?? ""
        setenv("PATH", "/usr/bin:/bin", 1)
        defer { setenv("PATH", originalPATH, 1) }

        let verifier = CosignCLIVerifier(repo: "danieljustus/symaira-vault", binaryName: "symvault")

        do {
            try await verifier.verifySignature(
                content: Data("content".utf8),
                signature: Data("signature".utf8),
                certificate: Data("certificate".utf8)
            )
            XCTFail("expected verification to fail when cosign is missing")
        } catch UpdateApplierError.cosignVerificationFailed(let message) {
            XCTAssertTrue(message.contains("cosign CLI not found"), "unexpected message: \(message)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testCosignCLIVerifierVerifyFailureThrowsDiagnosticCase() async throws {
        let which = try SubprocessRunner.runChecked(
            executable: URL(fileURLWithPath: "/usr/bin/which"),
            arguments: ["cosign"]
        )
        try XCTSkipIf(which.exitCode != 0, "cosign CLI not installed — diagnostic branch requires a real cosign binary")

        let verifier = CosignCLIVerifier(repo: "danieljustus/symaira-vault", binaryName: "symvault")

        do {
            try await verifier.verifySignature(
                content: Data("not-a-checksum".utf8),
                signature: Data("not-a-signature".utf8),
                certificate: Data("not-a-certificate".utf8)
            )
            XCTFail("expected cosign verify-blob to fail on garbage input")
        } catch UpdateApplierError.cosignVerificationFailedDiagnostic(let stderr) {
            XCTAssertFalse(stderr.isEmpty, "diagnostic stderr must carry the cosign failure output")

            let error = UpdateApplierError.cosignVerificationFailedDiagnostic(stderr)
            XCTAssertEqual(
                error.cosignDiagnosticStderr, stderr,
                "diagnostic accessor must return the full stderr"
            )
            XCTAssertLessThan(error.localizedDescription.utf8.count, 300, "user-facing description must stay bounded")
            XCTAssertTrue(
                error.localizedDescription.contains("cosign verify-blob failed"),
                "unexpected description: \(error.localizedDescription)"
            )
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - DMG/ZIP install failure paths (#49)
    //
    // These exercise the failure-mapping around the real /usr/bin/ditto and
    // /usr/bin/hdiutil subprocesses without touching /Applications: every
    // test stops before any copy into /Applications happens. They skip when
    // /Applications is not writable (non-admin environment).

    func testInstallDMGHdiutilAttachFailureThrowsDmgMountFailed() async throws {
        try XCTSkipIf(
            !FileManager.default.isWritableFile(atPath: "/Applications"),
            "requires a writable /Applications (admin user)"
        )

        let garbage = FileManager.default.temporaryDirectory
            .appendingPathComponent("updateapply-bad-\(UUID().uuidString).dmg")
        try Data("definitely-not-a-disk-image".utf8).write(to: garbage)
        defer { try? FileManager.default.removeItem(at: garbage) }

        let applier = UpdateApplier()
        do {
            _ = try await applier.installDMG(at: garbage, assetName: "MyApp_darwin_arm64.dmg")
            XCTFail("expected dmgMountFailed for an unreadable disk image")
        } catch UpdateApplierError.dmgMountFailed(let message) {
            XCTAssertTrue(message.contains("hdiutil attach failed"), "unexpected message: \(message)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testApplyBundleDMGAssetDispatchesToInstallDMG() async throws {
        try XCTSkipIf(
            !FileManager.default.isWritableFile(atPath: "/Applications"),
            "requires a writable /Applications (admin user)"
        )

        let dmgBody = Data("definitely-not-a-disk-image".utf8)
        let expectedSum = sha256Hex(dmgBody)

        let client = StubUpdateHTTPClient()
        client.setResponse(path: "/checksums.txt", body: Data("\(expectedSum)  MyApp_darwin_arm64.dmg\n".utf8))
        client.setResponse(path: "/dmg", body: dmgBody)

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "MyApp_darwin_arm64.dmg", browserDownloadURL: "https://example.com/dmg", size: Int64(dmgBody.count)),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        let applier = UpdateApplier(os: "darwin", arch: "arm64", client: client)

        do {
            _ = try await applier.applyBundle(release: release)
            XCTFail("expected dmgMountFailed for an unreadable DMG asset")
        } catch UpdateApplierError.dmgMountFailed {
            // expected — the DMG dispatch reached installDMG and hdiutil failed
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testInstallZipDittoFailureThrowsAppBundleCopyFailed() async throws {
        try XCTSkipIf(
            !FileManager.default.isWritableFile(atPath: "/Applications"),
            "requires a writable /Applications (admin user)"
        )

        let garbage = FileManager.default.temporaryDirectory
            .appendingPathComponent("updateapply-bad-\(UUID().uuidString).zip")
        try Data("definitely-not-a-zip-archive".utf8).write(to: garbage)
        defer { try? FileManager.default.removeItem(at: garbage) }

        let applier = UpdateApplier()
        do {
            _ = try await applier.installZip(at: garbage, assetName: "MyApp_darwin_arm64.zip")
            XCTFail("expected appBundleCopyFailed when ditto cannot extract")
        } catch UpdateApplierError.appBundleCopyFailed(let message) {
            XCTAssertTrue(message.contains("ditto extraction failed"), "unexpected message: \(message)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testInstallZipAppBundleNotFoundWhenArchiveHasNoApp() async throws {
        try XCTSkipIf(
            !FileManager.default.isWritableFile(atPath: "/Applications"),
            "requires a writable /Applications (admin user)"
        )

        let tempRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("updateapply-zip-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        // Build a real ZIP (via ditto) that contains no .app bundle.
        let src = tempRoot.appendingPathComponent("src")
        try FileManager.default.createDirectory(at: src, withIntermediateDirectories: true)
        try Data("readme".utf8).write(to: src.appendingPathComponent("readme.txt"))

        let zipURL = tempRoot.appendingPathComponent("archive.zip")
        let zipResult = try SubprocessRunner.runChecked(
            executable: URL(fileURLWithPath: "/usr/bin/ditto"),
            arguments: ["-c", "-k", src.path, zipURL.path]
        )
        XCTAssertEqual(zipResult.exitCode, 0, "test setup: ditto must create the fixture archive")

        let applier = UpdateApplier()
        do {
            _ = try await applier.installZip(at: zipURL, assetName: "MyApp_darwin_arm64.zip")
            XCTFail("expected appBundleNotFound for an archive without an .app")
        } catch UpdateApplierError.appBundleNotFound {
            // expected
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - Streaming download (#74)

    func testStreamingDownloadWritesFullBodyWithIncrementalProgress() async throws {
        let assetBody = Data((0..<100).map { UInt8($0 & 0xFF) })
        let expectedSum = sha256Hex(assetBody)

        let client = StreamingStubUpdateHTTPClient()
        client.setResponse(path: "/checksums.txt", body: Data("\(expectedSum)  mytool_darwin_arm64\n".utf8))
        client.setResponse(path: "/asset", body: assetBody)
        client.chunkSize = 16

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/asset", size: Int64(assetBody.count)),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        let progressBox = ProgressBox()
        let progressCalls = CounterBox()
        let applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client,
            progress: { written, total in
                progressBox.lastWritten = written
                progressCalls.count += 1
            }
        )

        let result = try await applier.apply(release: release)
        defer { try? FileManager.default.removeItem(at: result) }

        let downloaded = try Data(contentsOf: result)
        XCTAssertEqual(downloaded, assetBody, "streamed file must match the asset body")
        XCTAssertGreaterThan(progressCalls.count, 1, "progress must be reported per chunk, not once at 100%")
        XCTAssertEqual(progressBox.lastWritten, Int64(assetBody.count), "final progress must report the full body size")
    }

    func testStreamingDownloadRejectsOversizedContentLengthBeforeReadingBody() async throws {
        let checksumsText = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef  mytool_darwin_arm64\n"
        let client = StreamingStubUpdateHTTPClient()
        client.setResponse(path: "/checksums.txt", body: Data(checksumsText.utf8))
        client.setResponse(path: "/asset", body: Data("small-body".utf8))
        // The server advertises a body far above the injected cap.
        client.contentLengthOverrides["/asset"] = 10_000

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/asset", size: 0),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        var applier = UpdateApplier(os: "darwin", arch: "arm64", client: client)
        applier.maxBodySize = 1_000

        do {
            _ = try await applier.apply(release: release)
            XCTFail("expected downloadFailed for an oversized advertised Content-Length")
        } catch UpdateApplierError.downloadFailed(let message) {
            XCTAssertTrue(message.contains("maximum allowed size"), "unexpected message: \(message)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }

        XCTAssertEqual(client.consumedChunks.count, 0, "no body chunk may be read before the early rejection")
    }

    func testStreamingDownloadAbortsMidStreamWhenCapCrossed() async throws {
        let checksumsText = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef  mytool_darwin_arm64\n"
        let client = StreamingStubUpdateHTTPClient()
        client.setResponse(path: "/checksums.txt", body: Data(checksumsText.utf8))
        // Two chunks of 600 bytes each: the cap (1000) is crossed only when
        // the second chunk arrives. The server advertises a length under the
        // cap (Content-Length lies) so the mid-stream guard must fire — the
        // early header rejection must not preempt it.
        client.setResponse(path: "/asset", body: Data(repeating: 0x61, count: 600) + Data(repeating: 0x62, count: 600))
        client.contentLengthOverrides["/asset"] = 800
        client.chunkSize = 600

        let release = ReleaseInfo(
            tagName: "v1.2.0",
            htmlURL: "https://github.com/example/releases/tag/v1.2.0",
            assets: [
                Asset(name: "mytool_darwin_arm64", browserDownloadURL: "https://example.com/asset", size: 0),
                Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/checksums.txt", size: 0),
            ]
        )

        let progressCalls = CounterBox()
        var applier = UpdateApplier(
            os: "darwin",
            arch: "arm64",
            client: client,
            progress: { _, _ in progressCalls.count += 1 }
        )
        applier.maxBodySize = 1_000

        do {
            _ = try await applier.apply(release: release)
            XCTFail("expected downloadFailed when the stream crosses the cap")
        } catch UpdateApplierError.downloadFailed(let message) {
            XCTAssertTrue(message.contains("maximum allowed size"), "unexpected message: \(message)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }

        XCTAssertEqual(client.consumedChunks.count, 2, "abort must fire the moment the cap is crossed")
        XCTAssertEqual(progressCalls.count, 1, "progress must stop after the chunk that crossed the cap")
    }

    // MARK: - Async subprocess wrappers

    func testRunAsyncReturnsNonZeroExitWithoutThrowing() async throws {
        let result = try await SubprocessRunner.runAsync(
            executable: URL(fileURLWithPath: "/bin/sh"),
            arguments: ["-c", "printf failure >&2; exit 7"]
        )

        XCTAssertFalse(result.timedOut)
        XCTAssertEqual(result.exitCode, 7)
        XCTAssertEqual(String(decoding: result.stderr, as: UTF8.self), "failure")
    }

    func testRunAsyncTruncatesOutputAtConfiguredCap() async throws {
        let result = try await SubprocessRunner.runAsync(
            executable: URL(fileURLWithPath: "/bin/sh"),
            arguments: ["-c", "yes x | head -c 200000"],
            timeout: 5,
            maxOutputBytes: 1_024
        )

        XCTAssertFalse(result.timedOut, "output caps terminate the child independently of the timeout")
        XCTAssertEqual(result.stdout.count, 1_024, "stdout must be bounded exactly at the configured cap")
        XCTAssertNotEqual(result.exitCode, 0, "the capped child must not report a clean exit")
    }

    func testRunAsyncMissingExecutableThrowsLaunchFailed() async {
        let executable = URL(fileURLWithPath: "/definitely/missing/symaira-subprocess")

        do {
            _ = try await SubprocessRunner.runAsync(
                executable: executable,
                arguments: ["--version"]
            )
            XCTFail("expected launchFailed")
        } catch SubprocessRunnerError.launchFailed(let command) {
            XCTAssertEqual(command, "symaira-subprocess --version")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testRunAsyncOutputDecodeFailureSurfacesDecodingError() async throws {
        struct Payload: Decodable {
            let value: Int
        }

        let result = try await SubprocessRunner.runAsync(
            executable: URL(fileURLWithPath: "/bin/sh"),
            arguments: ["-c", "printf '%s' 'not-json'"]
        )

        do {
            _ = try JSONDecoder().decode(Payload.self, from: result.stdout)
            XCTFail("expected JSON decoding to fail")
        } catch is DecodingError {
            // Expected: the async wrapper preserves the invalid payload so
            // callers can surface the decode failure at their boundary.
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testRunCheckedAsyncTimeoutTerminatesChild() async {
        let start = Date()

        do {
            _ = try await SubprocessRunner.runCheckedAsync(
                executable: URL(fileURLWithPath: "/bin/sleep"),
                arguments: ["60"],
                timeout: 0.1
            )
            XCTFail("expected subprocessTimeout")
        } catch UpdateApplierError.subprocessTimeout(let command) {
            XCTAssertEqual(command, "sleep 60")
        } catch {
            XCTFail("unexpected error: \(error)")
        }

        XCTAssertLessThan(
            Date().timeIntervalSince(start),
            2,
            "a normally terminating child must be reaped promptly after timeout"
        )
    }

    func testRunCheckedAsyncEscalatesFromSIGTERMToSIGKILL() async {
        let start = Date()
        // This shell deliberately ignores SIGTERM and spins without creating
        // a descendant that could keep the output pipe open after SIGKILL.
        let ignoresSIGTERM = "trap '' TERM; while :; do :; done"

        do {
            _ = try await SubprocessRunner.runCheckedAsync(
                executable: URL(fileURLWithPath: "/bin/sh"),
                arguments: ["-c", ignoresSIGTERM],
                timeout: 0.1
            )
            XCTFail("expected subprocessTimeout")
        } catch UpdateApplierError.subprocessTimeout(let command) {
            XCTAssertEqual(command, "sh -c \(ignoresSIGTERM)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }

        let elapsed = Date().timeIntervalSince(start)
        XCTAssertGreaterThanOrEqual(
            elapsed,
            2.5,
            "a SIGTERM-resistant child must receive the implementation's grace period before SIGKILL"
        )
        XCTAssertLessThan(elapsed, 8, "SIGKILL escalation must remain bounded")
    }

    // MARK: - Async subprocess cooperative pool test (#94)

    /// Proves that independent async work completes while an update-flow
    /// subprocess is running. Without the async wrapper, the blocking
    /// DispatchSemaphore in SubprocessRunner.run can park the cooperative
    /// pool thread instead of suspending the calling task.
    func testAsyncWorkProgressesDuringSubprocess() async throws {
        let start = Date()
        let subprocess = Task {
            try await SubprocessRunner.runAsync(
                executable: URL(fileURLWithPath: "/bin/sleep"),
                arguments: ["2"],
                timeout: 5
            )
        }
        let independentWork = Task {
            try await Task.sleep(nanoseconds: 100_000_000)
            return true
        }

        let completed = try await independentWork.value
        let elapsed = Date().timeIntervalSince(start)
        XCTAssertTrue(completed)
        XCTAssertLessThan(elapsed, 1.0, "async work must not wait for the subprocess")

        let result = try await subprocess.value
        XCTAssertFalse(result.timedOut)
        XCTAssertEqual(result.exitCode, 0)
    }
}
