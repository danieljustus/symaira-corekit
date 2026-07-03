import XCTest
@testable import SymairaUpdateCheck

final class StableVersionTests: XCTestCase {
    func testParsesWithAndWithoutPrefix() {
        XCTAssertEqual(StableVersion("v1.2.3"), StableVersion("1.2.3"))
        XCTAssertEqual(StableVersion("v0.4.1")?.description, "v0.4.1")
    }

    func testRejectsPrereleaseAndGarbage() {
        XCTAssertNil(StableVersion("1.2.3-beta.1"))
        XCTAssertNil(StableVersion("1.2.3+build5"))
        XCTAssertNil(StableVersion("dev"))
        XCTAssertNil(StableVersion("1.2"))
        XCTAssertNil(StableVersion(""))
    }

    func testOrdering() {
        XCTAssertLessThan(StableVersion("1.2.3")!, StableVersion("1.2.10")!)
        XCTAssertLessThan(StableVersion("1.9.9")!, StableVersion("2.0.0")!)
        XCTAssertLessThan(StableVersion("0.9.0")!, StableVersion("0.10.0")!)
    }
}

private struct StubHTTPClient: UpdateHTTPClient {
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

final class UpdateCheckerTests: XCTestCase {
    private var cacheDir: URL!

    override func setUpWithError() throws {
        cacheDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("appkit-updatecheck-\(UUID().uuidString)")
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: cacheDir)
    }

    private func checker(latestTag: String, status: Int = 200) -> UpdateChecker {
        let body = "{\"tag_name\":\"\(latestTag)\",\"html_url\":\"https://github.com/danieljustus/x/releases/tag/\(latestTag)\"}"
        return UpdateChecker(
            owner: "danieljustus",
            repo: "x",
            client: StubHTTPClient(body: body, status: status),
            cacheDirectory: cacheDir
        )
    }

    func testReportsAvailableUpdate() async throws {
        let release = try await checker(latestTag: "v1.1.0").check(currentVersion: "v1.0.0")
        XCTAssertEqual(release?.tagName, "v1.1.0")
    }

    func testUpToDateReturnsNil() async throws {
        let release = try await checker(latestTag: "v1.0.0").check(currentVersion: "v1.0.0")
        XCTAssertNil(release)
    }

    func testNewerLocalVersionReturnsNil() async throws {
        let release = try await checker(latestTag: "v1.0.0").check(currentVersion: "v1.2.0")
        XCTAssertNil(release)
    }

    func testDevVersionSkipsCheck() async throws {
        let release = try await checker(latestTag: "v9.9.9").check(currentVersion: "1.0.0-dev")
        XCTAssertNil(release)
    }

    func testHTTPErrorThrows() async {
        do {
            _ = try await checker(latestTag: "v1.1.0", status: 500).check(currentVersion: "v1.0.0")
            XCTFail("expected httpStatus error")
        } catch UpdateCheckError.httpStatus(let code) {
            XCTAssertEqual(code, 500)
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testSecondCheckUsesDiskCache() async throws {
        _ = try await checker(latestTag: "v2.0.0").check(currentVersion: "v1.0.0")
        // New checker with a failing transport: must be served from cache.
        let cached = UpdateChecker(
            owner: "danieljustus",
            repo: "x",
            client: StubHTTPClient(body: "unreachable", status: 500),
            cacheDirectory: cacheDir
        )
        let release = try await cached.check(currentVersion: "v1.0.0")
        XCTAssertEqual(release?.tagName, "v2.0.0")
    }
}
