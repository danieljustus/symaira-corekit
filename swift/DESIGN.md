# Symaira UI Foundation

`SymairaTheme` is the shared design and interaction foundation for Symaira
products. The current direction is **Liquid Topography**: quiet gray surfaces,
Google Sans Flex for the largest headings over Figtree text, restrained champagne accents and native Apple chrome.

The canonical visual specification is
[`design/liquid-topography/DESIGN.md`](design/liquid-topography/DESIGN.md).
Its `topo.json` and token generator live beside it. This document routes native
consumers to that specification and the shipped APIs; it is not a second palette.

## Ownership of design rules

A reusable rule accepted in any Symaira product pilot belongs here, with its
implementation and regression check. Products consume it instead of copying
layout, colors, interaction geometry or shader lifecycle code. Future changes
start in AppKit and are checked in a real consumer before adoption elsewhere.

Product destinations, domain models, hardware actions, credentials, content
composition and preference identities stay in the product. In particular,
`Keep Awake` is Cockpit functionality; stable Start/End action geometry is a
shared rule. AppKit does not store application settings under a global key.

## Product and distribution assets

[`Brand/README.md`](Brand/README.md) defines the shared app-icon shell,
user-facing naming convention, and Finder disk-image presentation. Generic
sources and deterministic renderers live in AppKit; each product owns only its
recognizable glyph and vendors finished release assets so standalone builds
never depend on a sibling checkout.

## Material hierarchy

1. **Canvas:** `SymairaTopoView` on the adaptive canvas, or a plain canvas for
   dense lists/settings. Text and controls use `.topoProtected()` within the
   shared workspace. Protect each heading/description at its text bounds, before
   expanding frames or padding. Do not protect an entire header stack, spacer
   or divider row: short titles must not inherit a long subtitle's empty area.
   Content cards still protect their complete surface. Decoration must never
   compromise readability.
2. **Content:** opaque `.symairaCard()` surfaces, not glass behind reading/data.
3. **Chrome:** `SymairaWorkspace` shares one toolbar/sidebar background and one
   rounded inset content panel. `symairaGlassChrome`, toolbar buttons and
   `SymairaGlassEffectContainer` use native Liquid Glass on macOS/iOS 26+,
   with material/opaque fallbacks.
4. **Feedback:** `SymairaBadge`, `SymairaStatusLabel`, `SymairaNotice` and
   `SymairaEmptyState` retain shared semantic states; loading and progress are
   native `ProgressView`s.

## Platform behavior

- On macOS, use `SymairaWorkspace`, `SymairaSidebarState` and
  `SymairaSidebarToggle` for the approved rounded workspace. It supports native
  drag resizing, collapse to an icon rail, a resize cursor and keyboard/AX
  alternatives without recreating the content.
- Use `SymairaNavigationButton` for workspace destinations: it owns row geometry,
  label/icon modes, selection traits, hover/pressed styling and keyboard focus.
  Hosts supply meaningful labels, symbols, selection and actions. Use the lower-level
  `SymairaNavigationButtonStyle` only for genuinely custom rows.
- Use `.symairaButtonStyle(.primary)` for the one opaque Symaira action of a
  screen and `.secondary` for every other content action: native interactive
  Liquid Glass on macOS/iOS 26+, opaque `raised` under Reduce Transparency and
  on older systems. Both roles share font, horizontal padding and minimum
  height (36 pt capsule on macOS in the page tier, 44 pt iOS); switching roles must not shrink the action.
  A stateful label uses a stable full-width or explicitly reserved label area.
  A visible destructive action uses `.destructive` with `Button(role: .destructive)`:
  the primary's capsule in `critical` with an `on-critical` label (workbench:
  `borderedProminent` in the same colors), never `.tint(.red)` (GUIDELINES ACTION-4).
- `.toolbar` remains the compact, native glass button role. Glass buttons stay
  neutral; the selection tint belongs to segments and switches. Group adjacent
  glass controls in `SymairaGlassEffectContainer(spacing: 0)` rather than
  glassing every card. Page toolbar rows use `.controlSize(.extraLarge)`
  (GUIDELINES FORM-9). Sheet footers pair a secondary Cancel with a primary
  confirming verb (ACTION-5).
