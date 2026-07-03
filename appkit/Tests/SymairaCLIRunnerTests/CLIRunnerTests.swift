import XCTest
@testable import SymairaCLIRunner

final class CLIRunnerTests: XCTestCase {
    private let runner = CLIRunner(defaultTimeout: 10)
    private let sh = URL(fileURLWithPath: "/bin/sh")

    func testCapturesStdout() async throws {
        let result = try await runner.run(sh, arguments: ["-c", "echo hello"])
        XCTAssertEqual(result.exitCode, 0)
        XCTAssertEqual(result.stdoutText, "hello")
    }

    func testCapturesStderrAndExitCode() async throws {
        let result = try await runner.run(sh, arguments: ["-c", "echo oops >&2; exit 3"])
        XCTAssertEqual(result.exitCode, 3)
        XCTAssertEqual(result.stderrText, "oops")
    }

    func testRunCheckedThrowsOnNonZeroExit() async {
        do {
            _ = try await runner.runChecked(sh, arguments: ["-c", "echo bad >&2; exit 2"])
            XCTFail("expected executionFailed")
        } catch let CLIRunnerError.executionFailed(code, stderr) {
            XCTAssertEqual(code, 2)
            XCTAssertEqual(stderr, "bad")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testStdinIsForwarded() async throws {
        let result = try await runner.run(sh, arguments: ["-c", "cat"], stdin: Data("piped".utf8))
        XCTAssertEqual(result.stdoutText, "piped")
    }

    func testTimeoutTerminatesProcess() async {
        do {
            _ = try await runner.run(sh, arguments: ["-c", "sleep 30"], timeout: 0.5)
            XCTFail("expected timeout")
        } catch let CLIRunnerError.timeout(seconds) {
            XCTAssertEqual(seconds, 0.5)
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testLargeOutputDoesNotDeadlock() async throws {
        // > 64 KiB pipe buffer: reading only after termination would hang.
        let result = try await runner.run(sh, arguments: ["-c", "yes x | head -c 200000"])
        XCTAssertEqual(result.stdout.count, 200_000)
    }

    func testRunDecodingConvertsSnakeCase() async throws {
        struct Info: Decodable, Equatable {
            let toolName: String
            let schemaVersion: Int
        }
        let json = Data("{\"tool_name\":\"symfake\",\"schema_version\":1}".utf8)
        let info = try await runner.runDecoding(
            Info.self,
            executable: sh,
            arguments: ["-c", "cat"],
            stdin: json
        )
        XCTAssertEqual(info, Info(toolName: "symfake", schemaVersion: 1))
    }

    func testRunDecodingWrapsDecodeErrors() async {
        struct Info: Decodable { let x: Int }
        do {
            _ = try await runner.runDecoding(Info.self, executable: sh, arguments: ["-c", "echo not-json"])
            XCTFail("expected invalidJSON")
        } catch CLIRunnerError.invalidJSON {
            // expected
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testMissingExecutableThrows() async {
        do {
            _ = try await runner.run(URL(fileURLWithPath: "/nonexistent/sym"), arguments: [])
            XCTFail("expected error")
        } catch {
            // Foundation throws NSError for missing executables — anything is fine.
        }
    }
}
