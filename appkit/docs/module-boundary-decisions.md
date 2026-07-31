# Module boundary decisions

`AGENTS.md` states the rule: *a module belongs here only if ≥2 apps need it.* Applying
that rule takes an assessment, and an assessment that is not written down gets
repeated. This file records each one — including the ones that ended in "no".

A decision recorded here is not permanent. It is a snapshot of the evidence at a
point in time; a new consumer is a reason to reopen it.

---

## 2026-07-31 — `SymairaUI` stays in `symaira-terminal`

**Question.** `symaira-terminal` maintains a local `SymairaUI` module. appkit ships no
SwiftUI view module. Should the general parts move here?

**Verdict: no.** Nothing in `SymairaUI` is product-independent today.

### Inventory

23 files, ~3,780 lines under
`symaira-terminal/Packages/SymairaKit/Sources/SymairaUI/`.

**18 files import a terminal domain module** (`AgentKit`, `ProviderKit`, `StackKit`,
`WorktreeKit`, `ContextBank`, `UsageKit`, `TerminalCore`) and are product-specific by
construction:

| View | Depends on |
|---|---|
| `CommandInputEditor` | `TerminalCore` |
| `ContextBankPanel`, `ContextFileEditor`, `ContextFileListView` | `ContextBank` |
| `DiffReviewPanel`, `WorktreeListView`, `WorktreeStore` | `WorktreeKit` |
| `FixErrorService`, `FixErrorView` | `AgentKit`, `ProviderKit`, `TerminalCore` |
| `OnboardingView`, `ProviderSettingsView`, `ProviderStore` | `ProviderKit` |
| `SettingsView` | `AgentKit`, `ProviderKit`, `StackKit` |
| `StackSettingsView` | `StackKit` |
| `StatusRing` | `AgentKit` |
| `UsageDetailView`, `UsageStore`, `UsageSummaryView` | `UsageKit` |

The three that sound generic from their names are the clearest cases:

- `OnboardingView` is bound to `ProviderStore` — it onboards an AI provider setup.
- `SettingsView` composes `WorkspaceConfigManager`, `ProviderStore` and `StackStore`,
  and exposes `defaultShell` and `scrollbackLines`. That is a terminal's settings
  screen, not a settings screen.
- `StatusRing` renders agent state from `AgentKit`.

**5 files import no terminal module** — and none of them survives a second look:

| View | Why it still does not belong here |
|---|---|
| `BrowserPane` (281) | `WebKit` pane for the terminal's browser feature. No second consumer. |
| `WorkflowCanvasView` (127) | `WebKit` canvas for agent workflows. Product concept. |
| `SketchpadView` (196) | `AppKit` drawing surface. No second consumer. |
| `DiffView` (88) | Generic in principle. No second consumer — no other client renders diffs. |
| `STTService` (141) | Not a view, and built on Apple's `Speech`. See below. |

`STTService` deserves the explicit note because `symaira-meet` is the transcription
product and looks like an obvious second consumer. It is not: `symaira-meet` runs on
**WhisperKit**, a different engine with different output. Sharing an Apple-`Speech`
wrapper between them would serve neither, and WhisperKit is a third-party dependency
that appkit does not accept.

### Second-consumer check

`import SymairaUI` appears only inside `symaira-terminal` (`App/`, `AppTests/`,
`Packages/SymairaKit/Tests/`). No other repository consumes it.

The `SymairaFormSection` / `SymairaFormRow` scaffold added in 0.6.2 already covers the
one genuinely shared need this assessment set out to test — settings surfaces — without
moving a single view out of `symaira-terminal`.

### What the assessment did surface

Three repositories implement a multi-step onboarding flow independently:

| Repo | File | Lines | Step model |
|---|---|---|---|
| `symaira-desktop` | `Sources/SymDeskApp/UI/OnboardingView.swift` | 455 | `enum Step` with named cases |
| `symaira-terminal` | `Packages/SymairaKit/Sources/SymairaUI/OnboardingView.swift` | 303 | `Int` index |
| `symaira-vibecoder` | `client/Sources/SymvibeApp/Views/OnboardingView.swift` | 263 | own |

That is a shared *pattern*, not shared code — each flow onboards a different thing.
It argues for a small generic step-flow scaffold written from scratch here, not for
lifting `symaira-terminal`'s provider onboarding into appkit. Tracked separately.

### Revisit when

- A second repository needs `DiffView`-style diff rendering, or
- a third client starts a settings surface that `SymairaFormSection` cannot carry, or
- the generic step-flow scaffold lands and turns out to want companions.
