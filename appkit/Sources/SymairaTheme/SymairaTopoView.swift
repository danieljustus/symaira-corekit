import Observation
// Symaira Liquid Topography – SwiftUI-Hintergrund (macOS 14+ / iOS 17+).
// Nutzung:
//   ZStack { SymairaTopoView(model: topo); content }
//     .coordinateSpace(name: SymairaTopo.space)
//   Text("…").topoProtected(in: topo)          // Schutzzone
//   Card().topoProtected(in: topo, hill: true) // Schutzzone + Hügel
//   topo.state = .thinking ; topo.ripple(at: point)
import SwiftUI

#if os(macOS)
import AppKit
#endif

public enum SymairaTopo { public static let space = "symaira.topo" }

private struct SymairaTopographyKey: EnvironmentKey {
    static let defaultValue: SymairaTopoModel? = nil
}

extension EnvironmentValues {
    /// Set by SymairaWorkspace, or by a custom host sharing SymairaTopo.space.
    public var symairaTopography: SymairaTopoModel? {
        get { self[SymairaTopographyKey.self] }
        set { self[SymairaTopographyKey.self] = newValue }
    }
}

public enum SymairaTopoState: String, CaseIterable, Sendable {
    case idle, thinking, problem, input
    struct Target {
        let speed, warp, think, problem, ask, tintAmount: Double
        let tintIsCritical: Bool
    }
    var target: Target {
        switch self {  // 1:1 aus topo.json
        case .idle: Target(speed: 0.018, warp: 0.65, think: 0, problem: 0, ask: 0, tintAmount: 0, tintIsCritical: false)
        case .thinking:
            Target(speed: 0.04, warp: 0.75, think: 1, problem: 0, ask: 0, tintAmount: 0, tintIsCritical: false)
        case .problem:
            Target(speed: 0.012, warp: 0.6, think: 0, problem: 1, ask: 0, tintAmount: 0.55, tintIsCritical: true)
        case .input:
            Target(speed: 0.016, warp: 0.6, think: 0, problem: 0, ask: 1, tintAmount: 0.45, tintIsCritical: false)
        }
    }
}

