import SwiftUI

/// Canonical Symaira type scale.
///
/// Every entry is built with `Font.system(_:design:weight:)` so it stays tied to
/// a Dynamic Type text style — a fixed point size would freeze the layout for
/// users who scale text up. The scale is deliberately short: nine text roles and
/// two monospaced roles cover the clients we have, and a short scale is what
/// keeps them looking like one product.
public enum SymairaTypography {
    /// Hero copy on empty states and onboarding. One per screen at most.
    public static let display = Font.system(.largeTitle, design: .default, weight: .semibold)

    /// Primary screen title.
    public static let title = Font.system(.title, design: .default, weight: .semibold)

    /// Section or card heading.
    public static let heading = Font.system(.title3, design: .default, weight: .semibold)

    /// Sub-heading above a group of rows.
    public static let subheading = Font.system(.headline, design: .default, weight: .semibold)

    /// Default running text.
    public static let body = Font.system(.body, design: .default, weight: .regular)

    /// Running text that carries the weight of a decision (selected row, active value).
    public static let bodyEmphasized = Font.system(.body, design: .default, weight: .semibold)

    /// Running text on a secondary control — lighter than ``bodyEmphasized``,
    /// still heavier than ``body``.
    public static let bodyMedium = Font.system(.body, design: .default, weight: .medium)

    /// Badge and pill text.
    public static let label = Font.system(.caption, design: .default, weight: .semibold)

    /// Secondary text next to a control or inside a row.
    public static let callout = Font.system(.callout, design: .default, weight: .regular)

    /// Helper text, timestamps, counts.
    public static let caption = Font.system(.caption, design: .default, weight: .regular)

    /// Uppercase group labels and badges. The smallest role that still has to stay legible.
    public static let micro = Font.system(.caption2, design: .default, weight: .semibold)

    /// Command output, paths, hashes, identifiers.
    public static let mono = Font.system(.body, design: .monospaced, weight: .regular)

    /// Monospaced detail inside a dense row.
    public static let monoSmall = Font.system(.caption, design: .monospaced, weight: .regular)
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

    public var font: Font {
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

    /// Extra letter spacing. Only the uppercase section label needs it.
    public var tracking: CGFloat {
        self == .sectionLabel ? 0.6 : 0
    }
}

private struct SymairaTextRoleModifier: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme

    let role: SymairaTextRole
    let respectsForeground: Bool

    func body(content: Content) -> some View {
        let styled = content
            .font(role.font)
            .tracking(role.tracking)
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
