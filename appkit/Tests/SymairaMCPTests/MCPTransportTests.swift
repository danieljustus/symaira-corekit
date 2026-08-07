import XCTest
@testable import SymairaMCP

final class MCPTransportTests: XCTestCase {

    /// A newline-less line that exceeds `maxLineSize` is rejected: reading
    /// stops and the incoming stream finishes without delivering it, so an
    /// oversized or malicious message cannot cause unbounded allocation.
    func testRejectsOversizedLineWithoutNewline() async throws {
        let input = Pipe()
        let output = Pipe()
        let transport = MCPStdioTransport(
            input: input.fileHandleForReading,
            output: output.fileHandleForWriting,
            maxLineSize: 1024
        )
        let stream = transport.start()

        try input.fileHandleForWriting.write(contentsOf: Data(repeating: 0x61, count: 2048))
        input.fileHandleForWriting.closeFile()

        var lines: [String] = []
        for await line in stream {
            lines.append(line)
        }
        XCTAssertTrue(lines.isEmpty, "oversized line must be rejected, not delivered")
    }

    /// A line exactly at `maxLineSize` (terminated by a newline) is still
    /// delivered; only growth beyond the limit is rejected.
    func testDeliversLineExactlyAtLimit() async throws {
        let input = Pipe()
        let output = Pipe()
        let transport = MCPStdioTransport(
            input: input.fileHandleForReading,
            output: output.fileHandleForWriting,
            maxLineSize: 8
        )
        let stream = transport.start()

        var data = Data(repeating: 0x61, count: 8) // "aaaaaaaa", == limit
        data.append(0x0A)
        try input.fileHandleForWriting.write(contentsOf: data)
        input.fileHandleForWriting.closeFile()

        var lines: [String] = []
        for await line in stream {
            lines.append(line)
        }
        XCTAssertEqual(lines, ["aaaaaaaa"])
    }

    /// Data that grows a line beyond the limit in a later chunk (the line
    /// spans multiple reads) is rejected even though each chunk alone is
    /// small.
    func testRejectsLineGrowingBeyondLimitAcrossChunks() async throws {
        let input = Pipe()
        let output = Pipe()
        let transport = MCPStdioTransport(
            input: input.fileHandleForReading,
            output: output.fileHandleForWriting,
            maxLineSize: 8
        )
        let stream = transport.start()

        try input.fileHandleForWriting.write(contentsOf: Data(repeating: 0x61, count: 6))
        // Let the first chunk be consumed before growing past the limit.
        try await Task.sleep(for: .milliseconds(200))
        try input.fileHandleForWriting.write(contentsOf: Data(repeating: 0x62, count: 6)) // 12 bytes total, no newline
        input.fileHandleForWriting.closeFile()

        var lines: [String] = []
        for await line in stream {
            lines.append(line)
        }
        XCTAssertTrue(lines.isEmpty, "line grown beyond maxLineSize across chunks must be rejected")
    }
}