- Progress is a native `ProgressView(value:)`; sliders are native with
  `.tint(SymairaTokens.ink)`. `SymairaBarColors` stays for product-drawn
  meters: the empty track is a groove (`raised` fill, 1 pt `line` outline),
  the fill is `ink`. Warnings remain explicit text/icons.
- Dashboard summary values are `Gauge(value:)` with a `currentValueLabel` for
  bounded values and `LabeledContent` otherwise (`SymairaStatTile` is
  deprecated).
- `SymairaAppearance` and `SymairaAppearancePicker` (a native segmented picker
  with the Symaira selection tint) provide System/Light/Dark inside the settings
  form, alongside the other preferences, never in the gear.
  macOS `.apply()` affects existing/new native surfaces; System clears the
  override. iOS uses `.preferredColorScheme(selection.colorScheme)`.
- Workspace toolbars use one trailing `SymairaSettingsButton`: clicking the
  native gear opens the settings window directly, without any intermediate menu.
  SwiftUI hosts use `Settings { }` and `openSettings`; native AppKit hosts open
  their existing preferences window. Repeated clicks reuse that window. Do not
  duplicate settings in the sidebar or replace the current workspace destination.
- Mount `SymairaWorkspaceToolbar` and apply `.symairaWorkspaceWindow()` to the
  scene so placement and native title-bar mode cannot drift between consumers.
  Keep content fonts scoped to content, not the enclosing toolbar. Form sections
  and notices are opaque reading surfaces; only navigation chrome uses glass.
- Use native `NavigationSplitView`, `TabView`, toolbars, sheets and touch targets
  where appropriate to the platform. The drag-resizable workspace is macOS-only;
  do not impose a desktop column on phone layouts.
- Keep running text within `SymairaMetrics.proseMeasure` (about 71 to 73
  characters); `SymairaMetrics.readableContentWidth` is the page column for cards,
  forms and lists, and grids and dashboards may choose a wider product-owned budget.
- Type roles carry the token line heights for wrapped text (body 1.5), and on iOS
  they are `SymairaMetrics.textScale` larger so body text is 17 pt at the default
  Dynamic Type size (GUIDELINES TYPE-5, IOS-7).

- On tvOS, use the focus engine and a native top tab bar rather than pointer
  hover or the macOS workspace. Keep topography off dense content. Keyboard
  shortcuts and hover effects are unavailable; focus feedback belongs to the
  native controls. Liquid Glass falls back on tvOS before version 26.
- The tvOS home screen mounts the topography with `.symairaTopography(_:)`.
  The field is drawn at `SymairaMetrics.platformScale` (terrain, lines and
  ripples twice their point size) and follows the focus engine instead of a
  pointer: the focused item bends the lines, each focus move sends a ripple
  (GUIDELINES TV-1 to TV-3).

## Accessibility defaults

- Adaptive text/status colors retain the canonical contrast checks.
- Control boundaries use `control-outline` (at least 3:1 against `raised`,
  `surface` and `canvas`, WCAG 1.4.11); `line` stays the quiet stroke of cards,
  dividers and tables.
- Reduce Transparency replaces chrome with an opaque sidebar surface.
- Increase Contrast strengthens outlines; focus must not rely on color alone.
- Reduce Motion disables decorative movement and button scale animations.
- Topography protection updates after layout changes even when animation is
  paused. macOS window visibility, not an AppKit host's default scene phase,
  controls pausing; ripple ages are nonnegative.
- Decorative backgrounds are hidden from accessibility and never intercept input.
- Hosts still supply meaningful localized labels, selection traits, error text
  and keyboard focus. Native tests do not substitute for VoiceOver acceptance.

## Native controls (UI catalog 2026-11-25)

Daniel chose one variant per element in the UI catalog
([`design/ui-catalog/ui-catalog.md`](design/ui-catalog/ui-catalog.md), screenshots via
`design/ui-catalog/board.py`). On Apple platforms 23 of 33 elements are native controls or native glass,
3 of them with the Symaira selection tint (`.tint(SymairaTokens.selected)`, sliders
`.tint(SymairaTokens.ink)`) and 3 with Liquid Glass (secondary buttons, revised
2026-11-26 in the Soundworks pilot; icon buttons; toolbar groups). Symaira keeps its own primary
button, text fields outside forms, cards, notices, empty states, badge, status label and
the workspace shell. On the web, native HTML elements carry the
Symaira base (Figtree, token colours, `accent-color`); buttons, menus, sliders, notices, empty
states, sheets and disclosures use the full Symaira styling. The replaced Swift components are
deprecated, not removed (GUIDELINES NATIVE-1).

