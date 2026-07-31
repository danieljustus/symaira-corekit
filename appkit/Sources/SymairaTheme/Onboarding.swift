import SwiftUI

// MARK: - Step identity

/// Identity and order for one onboarding step.
///
/// Three clients each model their steps differently — an `enum` with named
/// cases, an `Int` index, and a bespoke struct. None of those shapes should
/// be forced on the others, so identity here is only `Hashable & Identifiable`
/// plus an explicit `order` for sorting. A conforming type can be an enum, a
/// struct wrapping an int, or anything else; the scaffold never assumes Int
/// indexing or a closed case set.
public protocol SymairaOnboardingStep: Hashable, Identifiable, Sendable {
    /// Position among sibling steps. Only used for sorting and progress math —
    /// never as a lookup key, so gaps and non-contiguous values are fine.
    var order: Int { get }

    /// Whether skipping is offered on this step.
    var isSkippable: Bool { get }

    /// Whether advancing from this step finishes the flow.
    var isTerminal: Bool { get }
}

extension SymairaOnboardingStep {
    public var isSkippable: Bool { true }
    public var isTerminal: Bool { false }
}

// MARK: - Flow state

/// Outcome of a step transition, for callers that want to react to skip vs.
/// finish vs. an ordinary advance.
public enum SymairaOnboardingOutcome: Sendable {
    case advanced
    case retreated
    case skipped
    case finished
}

/// Pure state machine driving an onboarding flow: current step, progress,
/// and the four transitions (advance, retreat, skip, finish). Holds no
/// SwiftUI dependency so it is testable without a view host.
@MainActor
@Observable
public final class SymairaOnboardingFlow<Step: SymairaOnboardingStep> {
    public private(set) var steps: [Step]
    public private(set) var currentIndex: Int
    public private(set) var isFinished: Bool

    public init(steps: [Step]) {
        precondition(!steps.isEmpty, "SymairaOnboardingFlow requires at least one step")
        self.steps = steps.sorted { $0.order < $1.order }
        self.currentIndex = 0
        self.isFinished = false
    }

    public var currentStep: Step { steps[currentIndex] }

    public var isFirstStep: Bool { currentIndex == 0 }

    public var isLastStep: Bool { currentIndex == steps.count - 1 }

    /// 1-based position for progress copy ("Step 2 of 5").
    public var position: Int { currentIndex + 1 }

    public var stepCount: Int { steps.count }

    public var progressFraction: Double {
        guard steps.count > 1 else { return 1 }
        return Double(currentIndex) / Double(steps.count - 1)
    }

    @discardableResult
    public func advance() -> SymairaOnboardingOutcome {
        guard !isFinished else { return .finished }
        if isLastStep || currentStep.isTerminal {
            isFinished = true
            return .finished
        }
        currentIndex += 1
        return .advanced
    }

    @discardableResult
    public func retreat() -> SymairaOnboardingOutcome? {
        guard !isFinished, !isFirstStep else { return nil }
        currentIndex -= 1
        return .retreated
    }

    @discardableResult
    public func skip() -> SymairaOnboardingOutcome? {
        guard !isFinished, currentStep.isSkippable else { return nil }
        return advance() == .finished ? .finished : .skipped
    }

    public func finish() {
        isFinished = true
    }
}

// MARK: - SwiftUI scaffold

/// Chrome and flow for a multi-step onboarding container. The client supplies
/// only step content via `content`; progress, navigation, skip/finish, and
/// accessibility live here.
public struct SymairaOnboardingScaffold<Step: SymairaOnboardingStep, Content: View>: View {
    @Bindable private var flow: SymairaOnboardingFlow<Step>
    private let title: (Step) -> String
    private let content: (Step) -> Content
    private let onFinish: () -> Void

    @AccessibilityFocusState private var isContentFocused: Bool
    @State private var announcedPosition: Int = 0

    public init(
        flow: SymairaOnboardingFlow<Step>,
        title: @escaping (Step) -> String,
        @ViewBuilder content: @escaping (Step) -> Content,
        onFinish: @escaping () -> Void
    ) {
        self.flow = flow
        self.title = title
        self.content = content
        self.onFinish = onFinish
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: SymairaSpacing.xLarge) {
            progressIndicator

            Text(title(flow.currentStep))
                .symairaText(.title)
                .accessibilityAddTraits(.isHeader)
                .accessibilityFocused($isContentFocused)

            content(flow.currentStep)
                .frame(maxWidth: .infinity, alignment: .leading)

            Spacer(minLength: 0)

            navigationBar
        }
        .padding(SymairaSpacing.xLarge)
        .onAppear { announce(position: flow.position) }
        .onChange(of: flow.currentIndex) { _, _ in
            isContentFocused = true
            announce(position: flow.position)
        }
        .onChange(of: flow.isFinished) { _, isFinished in
            if isFinished { onFinish() }
        }
    }

    private var progressIndicator: some View {
        VStack(alignment: .leading, spacing: SymairaSpacing.xSmall) {
            ProgressView(value: flow.progressFraction)
                .tint(SymairaTheme.goldPrimary)

            Text("Step \(flow.position) of \(flow.stepCount)")
                .symairaText(.caption)
                .accessibilityLabel("Step \(flow.position) of \(flow.stepCount)")
        }
    }

    private var navigationBar: some View {
        HStack(spacing: SymairaSpacing.medium) {
            if !flow.isFirstStep {
                Button("Back") { flow.retreat() }
                    .symairaButtonStyle(.secondary)
                    .keyboardShortcut(.leftArrow, modifiers: [])
            }

            Spacer()

            if flow.currentStep.isSkippable && !flow.currentStep.isTerminal {
                Button("Skip") { flow.skip() }
                    .symairaButtonStyle(.toolbar)
            }

            Button(flow.currentStep.isTerminal ? "Finish" : "Next") { flow.advance() }
                .symairaButtonStyle(.primary)
                .keyboardShortcut(.rightArrow, modifiers: [])
        }
    }

    private func announce(position: Int) {
        guard position != announcedPosition else { return }
        announcedPosition = position
        #if os(macOS) || os(iOS)
        AccessibilityNotification.Announcement(
            "Step \(position) of \(flow.stepCount)"
        ).post()
        #endif
    }
}

/*
 Migration sketch: symaira-desktop's `OnboardingView` (enum-based `Step`)
 adopting this scaffold — see docs/onboarding-scaffold-migration-sketch.md.
 */
