import SwiftUI

/// Canonical Symaira type scale (see ``SymairaFont``).
///
/// Only the largest headings, the page title (`display`) and other screen titles
/// (`title`), are set in Google Sans Flex with the fixed optical size `opsz` 18. Every
/// other role (headings, metrics, running text, labels and captions) is set in Figtree.
/// Names, sizes, weights and line heights follow the `typography` roles of
/// `design/liquid-topography/DESIGN.md` (kebab-case there). Wrapped text keeps the
/// role's line height; single lines keep the typeface's own. On iOS every role is
/// `SymairaMetrics.textScale` (15 / 13.5) larger and scales with Dynamic Type relative to
/// its text style; macOS has no Dynamic Type. If a bundled font cannot be registered, the
/// system font with the same size and weight is used. Monospaced roles stay on SF Mono.
/// Values are `SymairaFontRole` recipes; `.font(role)` resolves them in the view.
public enum SymairaTypography {
    /// Page title of `SymairaPage` (LAYOUT-1) and hero copy on empty states. One per screen.
    /// Google Sans Flex 26 / 700, line height 1.2.
    public static let display = SymairaFont.font(size: 26, weight: 700, relativeTo: .largeTitle).lineHeight(1.2)

    /// Screen title where no `SymairaPage` header exists (onboarding steps, sheets).
    /// Google Sans Flex 20 / 700, line height 1.25.
    public static let title = SymairaFont.font(size: 20, weight: 700, relativeTo: .title).lineHeight(1.25)

    /// Section or card heading. Figtree 16 / 700, line height 1.3.
    public static let heading = SymairaFont.font(size: 16, weight: 700, relativeTo: .title3, family: .text)
        .lineHeight(1.3)

    /// Sub-heading above a group of rows. Figtree 14 / 650, line height 1.35.
    public static let subheading = SymairaFont.font(size: 14, weight: 650, relativeTo: .headline, family: .text)
        .lineHeight(1.35)

    /// Default running text. Figtree 13.5 / 450, line height 1.5.
    public static let body = SymairaFont.font(size: 13.5, weight: 450, relativeTo: .body, family: .text)
        .lineHeight(1.5)

    /// Running text that carries the weight of a decision (selected row, active value). Figtree 13.5 / 600.
    public static let bodyEmphasized = SymairaFont.font(size: 13.5, weight: 600, relativeTo: .body, family: .text)
        .lineHeight(1.5)

    /// Running text on a secondary control. Figtree 13.5 / 550.
    public static let bodyMedium = SymairaFont.font(size: 13.5, weight: 550, relativeTo: .body, family: .text)
        .lineHeight(1.5)

    /// Badge, pill, button and control label text. Figtree 12.5 / 550, line height 1.4.
    public static let label = SymairaFont.font(size: 12.5, weight: 550, relativeTo: .caption, family: .text)
        .lineHeight(1.4)

    /// Secondary text next to a control or inside a row. Figtree 12.5 / 450, line height 1.5.
    public static let callout = SymairaFont.font(size: 12.5, weight: 450, relativeTo: .callout, family: .text)
        .lineHeight(1.5)

    /// Helper text, timestamps, counts, scale labels. Figtree 11.5 / 450, line height 1.4.
    public static let caption = SymairaFont.font(size: 11.5, weight: 450, relativeTo: .caption, family: .text)
        .lineHeight(1.4)

    /// Uppercase group labels. The smallest role that still has to stay legible. Figtree 11.5 / 600.
    public static let micro = SymairaFont.font(size: 11.5, weight: 600, relativeTo: .caption2, family: .text)
        .lineHeight(1.4)

    /// Live value next to a control (brightness, fan speed). Figtree 18 / 700, tabular digits.
    public static let readout = SymairaFont.font(size: 18, weight: 700, relativeTo: .title3, family: .text)
        .lineHeight(1.3).monospacedDigit()

    /// Summary metric in a stat card. Figtree 27 / 700, tabular digits.
    public static let stat = SymairaFont.font(size: 27, weight: 700, relativeTo: .largeTitle, family: .text)
        .lineHeight(1.2).monospacedDigit()