## Migration from app-local styles

See [shared workspace usage and ownership](docs/workspace-foundation.md) for
API examples, the approved rule inventory and consumer migration boundaries.
Update the app's exact AppKit pin only after a tagged release. Local editable
SPM dependencies are development state, not a published fleet upgrade.

| App-local pattern | Shared replacement |
| --- | --- |
| Rounded workspace, chrome and resizable sidebar | `SymairaWorkspace` + `SymairaSidebarState` |
| Sidebar toggle/shortcut | `SymairaSidebarToggle` |
| Toolbar placement and native title-bar mode | `SymairaWorkspaceToolbar`, `.symairaWorkspaceWindow()` |
| Navigation row geometry, labels and focus | `SymairaNavigationButton` |
| Navigation hover/selection palette | `SymairaNavigationButtonStyle` |
| Text-protection environment wrapper | `.topoProtected()` in a shared workspace |
| Stateful prominent/secondary button | `.symairaButtonStyle(.primary)` (opaque) / `.secondary` (native glass) |
| Red destructive button (`.tint(.red)`) | `.symairaButtonStyle(.destructive)` with `Button(role: .destructive)` |
| Hand-set `.lineSpacing` on role text | Nothing: `.font(role)` and `.symairaText(_:)` apply the token line height |
| Product-drawn meter palette | `SymairaBarColors` (progress itself: native `ProgressView(value:)`) |
| Dashboard summary value | `Gauge(value:)` or `LabeledContent` (`SymairaStatTile` deprecated) |
| Direct settings-window action | `SymairaSettingsButton` |
| Appearance mapping/control inside settings | `SymairaAppearance` + `SymairaAppearancePicker` |
| Text-bearing content card | `.symairaCard()` |
| Settings and forms | Native `Form { Section }.formStyle(.grouped)`; `SymairaFormRow`/`SymairaFormDivider` only for list rows in a card |
| Control tiers | Navigation (shell), page (`SymairaPage` toolbar, sheet footer: 36 pt capsules, glass) and workbench (content, form rows: native solid `.large`, 28 pt), GUIDELINES CTRL-1 |
| Segments, switches, menus | `SymairaSegmentedControl` (native segmented, tinted, size of its tier), `Toggle(.switch)` with `.tint(SymairaTokens.selected)`, `Picker(.menu)` |
| Group of floating controls | `SymairaGlassEffectContainer` |
| Custom toolbar glass background | `.symairaGlassChrome(isInteractive: true)` |
| Status pill, error/info banner | `SymairaBadge`, `SymairaNotice` |
| Empty/loading placeholder | `SymairaEmptyState`, native `ProgressView("…")` |

Legacy `SymairaBackdrop`, `BlueprintGrid`, `AmbientGlows`, `.glassCard()`,
`.glassmorphicPanel()` and fixed `Color.symaira*` aliases remain source-compatible.
They are compatibility APIs, not the current visual direction. Existing consumers
migrate deliberately; this source update does not re-theme already released apps.

`SymairaSettingsMenu` retains its old initializer for source compatibility but
now delegates directly to the settings button. Consumers must add the shared
appearance picker to their settings window before adopting this behavior change.

## Icons

Use `SymairaIcon` instead of raw SF Symbol strings. It has one semantic case per
meaning, such as `.delete`, `.refresh` or `.productVault`. The glyphs are drawn
in-house: rounded, with a 2 pt stroke, and licensed for every platform. Hovering
over an icon moves its parts into a small preview pose, and clicking plays a
motion that matches its meaning. For example, the trash lid lifts, the bell
rings, the check mark draws itself and the vault dial turns. When Reduce Motion
is on, the icons are drawn static. To add or change an icon, edit
[`Brand/Icons/icons.svg`](Brand/Icons/README.md) and regenerate. Never add icons
inside an app.