@MainActor @Observable
public final class SymairaTopoModel {
    public var state: SymairaTopoState = .idle { didSet { if let s = statusPoint { ripple(at: s, strength: 0.9) } } }
    public var askPoint: CGPoint?
    public var statusPoint: CGPoint?
    // Geometry is written only by layout callbacks, not by the shader. Observe it
    // so paused/reduced-motion surfaces redraw after scrolling or a sidebar change.
    var rects: [String: (CGRect, Bool)] = [:]
    // Pointer over the surface: render at display rate instead of the idle cap.
    // Observed, but only flips on enter/exit, never per mouse move.
    var interactive = false
    // Per-frame accumulators remain unobserved: the shader mutates them itself.
    @ObservationIgnored var ripples: [(CGPoint, Date, Double)] = []
    @ObservationIgnored var pointer: CGPoint?
    @ObservationIgnored var pointerVelocity: Double = 0
    @ObservationIgnored var pressed = false
    @ObservationIgnored var dragTravel = 0.0
    @ObservationIgnored var anchors: [String: CGRect] = [:]
    @ObservationIgnored var lastKeyed: [String: Date] = [:]
    public init() {}
    /// Never drop a protected element. If the bounded shader budget is exceeded,
    /// conservatively protect their union (decoration gives way to readability).
    func protectedRects(in viewport: CGRect) -> [Float] {
        let visible = rects.values.filter { $0.0.intersects(viewport.insetBy(dx: -22, dy: -22)) }
            .sorted { a, b in
                a.0.minY == b.0.minY ? a.0.minX < b.0.minX : a.0.minY < b.0.minY
            }
        let selected: [(CGRect, Bool)]
        if visible.count > SymairaTokens.Topo.maxProtectedRects {
            selected = [(visible.reduce(CGRect.null) { $0.union($1.0) }, false)]
        } else {
            selected = visible
        }
        return selected.flatMap { r -> [Float] in
            [
                Float(r.0.minX - viewport.minX), Float(r.0.minY - viewport.minY),
                Float(r.0.width), Float(r.0.height), r.1 ? 1 : 0,
            ]
        }
    }
    /// Welle im Koordinatenraum `SymairaTopo.space`. Mit `key` gedrosselt (ein Auslöser feuert nicht pro Frame).
    public func ripple(at p: CGPoint, strength: Double = 1, key: String? = nil) {
        if let key {
            if let t = lastKeyed[key], Date.now.timeIntervalSince(t) < SymairaTokens.Topo.layoutRippleThrottleSeconds {
                return
            }
            lastKeyed[key] = .now
        }
        ripples.append((p, .now, strength))
        if ripples.count > 8 { ripples.removeFirst() }
    }
    /// GUI-Element hat sich bewegt/vergrößert (Aufklappen, Verschieben, Seitenleiste) → Welle ab Schwelle.
    func layoutChanged(id: String, rect: CGRect) {
        guard let a = anchors[id] else {
            anchors[id] = rect
            return
        }
        let d =
            abs(a.midX - rect.midX) + abs(a.midY - rect.midY) + abs(a.width - rect.width) + abs(a.height - rect.height)
        if d > SymairaTokens.Topo.layoutMoveThreshold {
            anchors[id] = rect
            ripple(at: CGPoint(x: rect.midX, y: rect.midY), strength: 0.6, key: id)
        }
    }
    #if os(macOS)
    /// Pointer im Raum `SymairaTopo.space`; `nil` = außerhalb. Beim Ziehen gelten die Deltas aus `handle`.
    func move(to p: CGPoint?) {
        guard !pressed else { return }
        if let p, let old = pointer {
            pointerVelocity = min(1, pointerVelocity + Double(hypot(p.x - old.x, p.y - old.y)) / 120)
        }
        pointer = p
        if interactive != (p != nil) { interactive = p != nil }
    }
    /// Klick, Halten und Ziehen. Beim Ziehen pausiert Hover, daher Position über Deltas fortschreiben.
    func handle(_ e: NSEvent) {
        guard var p = pointer else { return }
        let tokens = SymairaTokens.Topo.self
        switch e.type {
        case .leftMouseDown:
            pressed = true
            dragTravel = 0
            ripple(at: p, strength: tokens.clickRipple)
        case .leftMouseDragged:
            p.x += e.deltaX
            p.y += e.deltaY
            pointer = p
            let step = hypot(e.deltaX, e.deltaY)
            pointerVelocity = min(1, pointerVelocity + step / 120)
            dragTravel += step
            if dragTravel > tokens.dragRippleEvery {
                dragTravel = 0
                ripple(at: p, strength: 0.35)
            }
        case .leftMouseUp:
            pressed = false
        default: break
        }
    }
    #endif
}

private final class Clock {  // Referenztyp: Mutation im Render-Pfad invalidiert keine View
    var a = Animated()
}

private struct Animated {
    // Random start slice of the noise field: every mount (window, page) shows new terrain.
    var flowT = SymairaTopoView.startPhase(), rt = 0.0, last: Date?, nextThink = 0.0
    var cur = SymairaTopoState.idle.target, tintMix = 0.0
    var mouse = CGPoint(x: -1e4, y: -1e4), mouseAmt = 0.0, press = 0.0
    var lastOrigin: CGPoint?, lastSize: CGSize?
}

