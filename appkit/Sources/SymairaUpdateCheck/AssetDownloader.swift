import Foundation
#if canImport(CryptoKit)
import CryptoKit
#else
import Crypto
#endif

#if os(macOS)
// MARK: - Streaming download seam

/// A chunked byte stream produced by a streaming HTTP client. Iterating it
/// yields the response body as incremental `Data` chunks so large assets
/// never need to be buffered in memory.
protocol UpdateByteStream: AsyncSequence, Sendable where Element == Data {}

/// Streaming variant of `UpdateHTTPClient` that can deliver response bodies
/// incrementally. `URLSession` conforms; clients that only implement
/// `data(for:)` fall back to the buffered single-chunk path in
/// `AssetDownloader`.
protocol UpdateHTTPStreamingClient: UpdateHTTPClient {
    /// Begin a streaming download of `request`, returning the response plus
    /// an async sequence of body chunks.
    func stream(for request: URLRequest) async throws -> (any UpdateByteStream, URLResponse)
}

extension URLSession: UpdateHTTPStreamingClient {
    func stream(for request: URLRequest) async throws -> (any UpdateByteStream, URLResponse) {
        let (bytes, response) = try await bytes(for: request)
        return (URLSessionByteStream(bytes), response)
    }
}

/// Wraps `URLSession.AsyncBytes` as an `UpdateByteStream`, batching
/// individual byte reads into 64 KiB `Data` chunks.  Each `next()` call
/// accumulates up to 65 536 bytes from `AsyncBytes.Iterator.next()` into
/// a single `Data` value, so the downstream hash/progress/write path
/// processes one chunk instead of one byte at a time.
private struct URLSessionByteStream: UpdateByteStream {
    private let inner: URLSession.AsyncBytes

    init(_ inner: URLSession.AsyncBytes) {
        self.inner = inner
    }

    struct Iterator: AsyncIteratorProtocol {
        private var inner: URLSession.AsyncBytes.Iterator
        private static let chunkSize = 64 * 1024

        init(_ inner: URLSession.AsyncBytes.Iterator) {
            self.inner = inner
        }

        mutating func next() async throws -> Data? {
            var chunk = Data()
            chunk.reserveCapacity(Self.chunkSize)
            while chunk.count < Self.chunkSize, let byte = try await inner.next() {
                chunk.append(byte)
            }
            return chunk.isEmpty ? nil : chunk
        }
    }

    func makeAsyncIterator() -> Iterator {
        Iterator(inner.makeAsyncIterator())
    }
}

/// An `UpdateByteStream` that yields a single, already-buffered chunk — the
/// fallback for HTTP clients that only implement `data(for:)`.
private struct SingleChunkByteStream: UpdateByteStream {
    private let chunk: Data

    init(_ chunk: Data) {
        self.chunk = chunk
    }

    struct Iterator: AsyncIteratorProtocol {
        private var chunk: Data?

        init(_ chunk: Data) {
            self.chunk = chunk
        }

        mutating func next() async throws -> Data? {
            defer { chunk = nil }
            return chunk
        }
    }

    func makeAsyncIterator() -> Iterator {
        Iterator(chunk)
    }
}

// MARK: - AssetDownloader

/// Internal downloader that streams release assets to temporary files while
/// computing their SHA256 incrementally. The size cap is enforced against
/// the advertised `Content-Length` before any body byte is read and again
/// as the running byte count crosses it mid-stream; progress is reported
/// per chunk.
struct AssetDownloader: Sendable {

    /// Default maximum body size for downloaded assets (1 GiB cap).
    static let defaultMaxBodySize: Int64 = 1 << 30

    let client: UpdateHTTPClient
    let progress: UpdateProgressHandler?
    let maxBodySize: Int64

    init(
        client: UpdateHTTPClient,
        progress: UpdateProgressHandler? = nil,
        maxBodySize: Int64 = AssetDownloader.defaultMaxBodySize
    ) {
        self.client = client
        self.progress = progress
        self.maxBodySize = maxBodySize
    }

