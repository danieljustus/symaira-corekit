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

    // MARK: Adaptive semantic colors

    /// Warm Symaira canvas that follows the system appearance.
    public static func backgroundPrimary(for colorScheme: ColorScheme) -> Color {
        colorScheme == .dark ? bgDark : Color(hex: "F7F3EC")
    }

    public static func backgroundSecondary(for colorScheme: ColorScheme) -> Color {
        colorScheme == .dark ? bgDarker : Color(hex: "EEE7DC")
    }

    public static func surfaceOpaque(for colorScheme: ColorScheme) -> Color {
        colorScheme == .dark ? Color(hex: "171510") : Color(hex: "FFFCF7")
    }

    public static func foregroundPrimary(for colorScheme: ColorScheme) -> Color {
        colorScheme == .dark ? textPrimary : Color(hex: "211D17")
    }

    public static func foregroundSecondary(for colorScheme: ColorScheme) -> Color {
        colorScheme == .dark ? textSecondary : Color(hex: "5F584F")
    }

    public static func foregroundMuted(for colorScheme: ColorScheme) -> Color {
        colorScheme == .dark ? textMuted : Color(hex: "756D63")
    }

    // Motion
    public static let transitionSmooth = Animation.timingCurve(0.16, 1, 0.3, 1, duration: 0.4)
    public static let transitionFast = Animation.easeOut(duration: 0.2)
}

/// Shared spacing scale. Keeping layout values here prevents each client from
/// inventing subtly different cards and content rhythm.
public enum SymairaSpacing {
    public static let xSmall: CGFloat = 4
    public static let small: CGFloat = 8
    public static let medium: CGFloat = 12
    public static let large: CGFloat = 16
    public static let xLarge: CGFloat = 24
    public static let section: CGFloat = 32
    public static let spacious: CGFloat = 48
}

public enum SymairaRadius {
    public static let control: CGFloat = 10
    public static let card: CGFloat = 16
    public static let panel: CGFloat = 20
}

public enum SymairaMetrics {
    #if os(iOS)
    public static let minimumControlHeight: CGFloat = 44
    #else
    public static let minimumControlHeight: CGFloat = 34
    #endif

    public static let readableContentWidth: CGFloat = 760
    public static let glassGroupSpacing: CGFloat = 12

    /// Symbol size for the illustration above an empty state. Fixed on purpose —
    /// it is a graphic, not text, and must not scale with Dynamic Type.
    public static let emptyStateSymbolSize: CGFloat = 36
}

extension Color {
    /// Hex color initializer supporting 3-digit RGB, 6-digit RGB, and
    /// 8-digit ARGB, with or without a leading `#`.
    public init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
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
