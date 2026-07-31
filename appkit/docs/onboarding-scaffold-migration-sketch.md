# Onboarding scaffold migration sketch

This is a sketch, not a migration — `symaira-desktop` is not checked out
here and is not touched. It shows how its enum-based `OnboardingView` step
model would adopt `SymairaOnboardingScaffold` (`Sources/SymairaTheme/Onboarding.swift`).

## Today (symaira-desktop, sketch of the existing shape)

```swift
enum Step: Int, CaseIterable {
    case welcome
    case vaultPicker
    case indexing
    case done
}

struct OnboardingView: View {
    @State private var step: Step = .welcome
    // ~455 lines: progress bar, back/next buttons, VoiceOver
    // announcements, and per-case content all hand-rolled here.
}
```

## After adopting the scaffold

The enum only needs to pick up `SymairaOnboardingStep` — `Hashable` and
`CaseIterable` are already satisfied by the raw-value enum, `Identifiable`
comes for free via `self`, and `order` maps straight from `rawValue`:

```swift
enum Step: Int, CaseIterable, SymairaOnboardingStep {
    case welcome
    case vaultPicker
    case indexing
    case done

    var id: Self { self }
    var order: Int { rawValue }
    var isTerminal: Bool { self == .done }
    var isSkippable: Bool { self != .done }
}

struct OnboardingView: View {
    @State private var flow = SymairaOnboardingFlow(steps: Array(Step.allCases))

    var body: some View {
        SymairaOnboardingScaffold(flow: flow, title: title(for:)) { step in
            switch step {
            case .welcome: WelcomeStepContent()
            case .vaultPicker: VaultPickerStepContent()
            case .indexing: IndexingStepContent()
            case .done: DoneStepContent()
            }
        } onFinish: {
            completeOnboarding() // app-owned persistence, unchanged
        }
    }

    private func title(for step: Step) -> String {
        switch step {
        case .welcome: "Welcome"
        case .vaultPicker: "Choose a vault"
        case .indexing: "Indexing"
        case .done: "You're set"
        }
    }
}
```

What moves out of `OnboardingView` and into the shared scaffold: the
progress bar, back/next/skip chrome, the terminal-step "Finish" label,
keyboard shortcuts, and the VoiceOver step-position announcement plus
focus-on-change. What stays app-owned: the four `*StepContent` views,
`completeOnboarding()` persistence, and the enum's own cases — the
scaffold never sees or constrains the case set.

The other two clients (`symaira-terminal`, an `Int`-indexed flow; and
`symaira-vibecoder`, a bespoke step struct) adopt the same protocol by
implementing `order`/`isSkippable`/`isTerminal` on their own step type —
neither needs to introduce an enum or an int index it doesn't already have.
