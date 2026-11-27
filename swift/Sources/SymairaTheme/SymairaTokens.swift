// generiert von build.py aus DESIGN.md – nicht von Hand bearbeiten
import SwiftUI

#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif

public enum SymairaTokens {
    /// Hell- und Dunkelwert einer Farbrolle (sRGB, 0xRRGGBB), 1:1 aus DESIGN.md.
    public struct Pair: Hashable, Sendable {
        public let light: Int
        public let dark: Int

        init(_ light: Int, _ dark: Int) {
            self.light = light
            self.dark = dark
        }

        /// Der feste Wert dieser Rolle in einer Darstellung.
        public func color(for colorScheme: ColorScheme) -> Color {
            let c = Self.components(colorScheme == .dark ? dark : light)
            return Color(.sRGB, red: c.red, green: c.green, blue: c.blue, opacity: 1)
        }

        /// Folgt der Darstellung des Fensters, in dem die Farbe gezeichnet wird.
        var adaptive: Color {
            let (l, d) = (Self.components(light), Self.components(dark))
            #if canImport(AppKit)
            return Color(
                nsColor: NSColor(name: nil) { a in
                    let c = a.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? d : l
                    return NSColor(srgbRed: c.red, green: c.green, blue: c.blue, alpha: 1)
                })
            #else
            return Color(
                uiColor: UIColor { t in
                    let c = t.userInterfaceStyle == .dark ? d : l
                    return UIColor(red: c.red, green: c.green, blue: c.blue, alpha: 1)
                })
            #endif
        }

        static func components(_ hex: Int) -> (red: Double, green: Double, blue: Double) {
            (Double((hex >> 16) & 0xFF) / 255, Double((hex >> 8) & 0xFF) / 255, Double(hex & 0xFF) / 255)
        }
    }

    /// Alle Farbrollen als Hell/Dunkel-Paare; die adaptiven Farben unten und
    /// `SymairaTheme.*(for:)` lesen ausschließlich hier.
    public enum Palette {
        public static let primary = Pair(0xE0D2BA, 0xE0D2BA)
        public static let onPrimary = Pair(0x1A1814, 0x1A1814)
        public static let primarySoft = Pair(0xE2DED5, 0x312F2B)
        public static let selected = Pair(0x141413, 0xE0D2BA)
        public static let onSelected = Pair(0xE1E0DA, 0x1A1814)
        public static let focus = Pair(0x141413, 0xE0D2BA)
        public static let canvas = Pair(0xEEEDEA, 0x1C1C1B)
        public static let sidebar = Pair(0xE1E0DA, 0x171716)
        public static let surface = Pair(0xE1E0DA, 0x141413)
        public static let raised = Pair(0xEEEDEA, 0x2B2B2A)
        public static let selection = Pair(0xB0AEA9, 0x2D2D2C)
        public static let line = Pair(0xB0AEA9, 0x30302E)
        public static let controlOutline = Pair(0x827F78, 0x74746F)
        public static let ink = Pair(0x141413, 0xEEEDEA)
        public static let ink2 = Pair(0x2B2B2A, 0xB0AEA9)
        public static let ink3 = Pair(0x62615D, 0x97958F)
        public static let positive = Pair(0x34694A, 0x93C49F)
        public static let warning = Pair(0x7E5310, 0xE9BC73)
        public static let critical = Pair(0x9A4634, 0xE39C8A)
        public static let onCritical = Pair(0xE1E0DA, 0x141413)
        public static let criticalSoft = Pair(0xF2DED8, 0x3A2925)
        public static let topo = Pair(0x2B2B2A, 0xE1E0DA)

        /// Rollenname aus DESIGN.md -> Paar; Tests gleichen damit gegen die Quelle ab.
        static let byName: [String: Pair] = [
            "primary": primary,
            "on-primary": onPrimary,
            "primary-soft": primarySoft,
            "selected": selected,
            "on-selected": onSelected,
            "focus": focus,
            "canvas": canvas,
            "sidebar": sidebar,
            "surface": surface,
            "raised": raised,
            "selection": selection,
            "line": line,
            "control-outline": controlOutline,
            "ink": ink,
            "ink-2": ink2,
            "ink-3": ink3,
            "positive": positive,
            "warning": warning,
            "critical": critical,
            "on-critical": onCritical,
            "critical-soft": criticalSoft,
            "topo": topo,
        ]
    }

    public static let primary = Palette.primary.adaptive
    public static let onPrimary = Palette.onPrimary.adaptive
    public static let primarySoft = Palette.primarySoft.adaptive
    public static let selected = Palette.selected.adaptive
    public static let onSelected = Palette.onSelected.adaptive
    public static let focus = Palette.focus.adaptive
    public static let canvas = Palette.canvas.adaptive
    public static let sidebar = Palette.sidebar.adaptive
    public static let surface = Palette.surface.adaptive
    public static let raised = Palette.raised.adaptive
    public static let selection = Palette.selection.adaptive
    public static let line = Palette.line.adaptive
    public static let controlOutline = Palette.controlOutline.adaptive
    public static let ink = Palette.ink.adaptive
    public static let ink2 = Palette.ink2.adaptive
    public static let ink3 = Palette.ink3.adaptive
    public static let positive = Palette.positive.adaptive
    public static let warning = Palette.warning.adaptive
    public static let critical = Palette.critical.adaptive
    public static let onCritical = Palette.onCritical.adaptive
    public static let criticalSoft = Palette.criticalSoft.adaptive
    public static let topo = Palette.topo.adaptive

    public enum Radius {
        public static let sm: CGFloat = 6.0
        public static let md: CGFloat = 10.0
        public static let lg: CGFloat = 14.0
        public static let xl: CGFloat = 20.0
        public static let pill: CGFloat = 999.0
    }
    public enum Space {
        public static let xs: CGFloat = 4.0
        public static let sm: CGFloat = 8.0
        public static let md: CGFloat = 12.0
        public static let lg: CGFloat = 16.0
        public static let xl: CGFloat = 24.0
        public static let xxl: CGFloat = 32.0
    }
    public static let iconWeight: Font.Weight = .semibold

    /// Parameter der Hochebene, 1:1 aus topo.json
    public enum Topo {
        public static let levels: Double = 16.0
        public static let scale: Double = 340.0
        public static let lineAlpha: Double = 0.13
        public static let indexAlpha: Double = 0.165
        public static let maxAlpha: Double = 0.26
        public static let basinOpen: Double = 0.7
        public static let lightModeFactor: Double = 0.9
        public static let transitionSeconds: Double = 0.9
        public static let fps: Double = 20.0
        public static let maxProtectedRects = 20
        public static let pointerRadius: Double = 70.0
        public static let pointerStrength: Double = 0.28
        public static let pressDepth: Double = 0.055
        public static let pressSeconds: Double = 0.55
        public static let dragRippleEvery: Double = 70.0
        public static let clickRipple: Double = 0.3
        public static let layoutMoveThreshold: Double = 24.0
        public static let layoutRippleThrottleSeconds: Double = 0.35
        public static let layoutEdgeRipple: Double = 0.8
    }
}
