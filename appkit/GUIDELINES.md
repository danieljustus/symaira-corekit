# Symaira Interface Guidelines

Rules for building and reviewing Symaira app surfaces, so that any agent or
person produces the same intuitive, uncluttered result without re-deriving the
design each time. This file owns structure, behavior, states, copy, keyboard,
accessibility and the review contract. The other three documents stay
authoritative for their part:

| Document | Owns |
| --- | --- |
| [`design/liquid-topography/DESIGN.md`](design/liquid-topography/DESIGN.md) | Normative tokens: colors, type, radii, spacing, topography parameters |
| [`DESIGN.md`](DESIGN.md) | Material hierarchy, platform behavior, accessibility defaults, API migration table |
| [`docs/workspace-foundation.md`](docs/workspace-foundation.md) | Shell API usage and the approved rule inventory with owners |

Where this file is silent, Apple's Human Interface Guidelines apply.

Every rule has an ID for reviews (`STATE-1`), one imperative sentence and the
`SymairaTheme` API that implements it. "Product" means an app repository that
consumes `symaira-appkit` through an exact pin.

## How to use

- **Building:** read this file, then `DESIGN.md`, then
  `docs/workspace-foundation.md`. Write the screen card (section 2) before
  writing code.
- **Reviewing:** run `python3 scripts/gui-review.py <swift-source-root>` for
  the mechanical rules, then walk the manual checklist in section 13. Report
  as `file:line - RULE-ID severity message`.
- **Changing a rule:** change it here together with its implementation and
  regression check, verify it in one real consumer, tag a release. Consumers
  adopt by updating their exact pin. Never patch a product to satisfy a rule
  that its pinned AppKit version does not ship yet.

## 1. Non-negotiables

- **NN-1** Tool before show: a decorative element must serve hierarchy,
  affordance, continuity or feedback; otherwise delete it.
- **NN-2** Roles, never raw values: colors from `SymairaTokens` and
  `SymairaTheme`, type from `SymairaTypography` or `.symairaText(_:)`,
  spacing from `SymairaSpacing`, radii from `SymairaTokens.Radius`.
- **NN-3** Champagne (`primary`) is a brand accent that the shared controls
  already apply; state uses `selected`, `onSelected` and `focus`. Champagne is
  never a text color or a state signal.
- **NN-4** One primary action per screen (`.symairaButtonStyle(.primary)`);
  every other action is secondary or a toolbar control.
- **NN-5** Every screen that loads data has loading, empty, error and
  unreachable states; none of them is a blank area or a spinner without words.
- **NN-6** Status is text or icon plus color, never color alone
  (`SymairaTone` through `SymairaStatusLabel`, `SymairaBadge`,
  `SymairaNotice`).
- **NN-7** Readability outranks topography and glass: text and controls are
  `.topoProtected()`, reading surfaces are opaque (`.symairaCard()`), glass is
  navigation chrome only.
- **NN-8** Destructive or consequential actions are confirmed with the verb in
  the button, or they are undoable; never immediate, never "OK".
- **NN-9** Everything reachable by pointer is reachable by keyboard and named
  for VoiceOver.
- **NN-10** Product logic, destinations, domain models and preference keys stay
  in the product; a reusable design or interaction rule moves here first.

## 2. Screen card (write before coding)

Six lines, kept in the pull request or issue:

1. **Destination:** where the screen sits in the sidebar (3 to 7 top-level
   destinations per app).
2. **Job:** the one thing the user comes here to do, which is the primary
   action.
3. **Data:** what loads, from where (CLI, MCP, HTTP), how stale it may be.
4. **States:** loading text, empty title plus message plus next action, error
   retry, unreachable backend.
5. **Density:** prose column (`SymairaMetrics.readableContentWidth`),
   dashboard grid, or table.
6. **Platform:** macOS workspace, iOS, or both; preference keys touched.

## 3. Shell and navigation (macOS)

- **SHELL-1** Use `SymairaWorkspace(sidebar:topography:navigation:content:)`
  with `SymairaSidebarState`; do not build a second shell, split view or
  sidebar.
- **SHELL-2** Apply `.symairaWorkspaceWindow()` to the `WindowGroup` and mount
  `SymairaWorkspaceToolbar(sidebar:openSettings:)`; the gear opens the native
  `Settings { }` scene directly, without a menu in between.
