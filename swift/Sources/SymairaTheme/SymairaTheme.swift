import SwiftUI

/// Canonical Symaira design tokens (champagne gold, warm neutrals, and glass).
///
/// Color values are taken 1:1 from the most mature donor (symaira-print);
/// member names match the former per-app `Theme` enums so migration is a
/// search-and-replace. The `Color.symaira*` statics below cover the second
/// legacy API style (seek/memory).
public enum SymairaTheme {
    // Backgrounds
    public static let bgDark = Color(hex: "0D0C0A")
    public static let bgDarker = Color(hex: "070605")
    public static let bgCard = Color(hex: "12110E").opacity(0.65)
    public static let bgCardHover = Color(hex: "1A1814").opacity(0.8)

    // Brand golds
    public static let goldPrimary = Color(hex: "E5C397")
    public static let goldSecondary = Color(hex: "F8E6CD")
    public static let goldShadow = Color(hex: "C29965")

    // Ice / sand accents
    public static let icePrimary = Color(hex: "EEDCC4")
    public static let iceSecondary = Color(hex: "D4B285")

    // Text
    public static let textPrimary = Color(hex: "F5F4F0")
    public static let textSecondary = Color(hex: "B5AEA5")
    /// Muted text that still clears a 4.5:1 contrast ratio on `bgDark`.
    public static let textMuted = Color(hex: "837D74")

    // Glass borders
    public static let borderGlass = Color.white.opacity(0.06)
    public static let borderGlassHover = Color(hex: "E5C397").opacity(0.22)

    // Ambient glows
    public static let glowSoft = goldPrimary.opacity(0.04)
    public static let glowIntense = goldPrimary.opacity(0.12)

    // Semantic feedback
    public static let positive = Color(hex: "7FD49A")
    public static let warning = Color(hex: "E9BC73")
    public static let critical = Color(hex: "FF8A80")
    public static let informative = Color(hex: "8CC8F2")

    // MARK: Adaptive semantic colors (Liquid Topography)
    //
    // Fixed per-appearance values of the Liquid Topography roles, read from the
    // generated `SymairaTokens.Palette` so a palette change in DESIGN.md reaches
    // these helpers through `build.py` alone. The fixed brand constants above
    // stay as legacy API for clients that have not migrated yet; new code uses
    // only these adaptive roles.

    /// Page canvas. Liquid Topography `canvas`.
    public static func backgroundPrimary(for colorScheme: ColorScheme) -> Color {
        SymairaTokens.Palette.canvas.color(for: colorScheme)
    }

    /// Sidebar. Liquid Topography `sidebar`.
    public static func backgroundSecondary(for colorScheme: ColorScheme) -> Color {
        SymairaTokens.Palette.sidebar.color(for: colorScheme)
    }

    /// Cards and panels. Liquid Topography `surface`.
    public static func surfaceOpaque(for colorScheme: ColorScheme) -> Color {
        SymairaTokens.Palette.surface.color(for: colorScheme)
    }

    /// Segment rails, secondary buttons, hover. Liquid Topography `raised`.
    public static func surfaceRaised(for colorScheme: ColorScheme) -> Color {
        SymairaTokens.Palette.raised.color(for: colorScheme)
    }

    /// Outline of opaque controls (text fields, the secondary button without glass) in both
    /// appearances: Liquid Topography `control-outline`, at least 3:1 against `raised`,
    /// `surface` and `canvas` (WCAG 1.4.11). Light `raised` equals `canvas`, so such a
    /// control would otherwise vanish on the canvas.
    public static func raisedOutline(for colorScheme: ColorScheme) -> Color {
        controlOutline(for: colorScheme)
    }

    /// Boundary of an interactive control. Liquid Topography `control-outline` (COLOR-4).
    public static func controlOutline(for colorScheme: ColorScheme) -> Color {
        SymairaTokens.Palette.controlOutline.color(for: colorScheme)
    }

