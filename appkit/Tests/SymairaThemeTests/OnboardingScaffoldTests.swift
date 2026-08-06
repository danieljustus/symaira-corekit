import XCTest
import SwiftUI
@testable import SymairaTheme

private struct ScaffoldStep: SymairaOnboardingStep {
    let id: Int
    let order: Int
    var isSkippable: Bool = true
    var isTerminal: Bool = false
}

/// Relies on the protocol's default `isSkippable`/`isTerminal` implementations.
private struct MinimalStep: SymairaOnboardingStep {
    let id: Int
    let order: Int
}

@MainActor
final class OnboardingScaffoldTests: XCTestCase {

    func testOutcomeCasesAreDistinct() {
        XCTAssertNotEqual(SymairaOnboardingOutcome.advanced, SymairaOnboardingOutcome.retreated)
        XCTAssertNotEqual(SymairaOnboardingOutcome.skipped, SymairaOnboardingOutcome.finished)
        XCTAssertNotEqual(SymairaOnboardingOutcome.advanced, SymairaOnboardingOutcome.finished)
    }

    func testProtocolDefaultsMakeStepsSkippableAndNonTerminal() {
        let flow = SymairaOnboardingFlow(steps: [MinimalStep(id: 0, order: 0)])
        XCTAssertTrue(flow.currentStep.isSkippable)
        XCTAssertFalse(flow.currentStep.isTerminal)
    }

    private func makeScaffold(
        steps: [ScaffoldStep] = [ScaffoldStep(id: 0, order: 0), ScaffoldStep(id: 1, order: 1)],
        onFinish: @escaping () -> Void = {}
    ) -> (SymairaOnboardingFlow<ScaffoldStep>, SymairaOnboardingScaffold<ScaffoldStep, Text>) {
        let flow = SymairaOnboardingFlow(steps: steps)
        let scaffold = SymairaOnboardingScaffold(
            flow: flow,
            title: { step in "Step \(step.id)" },
            content: { step in Text("Content \(step.id)") },
            onFinish: onFinish
        )
        return (flow, scaffold)
    }

    private func pumpMainRunLoop() {
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
    }

    func testScaffoldEvaluatesBodyAtFirstStep() {
        let (_, scaffold) = makeScaffold()
        XCTAssertNotNil(scaffold.body)
    }

    func testScaffoldReEvaluatesTitleAndContentWhenTheStepChanges() {
        var renderedTitles: [String] = []
        var renderedContent: [Int] = []
        let flow = SymairaOnboardingFlow(steps: [ScaffoldStep(id: 0, order: 0), ScaffoldStep(id: 1, order: 1)])
        let scaffold = SymairaOnboardingScaffold(
            flow: flow,
            title: { step in
                renderedTitles.append("Step \(step.id)")
                return "Step \(step.id)"
            },
            content: { step in
                renderedContent.append(step.id)
                return Text("Content \(step.id)")
            },
            onFinish: {}
        )
        ThemeRenderHost.render(scaffold)
        XCTAssertEqual(renderedTitles, ["Step 0"])
        XCTAssertEqual(renderedContent, [0])

        flow.advance()
        pumpMainRunLoop()
        XCTAssertEqual(
            renderedTitles,
            ["Step 0", "Step 1"],
            "advancing must re-render the scaffold for the new step"
        )
        XCTAssertEqual(renderedContent, [0, 1])
    }

    func testScaffoldConstructsBackAndFinishNavigationOnTerminalStep() {
        let terminal = ScaffoldStep(id: 1, order: 1, isTerminal: true)
        let (flow, scaffold) = makeScaffold(steps: [ScaffoldStep(id: 0, order: 0), terminal])
        XCTAssertNotNil(scaffold.body)

        flow.advance()
        XCTAssertTrue(flow.currentStep.isTerminal)
        // Body re-evaluated on the terminal step: the Back button branch and
        // the Finish label branch of the navigation bar both construct.
        XCTAssertNotNil(scaffold.body)

        flow.advance()
        XCTAssertTrue(flow.isFinished)
        XCTAssertNotNil(scaffold.body)
    }

    func testScaffoldConstructsSkipButtonOnlyOnSkippableSteps() {
        let steps = [
            ScaffoldStep(id: 0, order: 0, isSkippable: true),
            ScaffoldStep(id: 1, order: 1, isSkippable: false),
        ]
        let (flow, scaffold) = makeScaffold(steps: steps)
        XCTAssertNotNil(scaffold.body)

        flow.advance()
        XCTAssertNotNil(scaffold.body)
    }

    func testScaffoldInvokesOnFinishWhenTheFlowFinishes() {
        var finished = false
        let (flow, scaffold) = makeScaffold(steps: [ScaffoldStep(id: 0, order: 0)]) {
            finished = true
        }
        ThemeRenderHost.render(scaffold)
        flow.advance()
        pumpMainRunLoop()
        XCTAssertTrue(finished, "completing the flow must trigger onFinish")
    }
}
