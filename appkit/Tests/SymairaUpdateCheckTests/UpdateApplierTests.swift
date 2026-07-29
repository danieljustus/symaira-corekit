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

    func testCosignConfigDefaultIdentityRegexp() {
        let cfg = CosignConfig(
            repo: "danieljustus/symaira-vault",
            binaryName: "symvault"
        )
        let regexp = cfg.identityRegexpOrDefault()
        XCTAssertTrue(regexp.contains("danieljustus/symaira-vault"))
        XCTAssertTrue(regexp.contains("release"))
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
}
