import SwiftUI

// `SymairaIcon` cases, labels and drawing data live in the generated
// `SymairaIconData.swift` (scripts/build-icons.py). This file renders them.

/// An icon with Symaira micro-interactions: on hover its parts move to a small
/// preview pose, and whenever `trigger` changes it plays its click motion
/// (lid lifts, bell rings, check draws …). Honours Reduce Motion.
public struct SymairaIconView<Trigger: Equatable>: View {
    private let icon: SymairaIcon
    private let size: CGFloat
    private let trigger: Trigger
    @State private var isHovered = false
    @State private var hoverChange = Date.distantPast
    @State private var clickStart = Date.distantPast
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init(_ icon: SymairaIcon, size: CGFloat = 20, trigger: Trigger) {
        self.icon = icon
        self.size = size
        self.trigger = trigger
    }

    public var body: some View {
        let parts = icon.spec
        let busyUntil = max(
            hoverChange.addingTimeInterval(IconPart.hoverDuration),
            clickStart.addingTimeInterval(parts.map(\.clickDuration).max() ?? 0))
        TimelineView(.animation(paused: reduceMotion || Date() > busyUntil)) { timeline in
            Canvas { context, canvasSize in
                let now = timeline.date
                let hover =
                    reduceMotion
                    ? 0
                    : IconPart.hoverProgress(
                        isHovered: isHovered, since: now.timeIntervalSince(hoverChange))
                let elapsed = reduceMotion ? .infinity : now.timeIntervalSince(clickStart)
                for part in parts {
                    part.draw(in: &context, size: canvasSize, hover: hover, elapsed: elapsed)
                }
            }
        }
        .frame(width: size, height: size)
        .onHover { hovering in
            isHovered = hovering
            hoverChange = Date()
        }
        .onChange(of: trigger) { clickStart = Date() }
        .accessibilityHidden(true)
    }
}

extension SymairaIconView where Trigger == Int {
    /// Hover-only icon (no click trigger).
    public init(_ icon: SymairaIcon, size: CGFloat = 20) {
        self.init(icon, size: size, trigger: 0)
    }
}

/// A plain icon button that plays the icon's motion on every press.
public struct SymairaIconButton: View {
    private let title: LocalizedStringKey
    private let icon: SymairaIcon
    private let size: CGFloat
    private let action: () -> Void
    @State private var taps = 0

    public init(_ title: LocalizedStringKey, icon: SymairaIcon, size: CGFloat = 20, action: @escaping () -> Void) {
        self.title = title
        self.icon = icon
        self.size = size
        self.action = action
    }

    public var body: some View {
        Button {
            taps += 1
            action()
        } label: {
            SymairaIconView(icon, size: size, trigger: taps)
                .contentShape(Rectangle())
        }
        .buttonStyle(.borderless)
        .accessibilityLabel(Text(title))
        .help(Text(title))
    }
}

extension Label where Title == Text, Icon == SymairaIconView<Int> {
    /// `Label("Delete", symairaIcon: .delete)`
    public init(_ title: LocalizedStringKey, symairaIcon icon: SymairaIcon) {
        self.init {
            Text(title)
        } icon: {
            SymairaIconView(icon)
        }
    }
}

// MARK: - Engine

struct IconPose: Sendable {
    var s = 1.0, sx = 1.0, sy = 1.0, r = 0.0, x = 0.0, y = 0.0, o = 1.0, d = 1.0
    static let identity = IconPose()

    func mix(_ other: IconPose, _ t: Double) -> IconPose {
        func l(_ a: Double, _ b: Double) -> Double { a + (b - a) * t }
        return IconPose(
            s: l(s, other.s), sx: l(sx, other.sx), sy: l(sy, other.sy), r: l(r, other.r),
            x: l(x, other.x), y: l(y, other.y), o: l(o, other.o), d: l(d, other.d))
    }

    /// Stack a click pose on top of the hover pose.
    func adding(_ other: IconPose) -> IconPose {
        IconPose(
            s: s * other.s, sx: sx * other.sx, sy: sy * other.sy, r: r + other.r,
            x: x + other.x, y: y + other.y, o: o * other.o, d: min(d, other.d))
    }
}

