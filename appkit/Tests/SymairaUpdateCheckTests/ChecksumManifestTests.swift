import XCTest
@testable import SymairaUpdateCheck

// MARK: - ChecksumManifestTests

final class ChecksumManifestTests: XCTestCase {

    func testParseValidEntries() {
        let a = String(repeating: "a", count: 64)
        let b = String(repeating: "b", count: 64)
        let sums = ChecksumManifest.parse("\(a)  file1\n\(b)  file2\n")

        XCTAssertEqual(sums.count, 2)
        XCTAssertEqual(sums["file1"], a)
        XCTAssertEqual(sums["file2"], b)
    }

    func testParseLowercasesHashesAndSkipsInvalidLines() {
        let uppercase = "ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789  tool\n"
        let tooShort = "abc123  tool2\n"
        let notHex = String(repeating: "z", count: 64) + "  tool3\n"
        let noFilename = String(repeating: "a", count: 64) + "\n"
        let blank = "\n"

        let sums = ChecksumManifest.parse(uppercase + tooShort + notHex + noFilename + blank)

        XCTAssertEqual(
            sums,
            ["tool": String(repeating: "abcdef0123456789", count: 4)],
            "only well-formed 64-hex lines with a filename may be kept, lowercased"
        )
    }

    func testParseEmptyTextYieldsEmptyManifest() {
        XCTAssertTrue(ChecksumManifest.parse("").isEmpty)
        XCTAssertTrue(ChecksumManifest.parse("\n\n\n").isEmpty)
    }

    func testLocateAssetPrefersExactChecksumsName() throws {
        let assets = [
            Asset(name: "tool_checksums.txt", browserDownloadURL: "https://example.com/other", size: 0),
            Asset(name: "checksums.txt", browserDownloadURL: "https://example.com/exact", size: 0),
        ]
        let located = try ChecksumManifest.locateAsset(in: assets)
        XCTAssertEqual(located.browserDownloadURL, "https://example.com/exact")
    }

    func testLocateAssetFallsBackToContains() throws {
        let assets = [
            Asset(name: "tool_checksums.sha256", browserDownloadURL: "https://example.com/sums", size: 0),
        ]
        let located = try ChecksumManifest.locateAsset(in: assets)
        XCTAssertEqual(located.browserDownloadURL, "https://example.com/sums")
    }

    func testLocateAssetThrowsWhenMissing() {
        let assets = [
            Asset(name: "tool_darwin_arm64", browserDownloadURL: "https://example.com/tool", size: 0),
        ]
        XCTAssertThrowsError(try ChecksumManifest.locateAsset(in: assets)) { error in
            guard case UpdateApplierError.missingChecksumsAsset = error else {
                return XCTFail("unexpected error: \(error)")
            }
        }
    }
}
