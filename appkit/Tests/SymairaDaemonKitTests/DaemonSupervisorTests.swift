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
}

fileprivate extension DaemonState {
    var statePID: Int32? {
        if case .running(let pid) = self { return pid }
        return nil
    }
}
#endif
