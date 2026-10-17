# Shared workspace foundation

The Cockpit pilot is a consumer of `SymairaTheme`, not a private fork of its
design rules. See [the design contract](../DESIGN.md) and the
[canonical visual specification](../design/liquid-topography/DESIGN.md).

## Native macOS usage

```swift
import SwiftUI
import SymairaTheme

struct Workspace: View {
    @Environment(\.openSettings) private var openSettings
    @State private var sidebar = SymairaSidebarState()
    @State private var topography = SymairaTopoModel()

    var body: some View {
        SymairaWorkspace(
            sidebar: $sidebar, topography: topography,
            navigation: { showsLabels in
                VStack {
                    SymairaNavigationButton(
                        "Overview", systemImage: "house", isSelected: true,
                        showsLabel: showsLabels, action: {}
                    )
                    Spacer()
                }.padding(SymairaSpacing.medium)
            },
            content: {
                ScrollView {
                    Text("Your product content")
                        .topoProtected()
                        .padding(SymairaSpacing.xLarge)
                }
            }
        )
        .toolbar {
            SymairaWorkspaceToolbar(sidebar: $sidebar) { openSettings() }
        }
    }
}
```

Apply `.symairaWorkspaceWindow()` to the containing `WindowGroup` for the native
titled/unified header. Do not apply a content font to the toolbar's ancestor.
The host owns persistence and applies a restored appearance on launch. Its
existing preference keys must not change. Passive previews use in-memory state.
Register a native `Settings { }` scene for the gear action and Cmd-comma. Put
`SymairaAppearancePicker(selection:)` inside that settings form, backed by the
host's existing preference key. Apply appearance changes from settings so they
affect every open window even when the main workspace is closed. A native
AppKit host supplies its existing preferences-window action instead.
Omit `topography` for dense lists/settings. `animationEnabled: false` requests a
static background without turning off layout protection; true still respects
Reduce Motion, low power and window visibility. The workspace does not own a
ScrollView, so editors, grids and existing ScrollViewReader navigation can keep
their own content lifecycle.

## Approved rule inventory

| Rule | AppKit owner | Product responsibility |
| --- | --- | --- |
| Gray palette, Google Sans Flex, optical size, font licensing | Generated `SymairaTokens`, `SymairaFont`, typography roles | Use roles; do not vendor a second theme |
| Topography animation, clipping and readable protection | `SymairaTopoView`, `.topoProtected()`, `symairaTopography` environment | Protect individual text bounds before padding/expansion, not whole header stacks; cards retain full protection |
| Rounded main panel, 20 pt radius, 8 pt trailing/bottom inset | `SymairaWorkspace` | Content width and navigation destinations |
| Continuous sidebar/toolbar chrome, transparency/contrast fallbacks | `SymairaWorkspace`, existing glass helpers | Product content only |
| Native title bar and toolbar item placement | `.symairaWorkspaceWindow()`, `SymairaWorkspaceToolbar` | Scene title, sidebar binding, settings-window callback |
| Sidebar default 272 pt, expanded 224–360 pt, 64 pt icon rail | `SymairaSidebarState` | Keep state at window lifetime; compose labels/icons |
| At least 568 pt reserved for content while expanded | `SymairaSidebarState` | Product minimum window size and compact content layout |
| 10 pt drag target, horizontal resize cursor, snap threshold 144 pt | Native sidebar adapter | No extra event monitors or copied resize algorithm |
| Keep mounted content and last chosen width on toolbar toggles | Workspace + sidebar state | Avoid identity-reset workarounds |
| Native splitter semantics, arrow keys and toolbar shortcut | Sidebar adapter + `SymairaSidebarToggle` | Localized labels/focus in product rows |
| Stable action geometry across primary/secondary state | Button styles + `SymairaMetrics.contentAction*` | Stable label area, title and action callback |
| Neutral slider/meter rails and fills | `SymairaBarColors`, `SymairaProgressStyle` | Native slider mechanics, units, warning text/icons |
| Navigation geometry, selection/hover/pressed colors, focus and AX | `SymairaNavigationButton` | Destination, clear label, symbol, selection and action |
| System/Light/Dark control inside settings | `SymairaAppearance`, `SymairaAppearancePicker` | Existing persistence namespace; no writes from previews |
| One trailing native gear, direct action with no submenu | `SymairaSettingsButton` inside shared toolbar | Open/reuse native settings window; no duplicate sidebar/parent-toolbar entry |
| Opaque forms/notices; bounded empty/loading text protection | `SymairaFormSection`, `SymairaNotice`, `SymairaEmptyState`, `SymairaLoadingState` | Domain fields, messages and retry actions |

Button roles use the same font and 20 pt horizontal padding. Changing text can
still change an unconstrained intrinsic width; reserve the label area or make a
stateful action full-width. No API can infer every future localized label.
Disabled/pressed states must not change layout. Semantic safety/status cues are
never removed to obtain uniform gray meters.

## Boundary assessment and adoption

Cockpit's tuning window and Brain/Desktop's existing sidebar-based native
workspaces need the same design primitives; they do not share domain screens.
The library adds no product module or third-party dependency. Cockpit is the
first wired consumer. EraseMe now consumes the shared workspace, toolbar, navigation,
forms and feedback locally. Cockpit's existing composed toolbar is the reference;
its worktree is not modified by EraseMe's adoption. Brain and Desktop still require their own deliberate
pin update and integration; this is not a claim that either app was migrated.

`KeepAwakeCard`, sensor logic, preferences storage identities and per-product
navigation remain in Cockpit. Thin compatibility aliases can delegate to
AppKit, but contain no second rendering implementation. The native shell and
NSAppearance application API are macOS-only; colors, action styles, meters,
appearance vocabulary/picker and explicit topography protection remain shared
with iOS. Other platforms follow the canonical visual contract and exports,
not Swift imports.

## Verification contract

- AppKit tests exercise real NSWindow mouse routing, width bounds, retained
  control identity and protected geometry with animation paused.
- Render regressions compare primary/secondary action dimensions in light/dark,
  with intrinsic and full-width labels, and retain different state colors.
- Consumer tests exercise its actual controls and preference namespace separately.
- Full-window captures verify composition, not physical keyboard or VoiceOver.
- The design generator/contrast checks and strict source formatting remain gates.
- Local edits become available to other released products only after AppKit is
  reviewed/tagged and each consumer explicitly adopts the new exact version.

For local integration, editable dependencies are scoped to the SwiftPM scratch
directory. A `Packages/symaira-appkit` link alone does not prove the build uses
it. Configure edit mode and inspect `swift package --scratch-path <build-dir>
show-dependencies --format json` using the same build directory as the test and
app-assembly commands. Require the resolved AppKit path to equal the intended
worktree; otherwise the build can silently use the old remote pin. Preserve the
tracked lockfile and do not patch a cached checkout to compensate.