- **SHELL-3** Sidebar destinations use
  `SymairaNavigationButton(_:icon:isSelected:showsLabel:action:)` with a
  `SymairaIcon` and a clear noun label. Settings is never a destination.
- **SHELL-4** Minimum window width is the default sidebar plus
  `SymairaSidebarState.contentReserve` (272 + 568 = 840 pt). Products set
  `.frame(minWidth:minHeight:)` at or above 840 × 560 and a `.defaultSize`.
- **SHELL-5** Windows are freely resizable, restore their frame, and keep
  mounted content, drafts and scroll position across sidebar toggles.
- **SHELL-6** The sidebar holds navigation and one compact status line
  (`SymairaStatusLabel`, or `SymairaStatusDot` in the icon rail); no forms and
  no actions in it.
- **SHELL-7** Settings live in `SymairaSettingsScene { }` (native `Settings`,
  ⌘,), opened directly by `SymairaSettingsButton()` on macOS, and contain
  `SymairaAppearancePicker(selection:)` bound to the product's existing
  preference key; appearance changes apply to every open window.
- **SHELL-8** Pass `topography:` only for the main overview; omit it behind
  dense lists, tables and settings.
- **SHELL-9** Provide `.commands { SymairaCommands(destinations:selection:) }`
  using the same ordered destinations and product-owned selection as the sidebar
  for ⌘1 to ⌘9; add native commands for primary actions and ⌘R refresh alongside
  it. `SymairaSidebarState` continues to own layout, not navigation selection.

## 4. Screen layout

- **LAYOUT-1** Use `SymairaPage` for a stable title in
  `.symairaText(.display)` and a one-line subtitle, both `.topoProtected()`.
  The subtitle may be omitted; its line remains reserved to align controls.
- **LAYOUT-2** Prose stays within `SymairaMetrics.readableContentWidth`;
  dashboards and tables may use a wider product-owned budget.
- **LAYOUT-3** Content that carries text sits on `.symairaCard()`; sections
  inside a card are separated by `SymairaFormDivider()` and a
  `.sectionLabel`, not by a second card.
- **LAYOUT-4** Lists with more than roughly eight homogeneous rows become a
  native `Table` with sortable columns; shorter or heterogeneous lists are
  cards or rows.
- **LAYOUT-5** No nested scroll views: either the page scrolls or the table
  scrolls, never both.
- **LAYOUT-6** Spacing comes from `SymairaSpacing` (4 pt grid): page padding
  `xLarge`, gaps between cards `medium`, inside cards `small`.
- **LAYOUT-7** A toolbar row inside a page has a fixed height, so switching
  pages does not shift the content below it.
- **LAYOUT-8** Dashboards order summary tiles (value in
  `SymairaTypography.stat`) first, then charts, then tables, then event logs;
  at most five tiles in one row.

## 5. States and feedback

- **STATE-1** Loading: `SymairaLoadingState("Loading campaigns…")` with a
  specific noun and the ellipsis character; never a bare `ProgressView()`.
- **STATE-2** Empty: `SymairaEmptyState(icon:title:message:actions:)` with a
  title that names what is missing, a message that says how it gets filled,
  and at most one action that does exactly that. A nested empty section may
  use one muted caption line instead.
- **STATE-3** Error: `SymairaNotice(message:tone:onDismiss:)` with
  `.critical`, or the empty-state layout with a Retry action; the message names
  the cause and the next step.
- **STATE-4** Unreachable backend: a persistent `SymairaStatusLabel` in the
  sidebar plus the error state where content would start; never silent zeros.
- **STATE-5** Success: an inline `SymairaNotice` with `.positive` or a status
  change; no modal alert for success. Page loading/error/empty placeholders use
  `SymairaPageState` and `SymairaPageEmpty` with one shared fixed state height,
  so state changes do not shift the page toolbar.
- **STATE-6** A disabled control carries `SymairaLockedLabel` or a caption
  that says why; opacity alone is not a signal.
- **STATE-7** Progress with a known duration uses `SymairaProgressStyle`;
  unknown duration uses `SymairaLoadingState`; both keep the layout size
  stable.
