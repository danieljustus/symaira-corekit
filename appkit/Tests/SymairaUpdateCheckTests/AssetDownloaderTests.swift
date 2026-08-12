import XCTest
import CryptoKit
@testable import SymairaUpdateCheck

// MARK: - SHA256 helper

private func sha256Hex(_ data: Data) -> String {
    let digest = SHA256.hash(data: data)
    return digest.compactMap { String(format: "%02x", $0) }.joined()
}

// MARK: - Buffered-only client

/// An `UpdateHTTPClient` that implements only `data(for:)` — used to verify
/// the single-chunk fallback path of `AssetDownloader`.
private struct BufferedOnlyClient: UpdateHTTPClient {
    var responses: [String: (Data, Int)] = [:]
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
}

// MARK: - AssetDownloaderTests

final class AssetDownloaderTests: XCTestCase {

    private func makeAsset(_ path: String) -> Asset {
        Asset(name: path, browserDownloadURL: "https://example.com\(path)", size: 0)
    }

    // MARK: - Streaming path

    func testDownloadToTempStreamsChunksWithIncrementalProgress() async throws {
        let body = Data((0..<100).map { UInt8($0 & 0xFF) })
        let client = StreamingStubUpdateHTTPClient()
        client.setResponse(path: "/asset", body: body)
        client.chunkSize = 16

        let progressCalls = CounterBox()
        let progressBox = ProgressBox()
        let downloader = AssetDownloader(
            client: client,
            progress: { written, total in
                progressBox.lastWritten = written
                progressCalls.count += 1
            }
        )

        let (tempURL, sum) = try await downloader.downloadToTemp(asset: makeAsset("/asset"))
        defer { try? FileManager.default.removeItem(at: tempURL) }

        XCTAssertEqual(try Data(contentsOf: tempURL), body, "streamed file must match the body")
        XCTAssertEqual(sum, sha256Hex(body), "incremental hash must match a one-shot SHA256")
        XCTAssertGreaterThan(progressCalls.count, 1, "progress must be reported per chunk")
        XCTAssertEqual(progressBox.lastWritten, Int64(body.count))
    }

    func testDownloadToTempRejectsOversizedContentLengthBeforeReadingBody() async throws {
        let client = StreamingStubUpdateHTTPClient()
        client.setResponse(path: "/asset", body: Data("small-body".utf8))
        client.contentLengthOverrides["/asset"] = 10_000

        let downloader = AssetDownloader(client: client, maxBodySize: 1_000)

        do {
            _ = try await downloader.downloadToTemp(asset: makeAsset("/asset"))
            XCTFail("expected downloadFailed for an oversized advertised Content-Length")
        } catch UpdateApplierError.downloadFailed(let message) {
            XCTAssertTrue(message.contains("maximum allowed size"), "unexpected message: \(message)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }

        XCTAssertEqual(client.consumedChunks.count, 0, "no body chunk may be read before the early rejection")
    }

    func testDownloadToTempAbortsMidStreamWhenCapCrossed() async throws {
        let client = StreamingStubUpdateHTTPClient()
        // Two 600-byte chunks cross the 1000-byte cap only on the second
        // chunk; the advertised Content-Length stays under the cap.
        client.setResponse(path: "/asset", body: Data(repeating: 0x61, count: 600) + Data(repeating: 0x62, count: 600))
        client.contentLengthOverrides["/asset"] = 800
        client.chunkSize = 600

        let progressCalls = CounterBox()
        let downloader = AssetDownloader(
            client: client,
            progress: { _, _ in progressCalls.count += 1 },
            maxBodySize: 1_000
        )

        do {
            _ = try await downloader.downloadToTemp(asset: makeAsset("/asset"))
            XCTFail("expected downloadFailed when the stream crosses the cap")
        } catch UpdateApplierError.downloadFailed(let message) {
            XCTAssertTrue(message.contains("maximum allowed size"), "unexpected message: \(message)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }

        XCTAssertEqual(client.consumedChunks.count, 2, "abort must fire the moment the cap is crossed")
        XCTAssertEqual(progressCalls.count, 1, "progress must stop after the chunk that crossed the cap")
    }

    func testDownloadToTempHTTPErrorThrowsHttpStatus() async throws {
        let client = StreamingStubUpdateHTTPClient()
        client.setResponse(path: "/asset", body: Data("oops".utf8), status: 500)

        let downloader = AssetDownloader(client: client)

        do {
            _ = try await downloader.downloadToTemp(asset: makeAsset("/asset"))
            XCTFail("expected httpStatus error")
        } catch UpdateApplierError.httpStatus(let code) {
            XCTAssertEqual(code, 500)
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    // MARK: - Buffered fallback path

    func testDownloadToTempBufferedFallbackClient() async throws {
        let body = Data("buffered-fallback-body".utf8)
        var client = BufferedOnlyClient()
        client.responses["/asset"] = (body, 200)

        let progressCalls = CounterBox()
        let progressBox = ProgressBox()
        let downloader = AssetDownloader(
            client: client,
            progress: { written, total in
                progressBox.lastWritten = written
                progressCalls.count += 1
            }
        )

        let (tempURL, sum) = try await downloader.downloadToTemp(asset: makeAsset("/asset"))
        defer { try? FileManager.default.removeItem(at: tempURL) }

        XCTAssertEqual(try Data(contentsOf: tempURL), body)
        XCTAssertEqual(sum, sha256Hex(body))
        XCTAssertEqual(progressCalls.count, 1, "buffered fallback reports progress once")
        XCTAssertEqual(progressBox.lastWritten, Int64(body.count))
    }

    func testDownloadToTempBufferedFallbackIncompleteDownload() async throws {
        var client = BufferedOnlyClient()
        client.responses["/asset"] = (Data("short-body".utf8), 200)
        client.contentLengthOverrides["/asset"] = 1_000_000

        let downloader = AssetDownloader(client: client)

        do {
            _ = try await downloader.downloadToTemp(asset: makeAsset("/asset"))
            XCTFail("expected downloadFailed for a truncated body")
        } catch UpdateApplierError.downloadFailed(let message) {
            XCTAssertTrue(message.contains("Incomplete download"), "unexpected message: \(message)")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }
}