    /// Download an asset and return its body data, content length, and response.
    func download(asset: Asset) async throws -> (Data, Int64, URLResponse) {
        guard let url = URL(string: asset.browserDownloadURL) else {
            throw UpdateApplierError.downloadFailed("Invalid URL: \(asset.browserDownloadURL)")
        }

        var request = URLRequest(url: url, timeoutInterval: 30)
        request.httpMethod = "GET"

        let (data, response) = try await client.data(for: request)

        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw UpdateApplierError.httpStatus(http.statusCode)
        }

        let total = (response as? HTTPURLResponse)?.expectedContentLength ?? 0
        return (data, total, response)
    }

    /// Download an asset to a temporary file while computing its SHA256 hash.
    /// The response body is streamed to disk chunk by chunk — never buffered
    /// in memory — enforcing the size cap against the advertised
    /// `Content-Length` before any body byte is read and again as the
    /// running byte count crosses it mid-stream. Progress is reported per
    /// chunk. Returns the temp file URL and the hex-encoded hash.
    func downloadToTemp(asset: Asset) async throws -> (URL, String) {
        guard let url = URL(string: asset.browserDownloadURL) else {
            throw UpdateApplierError.downloadFailed("Invalid URL: \(asset.browserDownloadURL)")
        }

        var request = URLRequest(url: url, timeoutInterval: 30)
        request.httpMethod = "GET"

        // Prefer the streaming path when the client supports it; clients
        // that only implement `data(for:)` fall back to a single buffered
        // chunk (the size guard still fires before the chunk is written).
        if let streamingClient = client as? any UpdateHTTPStreamingClient {
            let (body, response) = try await streamingClient.stream(for: request)
            return try await streamBodyToTemp(body: body, response: response)
        }
        let (data, response) = try await client.data(for: request)
        return try await streamBodyToTemp(body: SingleChunkByteStream(data), response: response)
    }

    /// Shared streaming write path. `body` is generic so the loop variable
    /// is a concrete `Data` chunk; the size cap is enforced against the
    /// advertised `Content-Length` before any byte is read and again as the
    /// running byte count crosses it mid-stream. The hash is computed
    /// incrementally and progress is reported per chunk.
    private func streamBodyToTemp<Bytes: UpdateByteStream>(
        body: Bytes,
        response: URLResponse
    ) async throws -> (URL, String) {
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw UpdateApplierError.httpStatus(http.statusCode)
        }

        let total = (response as? HTTPURLResponse)?.expectedContentLength ?? 0

        // Reject early when the server advertises a body larger than the
        // cap — the guard fires before the body is downloaded at all.
        if total > maxBodySize {
            throw UpdateApplierError.downloadFailed(
                "Asset exceeds maximum allowed size (\(maxBodySize) bytes)"
            )
        }

        let tempDir = FileManager.default.temporaryDirectory
        let tempURL = tempDir.appendingPathComponent("updateapply-\(UUID().uuidString)")

        guard FileManager.default.createFile(atPath: tempURL.path, contents: nil) else {
            throw UpdateApplierError.destinationNotWritable(
                "Cannot create temp file at \(tempURL.path)"
            )
        }

        var written: Int64 = 0
        var hasher = SHA256()

        do {
            let handle = try FileHandle(forWritingTo: tempURL)
            defer { try? handle.close() }

            for try await chunk in body {
                written += Int64(chunk.count)

                // Abort the instant the running byte count crosses the cap,
                // before an oversized body is ever fully buffered.
                if written > maxBodySize {
                    try? FileManager.default.removeItem(at: tempURL)
                    throw UpdateApplierError.downloadFailed(
                        "Asset exceeds maximum allowed size (\(maxBodySize) bytes)"
                    )
                }

                try handle.write(contentsOf: chunk)
                hasher.update(data: chunk)
                progress?(written, total)
            }
        } catch let error as UpdateApplierError {
            throw error
        } catch {
            try? FileManager.default.removeItem(at: tempURL)
            throw UpdateApplierError.destinationNotWritable(
                "Cannot write to temp file at \(tempURL.path): \(error.localizedDescription)"
            )
        }

        // Verify the advertised content length was fully received.
        if total > 0, written != total {
            try? FileManager.default.removeItem(at: tempURL)
            throw UpdateApplierError.downloadFailed(
                "Incomplete download: got \(written) bytes, expected \(total)"
            )
        }

        let actualSum = hasher.finalize().compactMap { String(format: "%02x", $0) }.joined()
        return (tempURL, actualSum)
    }
}
#endif