- **STATE-8** Counts and summaries render only from loaded data; after a
  failed load the error appears where content would start, not zero values.
- **STATE-9** Topography follows the app state through `SymairaTopoModel`:
  `.thinking` while working, `.problem` on failure, `.input` when a field
  needs the user, `.idle` otherwise. The information still lives in text.

## 6. Actions, dialogs and destructive operations

- **ACTION-1** Button labels are specific verbs ("Execute Campaign",
  "Save API Key"); never "OK", "Continue", "Yes", "Submit".
- **ACTION-2** Primary and secondary content actions share geometry through
  `.symairaButtonStyle(.primary/.secondary)` and `SymairaSheetScaffold`
  (`SymairaMetrics.contentActionHeight`, 20 pt horizontal padding). Switching
  role or label must not change size; reserve width for stateful labels.
- **ACTION-3** Confirm consequential or irreversible actions with
  `confirmationDialog` or `.alert`: the primary button repeats the verb, the
  message states the consequence in one sentence, `Cancel` has
  `role: .cancel`.
- **ACTION-4** Prefer undo (`UndoManager`, ⌘Z) over confirmation for local,
  reversible deletes; mark the control with `role: .destructive`.
- **ACTION-5** Sheets share one scaffold: heading, scrolling content, footer
  with the secondary dismiss button left of the primary action, Esc cancels
  (`.cancelAction`), Return confirms (`.defaultAction`).
- **ACTION-6** Sheets are for multi-step or multi-field work; a single toggle
  or small choice is inline or a popover.
- **ACTION-7** Long-running actions disable their trigger, show progress where
  the result will appear, and stay cancelable.
- **ACTION-8** No modal alert for information; use `SymairaNotice`.
- **ACTION-9** Table rows and cards expose their actions in a `.contextMenu`
  as well as inline.

## 7. Forms and settings

- **FORM-1** Build forms from `SymairaFormSection(_:footer:content:)`,
  `SymairaFormRow(_:description:trailing:)` and `SymairaFormDivider()`; not
  from `Form`, `GroupBox` or ad-hoc stacks.
- **FORM-2** Fields use `.textFieldStyle(.symaira)`; the row carries the
  label, the placeholder shows an example or the default ("Auto-detect",
  "Default (~/Library/…)").
- **FORM-3** Validate inline below the field (`.caption` in `critical`) and
  move focus to the first error on submit; never block paste.
- **FORM-4** Secrets use `SecureField`, are stored through `SymairaKeychain`,
  and never appear in error text or logs.
- **FORM-5** Two to four options are a `SymairaSegmentedControl`; longer lists
  are a `SymairaFilterMenu` whose first option is the unfiltered default;
  on/off is `.toggleStyle(.symairaSwitch)`.
- **FORM-6** Settings persist under the product's existing keys; previews and
  tests write nothing.
- **FORM-7** Group settings by task (Connection, Configuration, Appearance,
  About); a section footer explains consequences where they exist.
- **FORM-8** Onboarding uses `SymairaOnboardingScaffold` with
  `SymairaOnboardingFlow`; steps are skippable unless they gate the product.

## 8. Color, typography and icons

- **COLOR-1** Use adaptive roles (`SymairaTokens.ink`, `ink2`, `ink3`,
  `surface`, `raised`, `line`, `positive`, `warning`, `critical`); no
  `Color(hex:)`, no `.red`, `.green`, `.orange`, no `Color.white` or
  `Color.black` on surfaces.
- **COLOR-2** `selected`, `onSelected` and `focus` carry state; `primary` is
  reserved for the brand accents the shared controls already apply.
- **COLOR-3** Status colors always pair with `SymairaTone` text or icon. Live
  measured values are `ink`; sample data gets a neutral icon and the word
  "Example".
- **COLOR-4** In light appearance, controls placed directly on the canvas carry
  the 1 pt `SymairaTheme.raisedOutline(for:)`; never rely on fill alone.
- **TYPE-1** Fonts come from `SymairaTypography` roles or `.symairaText(_:)`
  (Google Sans Flex `opsz` 18 for display, titles, headings and metrics;
  Inter `opsz` 14 for running text, labels and captions); no `.font(.system(size:))` and no
  `.font(.headline)` or other system text styles.