public struct SymairaTopoView: View {
    /// Start slice per mount; tests pin it to compare renders pixel for pixel.
    nonisolated(unsafe) static var startPhase: () -> Double = { .random(in: 0..<100) }
    /// SPM: Shader liegt im Modul-Bundle. Direkter swiftc-Build (Demo): App-Bundle.
    #if SWIFT_PACKAGE
    private static let library = ShaderLibrary.bundle(SymairaThemeResources.bundle)
    #else
    private static let library = ShaderLibrary.default
    #endif
    @Bindable var model: SymairaTopoModel
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.displayScale) private var displayScale
    @Environment(\.scenePhase) private var scenePhase
    @State private var clock = Clock()
    @State private var windowVisible = true
    private let animationEnabled: Bool
    public init(model: SymairaTopoModel, animationEnabled: Bool = true) {
        self.model = model
        self.animationEnabled = animationEnabled
    }

    private var lowPower: Bool { ProcessInfo.processInfo.isLowPowerModeEnabled }
    private var still: Bool { reduceMotion || lowPower || !animationEnabled }
    // AppKit-hosted windows (NSHostingView/Controller) report `.background`
    // permanently, which froze the timeline. macOS uses the owning window's
    // occlusion instead; scenePhase stays the signal on iOS.
    private var paused: Bool {
        #if os(macOS)
        still || !windowVisible
        #else
        still || !windowVisible || scenePhase == .background
        #endif
    }

    public var body: some View {
        GeometryReader { geo in
            TimelineView(
                .animation(minimumInterval: model.interactive ? nil : 1 / SymairaTokens.Topo.fps, paused: paused)
            ) { ctx in
                Rectangle().fill(SymairaTokens.canvas)  // Shader zeichnet die Linien über die Canvas-Farbe
                    .colorEffect(
                        // A paused timeline keeps its last date while layout still redraws;
                        // never let ripple ages run negative (they then grow unbounded).
                        shader(
                            size: geo.size, origin: geo.frame(in: .named(SymairaTopo.space)).origin,
                            now: max(ctx.date, .now)))
            }
            #if os(macOS)
            .background(TopoPointerTracker(model: model, origin: geo.frame(in: .named(SymairaTopo.space)).origin))
            #endif
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
        #if os(macOS)
        .background(TopoWindowVisibility(visible: $windowVisible))
        #endif
        .onChange(of: paused) { _, _ in
            clock.a.last = nil
            model.pressed = false
            model.pointer = nil
            model.interactive = false
            model.ripples.removeAll()
        }
    }

    /// Alle Eingänge kommen im Koordinatenraum `SymairaTopo.space`; der Shader rechnet im lokalen Raum der View.
    /// Die View kann davon abweichen (z. B. `ignoresSafeArea` unter einer eingeblendeten Sidebar) → Ursprung abziehen.
    private func shader(size: CGSize, origin o: CGPoint, now: Date) -> Shader {
        // Zeitintegration (Zustände gleiten mit transitionSeconds)
        var a = clock.a
        let dt = min(0.06, a.last.map { now.timeIntervalSince($0) } ?? 0)
        let f = 1 - exp(-dt / SymairaTokens.Topo.transitionSeconds)
        let tg = model.state.target
        a.last = now
        func ease(_ c: Double, _ t: Double) -> Double { c + (t - c) * f }
        a.cur = .init(
            speed: ease(a.cur.speed, tg.speed), warp: ease(a.cur.warp, tg.warp), think: ease(a.cur.think, tg.think),
            problem: ease(a.cur.problem, tg.problem), ask: ease(a.cur.ask, tg.ask),
            tintAmount: ease(a.cur.tintAmount, tg.tintAmount), tintIsCritical: tg.tintIsCritical)
        if !paused {
            a.flowT += a.cur.speed * dt
            a.rt += dt
        }
        if model.state == .thinking, a.rt > a.nextThink, let s = model.statusPoint {
            model.ripple(at: s, strength: 0.8)
            a.nextThink = a.rt + 1.4
        }
        let target = still ? nil : model.pointer.map { CGPoint(x: $0.x - o.x, y: $0.y - o.y) }
        if let p = target {
            let m = 1 - exp(-dt / 0.12)
            a.mouse =
                a.mouse.x < -9e3
                ? p : CGPoint(x: a.mouse.x + (p.x - a.mouse.x) * m, y: a.mouse.y + (p.y - a.mouse.y) * m)
        }
        model.pointerVelocity *= exp(-dt / 0.5)
        let goal = target == nil ? 0 : 0.45 + 0.55 * model.pointerVelocity
        a.mouseAmt += (goal - a.mouseAmt) * (1 - exp(-dt / 0.25))
        a.press += ((still || !model.pressed ? 0 : 1) - a.press) * (1 - exp(-dt / SymairaTokens.Topo.pressSeconds))
        // Fläche verschoben/verkleinert (z. B. Seitenleiste auf/zu) → Welle von der Kante
        if let lo = a.lastOrigin, let ls = a.lastSize,
            abs(lo.x - o.x) + abs(lo.y - o.y) + abs(ls.width - size.width) > 1
        {
            model.ripple(
                at: CGPoint(x: 0, y: o.y + size.height / 2), strength: SymairaTokens.Topo.layoutEdgeRipple,
                key: "layout.edge")
        }
        a.lastOrigin = o
        a.lastSize = size
        model.ripples.removeAll { now.timeIntervalSince($0.1) > 2.4 }
        clock.a = a

        let rects = model.protectedRects(in: CGRect(origin: o, size: size))
        let rip: [Float] =
            still
            ? []
            : model.ripples.flatMap { r -> [Float] in
                [Float(r.0.x - o.x), Float(r.0.y - o.y), Float(max(0, now.timeIntervalSince(r.1))), Float(r.2)]
            }
        let dark = scheme == .dark
        let ask =
            model.askPoint.map { CGPoint(x: $0.x - o.x, y: $0.y - o.y) }
            ?? CGPoint(x: size.width / 2, y: size.height - 60)
        let tokens = SymairaTokens.Topo.self
        return Self.library.symairaTopo(
            .float4(size.width, size.height, a.flowT, a.rt),
            .float4(a.mouse.x, a.mouse.y, a.mouseAmt, dark ? 1 : tokens.lightModeFactor),
            .float4(a.cur.warp, a.cur.think, a.cur.problem, a.cur.ask),
            .float4(a.cur.tintAmount, ask.x, ask.y, displayScale),
            .float4(tokens.scale, tokens.levels, tokens.lineAlpha, tokens.indexAlpha),
            .float4(tokens.bandAlpha, tokens.maxAlpha, tokens.basinOpen, a.press),
            .float4(tokens.pointerRadius, tokens.pointerStrength, tokens.pressDepth, 0),
            .color(SymairaTokens.topo),
            .color(
                a.cur.tintIsCritical
                    ? SymairaTokens.critical : (a.cur.ask > 0.01 ? SymairaTokens.primary : SymairaTokens.topo)),
            .floatArray(rects),
            .floatArray(rip))
    }
}