struct IconTrack: Sendable {
    let duration: Double
    let delay: Double
    let ease: (Double, Double, Double, Double)
    let draws: Bool
    let frames: [(Double, IconPose)]

    /// Pose at `elapsed` seconds after the click with CSS keyframe semantics:
    /// easing applies per segment, the first frame holds during the delay.
    func pose(at elapsed: Double) -> IconPose {
        let t = (elapsed - delay) / duration
        guard t < 1 else { return .identity }
        guard t > 0 else { return frames[0].1 }
        let i = frames.lastIndex { $0.0 <= t } ?? 0
        let (t0, a) = frames[i]
        let (t1, b) = frames[min(i + 1, frames.count - 1)]
        let local = t1 > t0 ? (t - t0) / (t1 - t0) : 1
        return a.mix(b, cubicBezier(ease, local))
    }
}

struct IconPart: Sendable {
    let origin: CGPoint
    let strokes: [[Double]]
    let fills: [[Double]]
    let hover: IconPose
    let click: [IconTrack]

    static let hoverDuration = 0.3
    var clickDuration: Double { click.map { $0.delay + $0.duration }.max() ?? 0 }

    /// 0…1 hover blend with a slight spring overshoot, like the web CSS.
    static func hoverProgress(isHovered: Bool, since: Double) -> Double {
        let e = cubicBezier((0.34, 1.56, 0.64, 1), min(1, max(0, since / hoverDuration)))
        return isHovered ? e : 1 - e
    }

    func draw(in context: inout GraphicsContext, size: CGSize, hover: Double, elapsed: Double) {
        var pose = IconPose.identity.mix(self.hover, hover)
        var draw = 1.0
        for track in click {
            let p = track.pose(at: elapsed)
            if track.draws { draw = p.d } else { pose = pose.adding(p) }
        }
        let unit = size.width / 24
        let transform = CGAffineTransform(translationX: origin.x + pose.x, y: origin.y + pose.y)
            .rotated(by: pose.r * .pi / 180)
            .scaledBy(x: pose.s * pose.sx, y: pose.s * pose.sy)
            .translatedBy(x: -origin.x, y: -origin.y)
            .concatenating(CGAffineTransform(scaleX: unit, y: unit))
        var ctx = context
        ctx.opacity = max(0, pose.o)
        let style = StrokeStyle(lineWidth: 2 * unit, lineCap: .round, lineJoin: .round)
        for ops in strokes {
            let path = Self.path(ops)
            let visible = draw < 1 ? path.trimmedPath(from: 0, to: max(0, draw)) : path
            ctx.stroke(visible.applying(transform), with: .foreground, style: style)
        }
        for ops in fills {
            ctx.fill(Self.path(ops).applying(transform), with: .foreground)
        }
    }

    static func path(_ ops: [Double]) -> Path {
        var p = Path()
        var i = 0
        func pt(_ k: Int) -> CGPoint { CGPoint(x: ops[i + k], y: ops[i + k + 1]) }
        while i < ops.count {
            switch ops[i] {
            case 0:
                p.move(to: pt(1))
                i += 3
            case 1:
                p.addLine(to: pt(1))
                i += 3
            case 2:
                p.addCurve(to: pt(5), control1: pt(1), control2: pt(3))
                i += 7
            default:
                p.closeSubpath()
                i += 1
            }
        }
        return p
    }
}

/// CSS `cubic-bezier()` timing: solve x(t) = progress, return y(t).
func cubicBezier(_ c: (Double, Double, Double, Double), _ x: Double) -> Double {
    if x <= 0 { return 0 }
    if x >= 1 { return 1 }
    func b(_ t: Double, _ p1: Double, _ p2: Double) -> Double {
        3 * (1 - t) * (1 - t) * t * p1 + 3 * (1 - t) * t * t * p2 + t * t * t
    }
    var lo = 0.0
    var hi = 1.0
    var t = x
    for _ in 0..<24 {
        t = (lo + hi) / 2
        if b(t, c.0, c.2) < x { lo = t } else { hi = t }
    }
    return b(t, c.1, c.3)
}