- **TYPE-2** Numbers that update use tabular digits (`SymairaTypography.stat`,
  `.readout`, or `.monospacedDigit()`); numeric table columns align trailing.
- **TYPE-3** Weights: Inter body and captions 450, labels and buttons 550,
  emphasis and section labels 600; Google Sans Flex titles 650, headings and
  metrics 700; no other weights.
- **ICON-1** Icons are `SymairaIcon` cases through `SymairaIconView`,
  `SymairaIconButton`, `Label(_:symairaIcon:)` and the `icon:` initializers of
  the shared components. An SF Symbol string is acceptable only where no case
  exists, and then the case is added to `Brand/Icons/icons.svg` instead of
  staying in the product.
- **ICON-2** Icon-only controls carry `.accessibilityLabel` and `.help(...)`;
  `SymairaIconButton` does both.
- **ICON-3** Toolbar controls use `.symairaButtonStyle(.toolbar)` (glass);
  content actions never do.

## 9. Motion, materials and topography

- **MOTION-1** Topography sits behind the main overview only, passed as
  `topography:` to `SymairaWorkspace` (macOS) or `.symairaTopography(_:)`
  (iOS, IOS-5); never behind settings, tables or dense lists, and never
  mounted directly in a product.
- **MOTION-2** Every text-bearing element in a topography area is
  `.topoProtected()`; cards protect their whole surface (`hill: true`);
  headers protect each text, not the whole stack.
- **MOTION-3** Glass (`SymairaGlassEffectContainer`, `.symairaGlassChrome`) is
  for navigation chrome and floating controls; reading surfaces stay
  `surface` or `raised`.
- **MOTION-4** No gradients on surfaces, no textures or images as backgrounds,
  no shadows except on floating elements (menus, popovers, composer).
- **MOTION-5** Reduce Motion, Reduce Transparency and Low Power are honored by
  the shared components; product animations are limited to state transitions
  and are interruptible.
- **MOTION-6** `SymairaBackdrop`, `BlueprintGrid`, `AmbientGlows`,
  `.glassCard()`, `.glassmorphicPanel()` and the fixed `Color.symaira*`
  aliases are compatibility APIs; add no new call sites.

## 10. Keyboard, pointer and accessibility

- **KEY-1** Every primary action and destination has a ⌘ shortcut through menu
  commands (`SymairaCommands(destinations:selection:)` covers the first nine
  destinations); Esc cancels, Return confirms, Delete removes the selection in
  lists.
- **KEY-2** Tab order follows reading order; custom controls are
  `.focusable()` and show the 2 pt `focus` ring.
- **POINTER-1** Interactive rows and cards have a hover state; the shared
  styles provide it, a `.plain` button wrapper must add its own.
- **POINTER-2** Rows, cards and table cells have a `.contextMenu` with their
  relevant actions.
- **POINTER-3** Icon-only and truncated controls have `.help` tooltips.
- **A11Y-1** Every control has a meaningful `accessibilityLabel`; decorative
  images are `.accessibilityHidden(true)`.
- **A11Y-2** Status changes are announced through text (`SymairaStatusLabel`,
  `SymairaNotice`), not through color or motion.
- **A11Y-3** Touch targets are at least 44 pt on iOS; content actions are at
  least 40 pt on macOS (`SymairaMetrics`).
- **A11Y-4** Dynamic Type scales every role on iOS; never fix a frame height
  that clips at accessibility sizes.
- **A11Y-5** Increase Contrast strengthens outlines and Reduce Transparency
  replaces glass with opaque `sidebar`; both come from the shared components
  and must not be overridden.

## 11. Copy

- **COPY-1** The UI language is English unless the product is localized; no
  German defaults in shared or product code.
- **COPY-2** Title Case for window titles, destinations, section titles,
  buttons and menu items; sentence case for messages, captions and footers.
- **COPY-3** Ongoing work ends with the ellipsis character "…" ("Loading…",
  "Saving…"); never three dots.
- **COPY-4** Numerals for counts ("8 requests"); tabular digits where they
  update.
- **COPY-5** Error text says what happened and what to do next, in the second
  person, without stack traces or secrets.
- **COPY-6** Empty-state copy names the missing thing and the way to create
  it; no humor, no exclamation marks.