extension View {
    /// Protect within the enclosing workspace; inert without a topography model
    /// (for example in popovers and settings). No app-local environment needed.
    public func topoProtected(hill: Bool = false) -> some View {
        modifier(WorkspaceTopoProtect(hill: hill))
    }

    /// Schutzzone: keine Höhenlinien unter diesem Element. `hill`: Linien legen sich drumherum.
    public func topoProtected(in model: SymairaTopoModel, hill: Bool = false, id: String = UUID().uuidString)
        -> some View
    {
        modifier(TopoProtect(model: model, hill: hill, id: id))
    }
}

private struct WorkspaceTopoProtect: ViewModifier {
    @Environment(\.symairaTopography) private var model
    let hill: Bool

    @ViewBuilder func body(content: Content) -> some View {
        if let model {
            content.topoProtected(in: model, hill: hill)
        } else {
            content
        }
    }
}

private struct TopoProtect: ViewModifier {
    let model: SymairaTopoModel
    let hill: Bool
    @State var id: String
    init(model: SymairaTopoModel, hill: Bool, id: String) {
        self.model = model
        self.hill = hill
        _id = State(initialValue: id)
    }
    func body(content: Content) -> some View {
        content
            .onGeometryChange(for: CGRect.self) {
                $0.frame(in: .named(SymairaTopo.space))
            } action: {
                model.layoutChanged(id: id, rect: $0)
                model.rects[id] = ($0, hill)
            }
            .onDisappear {
                model.rects[id] = nil
                model.anchors[id] = nil
                model.lastKeyed[id] = nil
            }
    }
}

