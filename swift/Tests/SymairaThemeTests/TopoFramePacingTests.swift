import XCTest

@testable import SymairaTheme

/// The pause and pacing rules shared by the macOS timer and the iOS display link.
final class TopoFramePacingTests: XCTestCase {
    func testPausedWhenStillHiddenOrLowPower() {
        XCTAssertFalse(TopoFramePacing.isPaused(still: false, visible: true, lowPower: false))
        XCTAssertTrue(TopoFramePacing.isPaused(still: true, visible: true, lowPower: false), "Reduce Motion")
        XCTAssertTrue(TopoFramePacing.isPaused(still: false, visible: false, lowPower: false), "background scene")
        XCTAssertTrue(TopoFramePacing.isPaused(still: false, visible: true, lowPower: true), "Low Power Mode")
    }

    func testLowPowerMakesFramesStaticWithoutStillFlag() {
        XCTAssertFalse(TopoFramePacing.isStill(still: false, lowPower: false))
        XCTAssertTrue(TopoFramePacing.isStill(still: false, lowPower: true))
        XCTAssertTrue(TopoFramePacing.isStill(still: true, lowPower: false))
    }

    func testFrameLoopNeedsUnpausedAndWindow() {
        XCTAssertTrue(TopoFramePacing.runsFrameLoop(paused: false, hasWindow: true))
        XCTAssertFalse(TopoFramePacing.runsFrameLoop(paused: true, hasWindow: true))
        XCTAssertFalse(
            TopoFramePacing.runsFrameLoop(paused: false, hasWindow: false),
            "a view removed from its window must drop its frame loop")
    }

    func testIdleRunsAtTokenCapRegardlessOfDisplay() {
        for maximum in [0, 60, 120] {
            XCTAssertEqual(
                TopoFramePacing.framesPerSecond(interactive: false, displayMaximum: maximum), SymairaTokens.Topo.fps)
            let rate = TopoFramePacing.rate(interactive: false, displayMaximum: maximum)
            XCTAssertEqual(rate, .init(minimum: 20, maximum: 20, preferred: 20), "idle must be pinned, not a range")
        }
    }

    func testInteractiveFollowsDisplayMaximum() {
        XCTAssertEqual(TopoFramePacing.framesPerSecond(interactive: true, displayMaximum: 120), 120)
        XCTAssertEqual(TopoFramePacing.framesPerSecond(interactive: true, displayMaximum: 60), 60)
        XCTAssertEqual(TopoFramePacing.framesPerSecond(interactive: true, displayMaximum: 0), 60, "unknown display")
        let rate = TopoFramePacing.rate(interactive: true, displayMaximum: 120)
        XCTAssertEqual(rate, .init(minimum: 20, maximum: 120, preferred: 120))
    }

    func testInteractiveRangeNeverDropsBelowIdleOrExceedsDisplay() {
        let rate = TopoFramePacing.rate(interactive: true, displayMaximum: 10)
        XCTAssertEqual(rate.maximum, 10)
        XCTAssertLessThanOrEqual(rate.minimum, rate.preferred)
        XCTAssertLessThanOrEqual(rate.preferred, rate.maximum)
    }
}