    /// 1 px separators and card outlines. Liquid Topography `line`: decorative, below 3:1 on
    /// purpose; control boundaries use ``controlOutline(for:)``.
    public static func line(for colorScheme: ColorScheme) -> Color {
        SymairaTokens.Palette.line.color(for: colorScheme)
    }

    /// Selected navigation row. Liquid Topography `selection`. Pair it with bold text:
    /// the fill alone is below 3:1 and is not a state cue.
    public static func navigationSelection(for colorScheme: ColorScheme) -> Color {
        SymairaTokens.Palette.selection.color(for: colorScheme)
    }

    public static func foregroundPrimary(for colorScheme: ColorScheme) -> Color {
        SymairaTokens.Palette.ink.color(for: colorScheme)
    }

    public static func foregroundSecondary(for colorScheme: ColorScheme) -> Color {
        SymairaTokens.Palette.ink2.color(for: colorScheme)
    }

    public static func foregroundMuted(for colorScheme: ColorScheme) -> Color {
        SymairaTokens.Palette.ink3.color(for: colorScheme)
    }

    /// Champagne brand accent, identical in both appearances. Never a state cue on
    /// light surfaces (about 1.2:1); use ``selected(for:)`` for selection.
    public static func accent(for colorScheme: ColorScheme) -> Color {
        SymairaTokens.Palette.primary.color(for: colorScheme)
    }

    /// Selected state: segments, switch on, checkmarks, slider thumbs.
    /// Dark: champagne. Light: ink (design decision A, 15.7:1 against the rail).
    public static func selected(for colorScheme: ColorScheme) -> Color {
        SymairaTokens.Palette.selected.color(for: colorScheme)
    }

    /// Text and glyphs on ``selected(for:)``.
    public static func onSelected(for colorScheme: ColorScheme) -> Color {
        SymairaTokens.Palette.onSelected.color(for: colorScheme)
    }

    /// 2 px keyboard focus ring.
    public static func focus(for colorScheme: ColorScheme) -> Color {
        SymairaTokens.Palette.focus.color(for: colorScheme)
    }

    // Motion
    public static let transitionSmooth = Animation.timingCurve(0.16, 1, 0.3, 1, duration: 0.4)
    public static let transitionFast = Animation.easeOut(duration: 0.2)

    /// Quick response to a pressed control: 0.25 s duration, 0.45 bounce.
    public static let springPress = Animation.spring(duration: 0.25, bounce: 0.45)

    /// One-shot reveal of a verdict or milestone: 0.5 s duration, 0.5 bounce.
    public static let springPop = Animation.spring(duration: 0.5, bounce: 0.5)

    /// Gentle fill of a progress indicator: 0.9 s duration, 0.15 bounce.
    public static let springFill = Animation.spring(duration: 0.9, bounce: 0.15)
}

/// Shared spacing scale. Keeping layout values here prevents each client from
/// inventing subtly different cards and content rhythm.
/// Spacing, radii, metrics and the bundled font sizes are multiplied by
/// `SymairaMetrics.platformScale`, so one layout reads at desk distance and from the couch.
public enum SymairaSpacing {
    public static let xSmall: CGFloat = 4 * SymairaMetrics.platformScale
    public static let small: CGFloat = 8 * SymairaMetrics.platformScale
    public static let medium: CGFloat = 12 * SymairaMetrics.platformScale
    public static let large: CGFloat = 16 * SymairaMetrics.platformScale
    public static let xLarge: CGFloat = 24 * SymairaMetrics.platformScale
    public static let section: CGFloat = 32 * SymairaMetrics.platformScale
    public static let spacious: CGFloat = 48 * SymairaMetrics.platformScale
}

/// Radii of the token scale (`SymairaTokens.Radius`), multiplied by `SymairaMetrics.platformScale`.
public enum SymairaRadius {
    /// Fields, rows, notices, sidebar entries: `rounded.md`.
    public static let control: CGFloat = SymairaTokens.Radius.md * SymairaMetrics.platformScale
    /// Content cards: `rounded.lg`.
    public static let card: CGFloat = SymairaTokens.Radius.lg * SymairaMetrics.platformScale
    /// The workspace's main panel: `rounded.xl`.
    public static let panel: CGFloat = SymairaTokens.Radius.xl * SymairaMetrics.platformScale
}

