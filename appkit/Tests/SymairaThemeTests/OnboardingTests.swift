import XCTest
@testable import SymairaTheme

private struct TestStep: SymairaOnboardingStep {
    let id: Int
    let order: Int
    var isSkippable: Bool = true
    var isTerminal: Bool = false
}

@MainActor
final class OnboardingTests: XCTestCase {
    private func makeFlow(count: Int = 4, lastSkippable: Bool = false) -> SymairaOnboardingFlow<TestStep> {
        let steps = (0..<count).map { index in
            TestStep(id: index, order: index, isSkippable: lastSkippable || index != count - 1)
        }
        return SymairaOnboardingFlow(steps: steps)
    }

    func testInitialStateStartsAtFirstStep() {
        let flow = makeFlow()
        XCTAssertEqual(flow.currentIndex, 0)
        XCTAssertEqual(flow.position, 1)
        XCTAssertTrue(flow.isFirstStep)
        XCTAssertFalse(flow.isLastStep)
        XCTAssertFalse(flow.isFinished)
    }

    func testAdvanceMovesToNextStep() {
        let flow = makeFlow()
        let outcome = flow.advance()
        XCTAssertEqual(outcome, .advanced)
        XCTAssertEqual(flow.currentIndex, 1)
        XCTAssertFalse(flow.isFinished)
    }

    func testAdvanceOnLastStepFinishesTheFlow() {
        let flow = makeFlow(count: 2)
        flow.advance()
        XCTAssertTrue(flow.isLastStep)
        let outcome = flow.advance()
        XCTAssertEqual(outcome, .finished)
        XCTAssertTrue(flow.isFinished)
    }

    func testAdvanceAfterFinishIsANoOp() {
        let flow = makeFlow(count: 1)
        XCTAssertEqual(flow.advance(), .finished)
        XCTAssertEqual(flow.advance(), .finished)
        XCTAssertEqual(flow.currentIndex, 0)
    }

    func testRetreatMovesBackAStep() {
        let flow = makeFlow()
        flow.advance()
        let outcome = flow.retreat()
        XCTAssertEqual(outcome, .retreated)
        XCTAssertEqual(flow.currentIndex, 0)
    }

    func testRetreatOnFirstStepIsANoOp() {
        let flow = makeFlow()
        XCTAssertNil(flow.retreat())
        XCTAssertEqual(flow.currentIndex, 0)
    }

    func testSkipAdvancesWhenStepIsSkippable() {
        let flow = makeFlow()
        let outcome = flow.skip()
        XCTAssertEqual(outcome, .skipped)
        XCTAssertEqual(flow.currentIndex, 1)
    }

    func testSkipOnNonSkippableStepIsANoOp() {
        let flow = makeFlow(count: 2, lastSkippable: false)
        flow.advance()
        XCTAssertTrue(flow.currentStep.isTerminal == false)
        XCTAssertFalse(flow.currentStep.isSkippable)
        let outcome = flow.skip()
        XCTAssertNil(outcome)
        XCTAssertTrue(flow.isLastStep)
        XCTAssertFalse(flow.isFinished)
    }

    func testSkipOnLastSkippableStepFinishes() {
        let flow = makeFlow(count: 2, lastSkippable: true)
        flow.advance()
        let outcome = flow.skip()
        XCTAssertEqual(outcome, .finished)
        XCTAssertTrue(flow.isFinished)
    }

    func testTerminalStepDetection() {
        let steps = [
            TestStep(id: 0, order: 0),
            TestStep(id: 1, order: 1, isTerminal: true),
        ]
        let flow = SymairaOnboardingFlow(steps: steps)
        flow.advance()
        XCTAssertTrue(flow.currentStep.isTerminal)
        let outcome = flow.advance()
        XCTAssertEqual(outcome, .finished)
        XCTAssertTrue(flow.isFinished)
    }

    func testFinishSetsIsFinishedDirectly() {
        let flow = makeFlow()
        flow.finish()
        XCTAssertTrue(flow.isFinished)
    }

    func testStepsAreSortedByOrderRegardlessOfInputOrder() {
        let steps = [
            TestStep(id: 2, order: 2),
            TestStep(id: 0, order: 0),
            TestStep(id: 1, order: 1),
        ]
        let flow = SymairaOnboardingFlow(steps: steps)
        XCTAssertEqual(flow.steps.map(\.id), [0, 1, 2])
    }

    func testProgressFractionSpansZeroToOne() {
        let flow = makeFlow(count: 3)
        XCTAssertEqual(flow.progressFraction, 0, accuracy: 0.0001)
        flow.advance()
        XCTAssertEqual(flow.progressFraction, 0.5, accuracy: 0.0001)
        flow.advance()
        XCTAssertEqual(flow.progressFraction, 1, accuracy: 0.0001)
    }

    func testSingleStepFlowReportsFullProgressAndIsBothEnds() {
        let flow = makeFlow(count: 1)
        XCTAssertTrue(flow.isFirstStep)
        XCTAssertTrue(flow.isLastStep)
        XCTAssertEqual(flow.progressFraction, 1, accuracy: 0.0001)
    }
}
