# Symaira UI Foundation

`SymairaTheme` keeps the existing champagne-gold, warm-black Symaira identity
while following the interaction and material conventions of macOS and iOS.

## Product and distribution assets

[`Brand/README.md`](Brand/README.md) defines the shared app-icon shell,
user-facing naming convention, and Finder disk-image presentation. Generic
sources and deterministic renderers live in AppKit; each product owns only its
recognizable glyph and vendors the finished release assets so standalone
builds never depend on a sibling checkout.

## Material hierarchy

Use the smallest amount of glass needed to make the interface hierarchy clear:

1. **Canvas:** `SymairaBackdrop` provides the branded background, subtle grid,
   and ambient light. It adapts to light/dark appearance and Reduce Transparency.
2. **Content:** `glassCard` and `glassmorphicPanel` use standard Apple material.
   These are reading and data surfaces, not Liquid Glass controls.
3. **Chrome and controls:** `symairaButtonStyle`, `symairaGlassChrome`, and
   `SymairaGlassEffectContainer` use native Liquid Glass on macOS/iOS 26+.
4. **Feedback:** `SymairaBadge`, `SymairaNotice`, `SymairaEmptyState`, and
   `SymairaLoadingState` give all clients consistent semantic states.

This separation matters: Liquid Glass is the functional layer floating above
content. Repeating it on every card makes hierarchy and text legibility worse.

## Platform behavior

- Prefer `NavigationSplitView`, `TabView`, toolbars, sheets, and native controls.
  System components automatically track current Apple platform behavior.
- Use `symairaButtonStyle(.primary)` for the main action,
  `.secondary` for supporting actions, and `.toolbar` for compact toolbar items.
- Group nearby glass controls in one `SymairaGlassEffectContainer`; this improves
  rendering and enables system morphing between adjacent glass shapes.
- Keep touch controls at least 44 points high on iOS. The legacy Symaira button
  styles enforce the correct platform minimum automatically.
- Keep important content inside `SymairaMetrics.readableContentWidth` on wide
  Mac windows and let lists or grids adapt outside that reading column.

## Accessibility defaults

- Text and semantic colors adapt to light/dark appearance. The updated muted
  dark token clears 4.5:1 contrast on the canonical dark canvas.
- Reduce Transparency replaces materials with an opaque warm Symaira surface.
- Increase Contrast strengthens borders.
- Reduce Motion removes the scale animation from custom fallback buttons.
- Decorative grids, glows, and telemetry corners are hidden from accessibility
  and never intercept input.
- Empty, loading, and notice components expose useful combined labels; callers
  still need localized copy and meaningful button labels.

## Migration from app-local styles

Replace duplicated theme code only after the app updates its exact AppKit pin.
The intended mappings are:

| App-local pattern | Shared replacement |
| --- | --- |
| Blueprint/dot grid plus ambient gradients | `SymairaBackdrop` |
| Static translucent content background | `.glassCard()` |
| Large content panel | `.glassmorphicPanel()` |
| Custom prominent/secondary glass button | `.symairaButtonStyle(.primary/.secondary)` |
| Group of floating controls | `SymairaGlassEffectContainer` |
| Custom toolbar glass background | `.symairaGlassChrome(isInteractive: true)` |
| Status pill | `SymairaBadge` |
| Error/info banner | `SymairaNotice` |
| Empty or loading placeholder | `SymairaEmptyState` / `SymairaLoadingState` |

Legacy token aliases and button styles remain source-compatible so each client
can migrate deliberately after a tagged AppKit release.

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
