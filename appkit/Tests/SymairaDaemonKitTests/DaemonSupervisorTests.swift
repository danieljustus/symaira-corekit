#if os(macOS)
import XCTest
@testable import SymairaDaemonKit

final class DaemonSupervisorTests: XCTestCase {
    
    func testStartAndStopDaemon() async throws {
        let supervisor = DaemonSupervisor()
        
        // Use a simple long-running command like sleep
        let sleepURL = URL(fileURLWithPath: "/bin/sleep")
        
        let stream = supervisor.start(executable: sleepURL, arguments: ["10"])
        
        // Wait a short moment to ensure the process runs
        try? await Task.sleep(nanoseconds: 100_000_000) // 100ms
        
        XCTAssertEqual(supervisor.state, .running(pid: supervisor.state.statePID ?? 0))
        
        supervisor.stop()
        
        // Read from the stream to ensure it terminates
        var lines: [DaemonLogLine] = []
        for await line in stream {
            lines.append(line)
        }
        
        XCTAssertEqual(supervisor.state, .stopped)
        XCTAssertFalse(lines.isEmpty)
        XCTAssertTrue(lines.contains { $0.text.contains("stopped cleanly") || $0.text.contains("Stopping process") })
    }
    
    func testEchoOutputCaptured() async throws {
        let supervisor = DaemonSupervisor()
        let echoURL = URL(fileURLWithPath: "/bin/echo")
        
        let stream = supervisor.start(executable: echoURL, arguments: ["hello-world-daemon"])
        
        var lines: [DaemonLogLine] = []
        for await line in stream {
            lines.append(line)
        }
        
        XCTAssertEqual(supervisor.state, .stopped)
        XCTAssertTrue(lines.contains { $0.text == "hello-world-daemon" })
    }
    
    func testFailedExecution() async throws {
        let supervisor = DaemonSupervisor()
        let falseURL = URL(fileURLWithPath: "/usr/bin/false")
        
        let stream = supervisor.start(executable: falseURL, arguments: [])
        
        var lines: [DaemonLogLine] = []
        for await line in stream {
            lines.append(line)
        }
        
        guard case .failed(let msg) = supervisor.state else {
            XCTFail("Expected state to be failed, was \(supervisor.state)")
            return
        }
        
        XCTAssertTrue(msg.contains("exited with code 1") || msg.contains("status 1"))
    }
    
    // MARK: - Issue #13: Restart race
    
    func testRestartWhileRunningReturnsLiveStreamForNewProcess() async throws {
        let supervisor = DaemonSupervisor()
        let sleepURL = URL(fileURLWithPath: "/bin/sleep")
        
        // Start first process (long-running)
        let stream1 = supervisor.start(executable: sleepURL, arguments: ["10"])
        
        // Give it time to start
        try? await Task.sleep(nanoseconds: 200_000_000) // 200ms
        
        let pid1: Int32
        if case .running(let pid) = supervisor.state { pid1 = pid }
        else { XCTFail("Expected running state after start"); return }
        
        // Restart while running: this triggers stopInternal() → old process terminated,
        // then a new process is spawned. The new stream must be live.
        let stream2 = supervisor.start(executable: sleepURL, arguments: ["5"])
        
        // Give the second process time to start
        try? await Task.sleep(nanoseconds: 200_000_000) // 200ms
        
        // The supervisor must be in .running state for the new process
        guard case .running(let pid2) = supervisor.state else {
            XCTFail("Expected .running after restart, got \(supervisor.state)")
            return
        }
        XCTAssertNotEqual(pid1, pid2, "Restart should spawn a new process with a different PID")
        
        // Stream1 should complete (old process terminated)
        var stream1Lines: [DaemonLogLine] = []
        for await line in stream1 {
            stream1Lines.append(line)
        }
        XCTAssertFalse(stream1Lines.isEmpty, "Stream1 should have yielded some lines")
        
        // Stream2 should still be live (new process running)
        // We verify this by stopping and reading the remainder
        supervisor.stop()
        
        var stream2Lines: [DaemonLogLine] = []
        for await line in stream2 {
            stream2Lines.append(line)
        }
        
        XCTAssertEqual(supervisor.state, .stopped)
        XCTAssertFalse(stream2Lines.isEmpty, "Stream2 should have yielded lines from the new process")
    }
}

fileprivate extension DaemonState {
    var statePID: Int32? {
        if case .running(let pid) = self { return pid }
        return nil
    }
}
#endif