public enum SymairaMetrics {
    /// Factor from the Symaira scale to this platform. The scale is set for desk and hand
    /// distance; an Apple TV is read from the couch, so every size doubles there: body text is
    /// 27 pt on the 1920 pt wide screen, close to the 29 pt of tvOS body text, and a layout
    /// looks like a 960 pt wide window at twice the size.
    #if os(tvOS)
    public static let platformScale: CGFloat = 2
    #else
    public static let platformScale: CGFloat = 1
    #endif

    /// Factor from the Symaira type scale to this platform's text sizes. The roles are set
    /// for desk distance (body 13.5 pt on macOS). iOS is read at hand distance, so every role
    /// grows by 15 / 13.5 there before Dynamic Type scales it: body 15 pt at the default size
    /// (GUIDELINES IOS-7). Apple's 17 pt read as oversized in dense Symaira screens (#523).
    /// tvOS follows `platformScale` like every other size.
    #if os(iOS)
    public static let textScale: CGFloat = 15 / 13.5
    #else
    public static let textScale: CGFloat = platformScale
    #endif

    #if os(iOS)
    public static let minimumControlHeight: CGFloat = 44
    #else
    public static let minimumControlHeight: CGFloat = 34 * platformScale
    #endif

    /// Page actions share geometry, including when an action changes state: the 36 pt capsule
    /// of the extra-large native controls beside them (CTRL-1), the touch minimum on iOS.
    public static let contentActionHeight: CGFloat = max(minimumControlHeight, 36 * platformScale)
    public static let contentActionHorizontalPadding: CGFloat = 20 * platformScale

    /// Default width of a `SymairaPage` column, which carries cards, forms and lists. Running
    /// text inside it keeps to ``proseMeasure``.
    public static let readableContentWidth: CGFloat = 760 * platformScale
    /// Measure of running text (LAYOUT-2): about 71 to 73 characters of 13.5 pt Figtree, inside
    /// the 45 to 75 characters the type literature recommends. A full page column would hold
    /// about 115.
    public static let proseMeasure: CGFloat = 440 * platformScale
    public static let glassGroupSpacing: CGFloat = 12 * platformScale
    /// One height for every segmented control, the 36 pt of the extra-large native controls.
    public static let segmentedControlHeight: CGFloat = 36 * platformScale
    /// Height of the `workbench` control tier (CTRL-1): the native `.large` controls on macOS,
    /// the touch minimum on iOS.
    #if os(iOS)
    public static let workbenchControlHeight: CGFloat = minimumControlHeight
    #else
    public static let workbenchControlHeight: CGFloat = 28 * platformScale
    #endif

    /// Symbol size for the illustration above an empty state. Fixed on purpose —
    /// it is a graphic, not text, and must not scale with Dynamic Type.
    public static let emptyStateSymbolSize: CGFloat = 36 * platformScale
}

extension Color {
    /// Hex color initializer supporting 3-digit RGB, 6-digit RGB, and
    /// 8-digit ARGB, with or without a leading `#`.
    public init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a: UInt64
        let r: UInt64
        let g: UInt64
        let b: UInt64
        switch hex.count {
        case 3:  // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6:  // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8:  // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }

    // Compatibility surface for the seek/memory naming style.
    public static let symairaBg = SymairaTheme.bgDark
    public static let symairaBgDarker = SymairaTheme.bgDarker
    public static let symairaGold = SymairaTheme.goldPrimary
    public static let symairaGoldSecondary = SymairaTheme.goldSecondary
    public static let symairaGoldShadow = SymairaTheme.goldShadow
    public static let symairaText = SymairaTheme.textPrimary
    public static let symairaTextSecondary = SymairaTheme.textSecondary
    public static let symairaMuted = SymairaTheme.textMuted
    public static let symairaCard = SymairaTheme.bgCard
    public static let symairaCardHover = SymairaTheme.bgCardHover
}
