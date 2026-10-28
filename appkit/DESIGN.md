# Symaira UI Foundation

`SymairaTheme` is the shared design and interaction foundation for Symaira
products. The current direction is **Liquid Topography**: quiet gray surfaces,
Google Sans Flex headings over Inter text, restrained champagne accents and native Apple chrome.

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
4. **Feedback:** `SymairaBadge`, `SymairaNotice`, `SymairaEmptyState` and
   `SymairaLoadingState` retain shared semantic states.

## Platform behavior

- On macOS, use `SymairaWorkspace`, `SymairaSidebarState` and
  `SymairaSidebarToggle` for the approved rounded workspace. It supports native
  drag resizing, collapse to an icon rail, a resize cursor and keyboard/AX
  alternatives without recreating the content.
- Use `SymairaNavigationButton` for workspace destinations: it owns row geometry,
  label/icon modes, selection traits, hover/pressed styling and keyboard focus.
  Hosts supply meaningful labels, symbols, selection and actions. Use the lower-level
  `SymairaNavigationButtonStyle` only for genuinely custom rows.
- Use `.symairaButtonStyle(.primary/.secondary)` for opaque content actions.
  Both roles share font, horizontal padding and minimum height (40 pt macOS,
  44 pt iOS); switching roles must not shrink the action. A stateful label uses
  a stable full-width or explicitly reserved label area.
- `.toolbar` remains the compact, native glass button role. Group adjacent glass
  controls in `SymairaGlassEffectContainer` rather than glassing every card.
- `SymairaBarColors` and `SymairaProgressStyle` share neutral meter/slider colors.
  Warnings remain explicit text/icons, not an unrelated meter palette.
- `SymairaAppearance` and `SymairaAppearancePicker` provide System/Light/Dark
  inside the settings form, alongside the other preferences, never in the gear.
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
- Keep prose within `SymairaMetrics.readableContentWidth`; grids and dashboards
  may choose a wider product-owned content budget.

## Accessibility defaults

- Adaptive text/status colors retain the canonical contrast checks.
- Reduce Transparency replaces chrome with an opaque sidebar surface.
- Increase Contrast strengthens outlines; focus must not rely on color alone.
- Reduce Motion disables decorative movement and button scale animations.
- Topography protection updates after layout changes even when animation is
  paused. macOS window visibility, not an AppKit host's default scene phase,
  controls pausing; ripple ages are nonnegative.
- Decorative backgrounds are hidden from accessibility and never intercept input.
- Hosts still supply meaningful localized labels, selection traits, error text
  and keyboard focus. Native tests do not substitute for VoiceOver acceptance.

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
| Stateful prominent/secondary button | `.symairaButtonStyle(.primary/.secondary)` |
| Native slider and meter palette | `SymairaBarColors` + `SymairaProgressStyle` |
| Direct settings-window action | `SymairaSettingsButton` |
| Appearance mapping/control inside settings | `SymairaAppearance` + `SymairaAppearancePicker` |
| Text-bearing content card | `.symairaCard()` |
| Settings/form sections, rows, fields and dividers | `SymairaFormSection`, `SymairaFormRow`, `.symaira`, `SymairaFormDivider` |
| Group of floating controls | `SymairaGlassEffectContainer` |
| Custom toolbar glass background | `.symairaGlassChrome(isInteractive: true)` |
| Status pill, error/info banner | `SymairaBadge`, `SymairaNotice` |
| Empty/loading placeholder | `SymairaEmptyState`, `SymairaLoadingState` |

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