    /// Command output, paths, hashes, identifiers.
    public static let mono = SymairaFontRole(source: .system(.system(.body, design: .monospaced, weight: .regular)))

    /// Monospaced detail inside a dense row.
    public static let monoSmall = SymairaFontRole(
        source: .system(.system(.caption, design: .monospaced, weight: .regular)))
}

/// A text role pairs a font with the foreground colour it is meant to carry.
///
/// Font and colour drift apart when each client picks them separately — one app
/// ends up with muted headings, another with full-contrast captions. Applying
/// them together through ``SwiftUI/View/symairaText(_:)`` keeps that from
/// happening.
public enum SymairaTextRole: Sendable {
    case display
    case title
    case heading
    case subheading
    case body
    case bodyEmphasized
    case callout
    /// Secondary running text — same size as ``callout``, lower contrast.
    case secondary
    case caption
    /// Uppercase group label. Applies tracking; the caller supplies the casing.
    case sectionLabel
    case mono
    case monoSmall

    public var font: SymairaFontRole {
        switch self {
        case .display: SymairaTypography.display
        case .title: SymairaTypography.title
        case .heading: SymairaTypography.heading
        case .subheading: SymairaTypography.subheading
        case .body: SymairaTypography.body
        case .bodyEmphasized: SymairaTypography.bodyEmphasized
        case .callout, .secondary: SymairaTypography.callout
        case .caption: SymairaTypography.caption
        case .sectionLabel: SymairaTypography.micro
        case .mono: SymairaTypography.mono
        case .monoSmall: SymairaTypography.monoSmall
        }
    }

    /// Foreground colour for this role in the given appearance.
    public func foreground(for colorScheme: ColorScheme) -> Color {
        switch self {
        case .display, .title, .heading, .subheading, .body, .bodyEmphasized, .mono:
            SymairaTheme.foregroundPrimary(for: colorScheme)
        case .callout:
            SymairaTheme.foregroundPrimary(for: colorScheme)
        case .secondary, .monoSmall:
            SymairaTheme.foregroundSecondary(for: colorScheme)
        case .caption, .sectionLabel:
            SymairaTheme.foregroundMuted(for: colorScheme)
        }
    }

    /// Letter spacing in points in light appearance. Large roles are tightened
    /// as specified in DESIGN.md; only the uppercase section label is opened up.
    public var tracking: CGFloat {
        switch self {
        case .display: -0.65  // -0.025em at 26 pt
        case .title: -0.3  // -0.015em at 20 pt
        case .heading: -0.16  // -0.01em at 16 pt
        case .sectionLabel: 0.6
        default: 0
        }
    }

    /// Letter spacing in points for the given appearance. Small gray text
    /// (``secondary`` and ``caption``) opens by +0.01em in dark appearance,
    /// where light-on-dark glyphs otherwise run together.
    public func tracking(for colorScheme: ColorScheme) -> CGFloat {
        guard colorScheme == .dark else { return tracking }
        switch self {
        case .secondary: return 0.125  // +0.01em at 12.5 pt
        case .caption: return 0.115  // +0.01em at 11.5 pt
        default: return tracking
        }
    }
}

private struct SymairaTextRoleModifier: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme

    let role: SymairaTextRole
    let respectsForeground: Bool

    func body(content: Content) -> some View {
        let styled =
            content
            .font(role.font)
            .tracking(role.tracking(for: colorScheme))
        if respectsForeground {
            styled.foregroundStyle(role.foreground(for: colorScheme))
        } else {
            styled
        }
    }
}

extension View {
    /// Applies the font, tracking, and foreground colour of a Symaira text role.
    ///
    /// Pass `respectsForeground: false` when the surrounding container already
    /// sets a colour that must win — a badge on a tinted background, for example.
    public func symairaText(
        _ role: SymairaTextRole,
        respectsForeground: Bool = true
    ) -> some View {
        modifier(SymairaTextRoleModifier(role: role, respectsForeground: respectsForeground))
    }
}
