// generiert von build.py aus DESIGN.md – nicht von Hand bearbeiten
import SwiftUI

#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif

public enum SymairaTokens {
    static func adaptive(_ l: (Double, Double, Double), _ d: (Double, Double, Double)) -> Color {
        #if canImport(AppKit)
        return Color(
            nsColor: NSColor(name: nil) { a in
                let c = a.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? d : l
                return NSColor(srgbRed: c.0, green: c.1, blue: c.2, alpha: 1)
            })
        #else
        return Color(
            uiColor: UIColor { t in
                let c = t.userInterfaceStyle == .dark ? d : l
                return UIColor(red: c.0, green: c.1, blue: c.2, alpha: 1)
            })
        #endif
    }

    public static let primary = adaptive((0.8784, 0.8235, 0.7294), (0.8784, 0.8235, 0.7294))
    public static let onPrimary = adaptive((0.1020, 0.0941, 0.0784), (0.1020, 0.0941, 0.0784))
    public static let primarySoft = adaptive((0.8863, 0.8706, 0.8353), (0.1922, 0.1843, 0.1686))
    public static let selected = adaptive((0.0784, 0.0784, 0.0745), (0.8784, 0.8235, 0.7294))
    public static let onSelected = adaptive((0.8824, 0.8784, 0.8549), (0.1020, 0.0941, 0.0784))
    public static let focus = adaptive((0.0784, 0.0784, 0.0745), (0.8784, 0.8235, 0.7294))
    public static let canvas = adaptive((0.9333, 0.9294, 0.9176), (0.1098, 0.1098, 0.1059))
    public static let sidebar = adaptive((0.8824, 0.8784, 0.8549), (0.0902, 0.0902, 0.0863))
    public static let surface = adaptive((0.8824, 0.8784, 0.8549), (0.0784, 0.0784, 0.0745))
    public static let raised = adaptive((0.9333, 0.9294, 0.9176), (0.1686, 0.1686, 0.1647))
    public static let selection = adaptive((0.6902, 0.6824, 0.6627), (0.1765, 0.1765, 0.1725))
    public static let line = adaptive((0.6902, 0.6824, 0.6627), (0.1882, 0.1882, 0.1804))
    public static let ink = adaptive((0.0784, 0.0784, 0.0745), (0.9333, 0.9294, 0.9176))
    public static let ink2 = adaptive((0.1686, 0.1686, 0.1647), (0.6902, 0.6824, 0.6627))
    public static let ink3 = adaptive((0.3843, 0.3804, 0.3647), (0.5922, 0.5843, 0.5608))
    public static let positive = adaptive((0.2039, 0.4118, 0.2902), (0.5765, 0.7686, 0.6235))
    public static let warning = adaptive((0.4941, 0.3255, 0.0627), (0.9137, 0.7373, 0.4510))
    public static let critical = adaptive((0.6039, 0.2745, 0.2039), (0.8902, 0.6118, 0.5412))
    public static let onCritical = adaptive((0.8824, 0.8784, 0.8549), (0.0784, 0.0784, 0.0745))
    public static let criticalSoft = adaptive((0.9490, 0.8706, 0.8471), (0.2275, 0.1608, 0.1451))
    public static let topo = adaptive((0.1686, 0.1686, 0.1647), (0.8824, 0.8784, 0.8549))

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
        public static let bandAlpha: Double = 0.018
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
