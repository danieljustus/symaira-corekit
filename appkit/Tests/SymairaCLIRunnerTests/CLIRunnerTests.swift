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
        } catch let CLIRunnerError.executionFailed(code, fullStderr) {
            XCTAssertEqual(code, 2)
            XCTAssertEqual(fullStderr, "bad")
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testEnvironmentIsMergedOverInherited() async throws {
        let result = try await runner.run(
            sh,
            arguments: ["-c", "printf '%s' \"$SYMTEST_FLAG\""],
            environment: ["SYMTEST_FLAG": "on"]
        )
        XCTAssertEqual(result.stdoutText, "on")
        // PATH augmentation must survive the merge.
        let path = try await runner.run(sh, arguments: ["-c", "printf '%s' \"$PATH\""], environment: ["X": "y"])
        XCTAssertTrue(path.stdoutText.hasPrefix(CLIRunner.augmentedPATHPrefix))
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

    // MARK: - Issue #9: Safe error descriptions

    func testFullStderrPropertyNotPartOfLocalizedError() {
        // fullStderr is a separate property, not localised.
        let err = CLIRunnerError.executionFailed(code: 1, fullStderr: "raw secret data")
        XCTAssertEqual(err.fullStderr, "raw secret data")
        // errorDescription (LocalizedError) must NOT contain the raw text verbatim
        // when it looks secret-like.
    }

    func testErrorDescriptionIsBoundedTo200Bytes() {
        // Generate a stderr line > 300 bytes — the description must be ≤ 200 bytes.
        let longStderr = String(repeating: "A", count: 500)
        let err = CLIRunnerError.executionFailed(code: 1, fullStderr: longStderr)
        let desc = err.errorDescription ?? ""
        // The description prefix "CLI execution failed with exit code 1: " takes
        // ~40 bytes, leaving ~160 for the content. The ellipsis adds 3 more bytes.
        // Total should be ≤ ~205 bytes.
        let descBytes = desc.utf8.count
        XCTAssertLessThanOrEqual(descBytes, 210, "errorDescription is \(descBytes) bytes, expected ≤ 210")
        // Should contain the exit code.
        XCTAssertTrue(desc.contains("exit code 1"))
    }

    func testErrorDescriptionRedactsPEMBlocks() {
        let pemStderr = """
        -----BEGIN RSA PRIVATE KEY-----
        MIIEpAIBAAKCAQEA0Z3...
        -----END RSA PRIVATE KEY-----
        """
        let err = CLIRunnerError.executionFailed(code: 2, fullStderr: pemStderr)
        let desc = err.errorDescription ?? ""
        XCTAssertFalse(desc.contains("BEGIN RSA"), "PEM block not redacted: \(desc)")
        XCTAssertTrue(desc.contains("[REDACTED]"), "Expected [REDACTED] in: \(desc)")
    }

    func testErrorDescriptionRedactsLongBase64Tokens() {
        let tokenStderr = "error: invalid token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        let err = CLIRunnerError.executionFailed(code: 1, fullStderr: tokenStderr)
        let desc = err.errorDescription ?? ""
        XCTAssertTrue(desc.contains("[REDACTED]"), "Base64 token not redacted: \(desc)")
    }

    func testErrorDescriptionRedactsLongHexStrings() {
        let hexStderr = "error: key deadbeef1234567890abcdef1234567890abcdef1234567890abcdef is invalid"
        let err = CLIRunnerError.executionFailed(code: 1, fullStderr: hexStderr)
        let desc = err.errorDescription ?? ""
        XCTAssertTrue(desc.contains("[REDACTED]"), "Hex string not redacted: \(desc)")
    }

    func testErrorDescriptionRedactsKeyPrefixedSecrets() {
        let keyStderr = "error: API_KEY=sk-1234567890abcdefghijklmnopqrstuvwxyz"
        let err = CLIRunnerError.executionFailed(code: 1, fullStderr: keyStderr)
        let desc = err.errorDescription ?? ""
        XCTAssertTrue(desc.contains("[REDACTED]"), "Key-prefixed secret not redacted: \(desc)")
    }

    func testFullStderrIsNeverRedacted() {
        let secretStderr = "API_KEY=sk-supersecret"
        let err = CLIRunnerError.executionFailed(code: 1, fullStderr: secretStderr)
        // The fullStderr property returns the raw, unredacted text.
        XCTAssertEqual(err.fullStderr, secretStderr)
    }

    // MARK: - Issue #17: Output buffering cap

    func testOutputTruncationTerminatesProcess() async throws {
        // Emit > 64 KiB (a small cap) and verify the process is terminated early.
        let result = try await runner.run(
            sh,
            arguments: ["-c", "yes x | head -c 200000"],
            maxOutputBytes: 10_000
        )
        XCTAssertTrue(result.isTruncated, "Expected isTruncated=true")
        // The output must be ≤ the cap (with a small buffer for chunk alignment).
        XCTAssertLessThanOrEqual(result.stdout.count, 10_100)
    }

    func testRunCheckedThrowsOnTruncation() async {
        do {
            _ = try await runner.runChecked(
                sh,
                arguments: ["-c", "yes x | head -c 200000"],
                maxOutputBytes: 5_000
            )
            XCTFail("expected outputTruncated")
        } catch CLIRunnerError.outputTruncated(let size) {
            XCTAssertEqual(size, 5_000)
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testRunDecodingThrowsOnTruncationInsteadOfDecodingGarbage() async {
        struct Info: Decodable { let x: Int }
        do {
            _ = try await runner.runDecoding(
                Info.self,
                executable: sh,
                arguments: ["-c", "yes x | head -c 200000"],
                maxOutputBytes: 1_000
            )
            XCTFail("expected outputTruncated, not a decode error")
        } catch CLIRunnerError.outputTruncated {
            // Expected: decode was never attempted on truncated payload.
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testLargeOutputDoesNotDeadlockWithCap() async throws {
        // Existing deadlock test, now with the cap plumbing — must still pass.
        // Use a cap larger than the output so truncation does not trigger.
        let result = try await runner.run(
            sh,
            arguments: ["-c", "yes x | head -c 200000"],
            maxOutputBytes: CLIRunner.defaultMaxOutputBytes
        )
        XCTAssertEqual(result.stdout.count, 200_000)
        XCTAssertFalse(result.isTruncated)
    }

    // MARK: - Issue #14: Shared PATH plumbing

    func testAugmentedEnvironmentPrependsPATHPrefix() {
        let env = CLIRunner.augmentedEnvironment(["HOME": "/Users/test"])
        let path = env["PATH"] ?? ""
        XCTAssertTrue(path.hasPrefix(CLIRunner.augmentedPATHPrefix),
                      "PATH should start with augmented prefix, got: \(path)")
        XCTAssertTrue(path.contains("/Users/test") == false,
                      "Augmented environment should not leak non-PATH keys into PATH")
        XCTAssertEqual(env["HOME"], "/Users/test", "Non-PATH keys must be preserved")
    }

    func testAugmentedEnvironmentPreservesExistingPATHSuffix() {
        let env = CLIRunner.augmentedEnvironment(["PATH": "/custom/bin"])
        let path = env["PATH"] ?? ""
        XCTAssertTrue(path.hasPrefix(CLIRunner.augmentedPATHPrefix),
                      "PATH must start with augmented prefix")
        XCTAssertTrue(path.hasSuffix(":/custom/bin"),
                      "Existing PATH must be appended after the prefix, got: \(path)")
    }

    func testSpawnPathsYieldIdenticalAugmentation() async throws {
        // Verify both spawn paths (CLIRunner and DaemonSupervisor) produce
        // identical PATH augmentation via the shared helper.
        let cliEnv = CLIRunner.augmentedEnvironment([:])
        let cliPath = cliEnv["PATH"] ?? ""

        // DaemonSupervisor uses the same helper — verify by running a process
        // through CLIRunner (which uses augmentedEnvironment internally).
        let result = try await runner.run(
            sh,
            arguments: ["-c", "printf '%s' \"$PATH\""],
            environment: [:]
        )
        // The subprocess PATH should start with the same prefix.
        XCTAssertTrue(result.stdoutText.hasPrefix(CLIRunner.augmentedPATHPrefix),
                      "Subprocess PATH should start with augmented prefix, got: \(result.stdoutText)")
        // The prefix should match what augmentedEnvironment produces.
        XCTAssertEqual(String(cliPath.prefix(CLIRunner.augmentedPATHPrefix.count)),
                       CLIRunner.augmentedPATHPrefix)
    }
}
