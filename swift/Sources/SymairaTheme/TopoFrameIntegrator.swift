import SwiftUI

private struct Animated {
    // Random start slice of the noise field: every mount (window, page) shows new terrain.
    var flowT = SymairaTopoView.startPhase(), rt = 0.0, last: Date?, nextThink = 0.0
    var cur = SymairaTopoState.idle.target, tintMix = 0.0
    var mouse = CGPoint(x: -1e4, y: -1e4), mouseAmt = 0.0, press = 0.0
    var lastOrigin: CGPoint?, lastSize: CGSize?
}

/// One frame value shared by the stitchable and native Metal paths.
struct TopoFrame {
    var vectors: [SIMD4<Float>]
    var canvas, topo, tint: SIMD4<Float>
    var rects, ripples: [Float]

    var shader: Shader {
        let library = ShaderLibrary.bundle(SymairaThemeResources.bundle)
        let arguments = vectors.map { Shader.Argument.float4($0.x, $0.y, $0.z, $0.w) }
        return Shader(
            function: ShaderFunction(library: library, name: "symairaTopo"),
            arguments: arguments + [
                .color(color(topo)), .color(color(tint)), .floatArray(rects), .floatArray(ripples),
            ])
    }

    private func color(_ v: SIMD4<Float>) -> Color {
        Color(.sRGB, red: Double(v.x), green: Double(v.y), blue: Double(v.z), opacity: Double(v.w))
    }
}

@MainActor
final class TopoFrameIntegrator {
    private var a = Animated()
    func reset() { a.last = nil }

    func frame(
        model: SymairaTopoModel, size: CGSize, origin o: CGPoint, now: Date,
        scheme: ColorScheme, displayScale: CGFloat, still: Bool, paused: Bool
    ) -> TopoFrame {
        // Zeitintegration (Zustände gleiten mit transitionSeconds)
        var a = self.a
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
        self.a = a

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
        func vector(_ x: Double, _ y: Double, _ z: Double, _ w: Double) -> SIMD4<Float> {
            SIMD4(Float(x), Float(y), Float(z), Float(w))
        }
        var environment = EnvironmentValues()
        environment.colorScheme = scheme
        func resolve(_ color: Color) -> SIMD4<Float> {
            let c = color.resolve(in: environment)
            return SIMD4(c.red, c.green, c.blue, c.opacity)
        }
        return TopoFrame(
            vectors: [
                vector(size.width, size.height, a.flowT, a.rt),
                vector(a.mouse.x, a.mouse.y, a.mouseAmt, dark ? 1 : tokens.lightModeFactor),
                vector(a.cur.warp, a.cur.think, a.cur.problem, a.cur.ask),
                vector(a.cur.tintAmount, ask.x, ask.y, displayScale),
                vector(tokens.scale, tokens.levels, tokens.lineAlpha, tokens.indexAlpha),
                vector(0, tokens.maxAlpha, tokens.basinOpen, a.press),
                vector(tokens.pointerRadius, tokens.pointerStrength, tokens.pressDepth, 0),
            ], canvas: resolve(SymairaTokens.canvas), topo: resolve(SymairaTokens.topo),
            tint: resolve(
                a.cur.tintIsCritical
                    ? SymairaTokens.critical : (a.cur.ask > 0.01 ? SymairaTokens.primary : SymairaTokens.topo)),
            rects: rects, ripples: rip)
    }
}