- **COPY-7** Product names are singular and spelled as in the brand assets
  (Symaira EraseMe, Symaira Cockpit); "SymSkills" is the only plural.

## 12. iOS

- **IOS-1** Use native `NavigationSplitView` and `TabView`; the drag-resizable
  desktop workspace is macOS only.
- **IOS-2** Shared colors, type roles, actions, meters, the appearance picker
  and `.topoProtected()` apply; `.preferredColorScheme(selection.colorScheme)`
  applies the appearance.
- **IOS-3** Primary actions sit at the bottom within thumb reach; destructive
  actions use confirmation sheets.
- **IOS-4** Low Power Mode pauses the topography; never force animation.
- **IOS-5** The main overview mounts the topography with
  `.symairaTopography(model)` inside its navigation stack, the iOS counterpart
  of `SymairaWorkspace(topography:)`; dense lists, tables and settings pass
  `nil` or omit it (MOTION-1).
- **IOS-6** Tab bar items use `Label { Text(title) } icon: { Image(symairaIcon:) }`;
  the tab bar renders only `Image`, so `Label(_:symairaIcon:)` shows no icon
  there.

## 13. Review contract

Report per file, VS Code clickable, terse:

```text
## Sources/App/Views/RequestsView.swift
Sources/App/Views/RequestsView.swift:152 - STATE-1 warn bare ProgressView(); use SymairaLoadingState("Loading events…")

## project
project - POINTER-2 info no context menus on rows or cards
```

Severity: `error` violates a non-negotiable or the token contract; `warn`
violates a rule that has an existing shared replacement; `info` marks a
judgment call or a project-level absence.

**Mechanical** (`scripts/gui-review.py`): COLOR-1, TYPE-1, ICON-1, ICON-2,
STATE-1, ACTION-1, COPY-3, MOTION-1, MOTION-4, MOTION-6, FORM-1, SHELL-1, and
the project-level absences KEY-1, SHELL-7, SHELL-9, POINTER-2, POINTER-3.

**Manual checklist** (one pass per screen):

1. Section 2 screen card exists and matches the implementation.
2. NN-4: exactly one primary action.
3. STATE-1 to STATE-8: loading, empty, error and unreachable are all present
   and look like the shared components.
4. STATE-2: the empty state offers its one action when one exists.
5. ACTION-3 and ACTION-4: destructive paths are confirmed with the verb or are
   undoable.
6. ACTION-5: sheets use the scaffold with Esc and Return.
7. LAYOUT-1 and LAYOUT-5: stable header, no nested scrolling.
8. FORM-6: preference keys unchanged.
9. MOTION-1 and MOTION-2: topography placement and protection.
10. TYPE-2: numeric columns use tabular digits and trailing alignment.
11. A11Y-1: labels on every control.
12. Both appearances and Reduce Motion checked in a running build; say what
    was not run.

## 14. Anti-patterns (flag on sight)

- A second theme, token file, icon set or shell inside a product.
- `NavigationSplitView` as the macOS shell, hamburger menus, bottom tab bars on
  macOS, floating action buttons.
- A spinner without words; an empty list rendering as blank; zero counts after
  a failed load.
- "Are you sure?" with OK/Cancel; a destructive action without confirmation
  or undo.
- Champagne text, champagne as a state, gradients, glass behind text, shadows
  on cards.
- SF Symbol strings where a `SymairaIcon` exists; `.font(.system(size:))`;
  hex colors.
- Settings as a sidebar destination; the appearance control in the toolbar;
  renamed preference keys.
- A fixed window size; content remounted on sidebar toggle; a header that
  grows when the subtitle is missing.
- German or mixed-language strings in an English product.

## 15. Known gaps (AppKit side)

Listed so that nobody invents a rule or a component:

- No shared helper for `.searchable` placement; products wire it natively.
  Destination commands and the Settings scene use `SymairaCommands` and
  `SymairaSettingsScene` (SHELL-7, SHELL-9).
- No shared table styling or numeric-column helper; products use the native
  `Table` with `.monospacedDigit()`.
- The onboarding scaffold adoption is documented as a sketch, not as a
  verified consumer. The iOS shell has one verified consumer (Symaira
  Learning: `TabView`, `.symairaTopography(_:)`, `Image(symairaIcon:)`).