#if os(macOS)
/// Observe the owning window, not the application's key window. No polling and
/// no input interception; a covered/minimized window stops its own timeline.
private struct TopoWindowVisibility: NSViewRepresentable {
    @Binding var visible: Bool
    func makeNSView(context: Context) -> Probe {
        let binding = $visible
        let view = Probe()
        view.changed = { value in
            Task { @MainActor in
                if binding.wrappedValue != value { binding.wrappedValue = value }
            }
        }
        return view
    }
    func updateNSView(_ view: Probe, context: Context) {}
    static func dismantleNSView(_ view: Probe, coordinator: ()) { view.stop() }

    final class Probe: NSView {
        var changed: ((Bool) -> Void)?
        private var observers: [NSObjectProtocol] = []
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        func stop() {
            observers.forEach(NotificationCenter.default.removeObserver)
            observers.removeAll()
        }
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            stop()
            guard let window else {
                changed?(false)
                return
            }
            for name in [
                NSWindow.didChangeOcclusionStateNotification,
                NSWindow.didMiniaturizeNotification, NSWindow.didDeminiaturizeNotification,
            ] {
                observers.append(
                    NotificationCenter.default.addObserver(forName: name, object: window, queue: .main) {
                        [weak self] _ in
                        MainActor.assumeIsolated { self?.publish() }
                    })
            }
            publish()
        }
        private func publish() {
            changed?(window.map { $0.isVisible && !$0.isMiniaturized && $0.occlusionState.contains(.visible) } ?? false)
        }
    }
}
#endif

#if os(macOS)
/// Observes this window's pointer events without consuming them, so content layered
/// over the topography (scroll views, lists, cards) never hides the pointer from it.
/// SwiftUI hover on a background view only fires where nothing above is hit-testable.
private struct TopoPointerTracker: NSViewRepresentable {
    let model: SymairaTopoModel
    let origin: CGPoint
    func makeNSView(context: Context) -> Probe { Probe(model: model) }
    func updateNSView(_ view: Probe, context: Context) {
        view.model = model
        view.origin = origin
    }
    static func dismantleNSView(_ view: Probe, coordinator: ()) { view.stop() }

    final class Probe: NSView {
        var model: SymairaTopoModel
        var origin = CGPoint.zero
        private var monitor: Any?
        init(model: SymairaTopoModel) {
            self.model = model
            super.init(frame: .zero)
        }
        required init?(coder: NSCoder) { nil }
        override var isFlipped: Bool { true }  // SwiftUI coordinates: origin top-left
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        func stop() {
            if let monitor { NSEvent.removeMonitor(monitor) }
            monitor = nil
        }
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            stop()
            guard let window else { return }
            window.acceptsMouseMovedEvents = true
            // Lokaler Monitor beobachtet nur, Events laufen unverändert weiter an Buttons usw.
            monitor = NSEvent.addLocalMonitorForEvents(
                matching: [.mouseMoved, .leftMouseDown, .leftMouseDragged, .leftMouseUp]
            ) { [weak self] e in
                MainActor.assumeIsolated { self?.observe(e) }
                return e
            }
        }
        // Leaving the window sends no further mouseMoved; a tracking area reports the exit.
        override func updateTrackingAreas() {
            super.updateTrackingAreas()
            trackingAreas.forEach(removeTrackingArea)
            addTrackingArea(
                NSTrackingArea(
                    rect: .zero, options: [.mouseEnteredAndExited, .activeInKeyWindow, .inVisibleRect], owner: self))
        }
        override func mouseExited(with event: NSEvent) { model.move(to: nil) }
        func observe(_ e: NSEvent) {
            guard e.window === window else { return }
            if e.type == .mouseMoved {
                let p = convert(e.locationInWindow, from: nil)
                model.move(to: bounds.contains(p) ? CGPoint(x: p.x + origin.x, y: p.y + origin.y) : nil)
            } else {
                model.handle(e)
            }
        }
    }
}
#endif
