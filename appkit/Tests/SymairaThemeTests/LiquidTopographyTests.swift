import SwiftUI
import XCTest

@testable import SymairaTheme

/// Liquid Topography: Shader liegt im Bundle, rendert sichtbar, Schutzzonen bleiben frei.
@MainActor
final class LiquidTopographyTests: XCTestCase {
    func testShaderLibraryIsBundled() throws {
        let url = try XCTUnwrap(
            Bundle.module.url(forResource: "default", withExtension: "metallib"),
            "default.metallib fehlt im SymairaTheme-Bundle")
        XCTAssertGreaterThan(try Data(contentsOf: url).count, 1_000)
    }

    func testTopoParametersRespectReadabilityCap() {
        XCTAssertLessThanOrEqual(SymairaTokens.Topo.maxAlpha, 0.26)
        XCTAssertLessThanOrEqual(SymairaTokens.Topo.indexAlpha, SymairaTokens.Topo.maxAlpha)
        XCTAssertEqual(SymairaTokens.Topo.pointerRadius, 70)
        XCTAssertLessThanOrEqual(SymairaTokens.Topo.fps, 30)
    }

    func testStatesDifferInTempo() {
        XCTAssertGreaterThan(SymairaTopoState.thinking.target.speed, SymairaTopoState.idle.target.speed)
        XCTAssertLessThan(SymairaTopoState.problem.target.speed, SymairaTopoState.idle.target.speed)
        XCTAssertTrue(SymairaTopoState.problem.target.tintIsCritical)
    }

    func testRippleThrottlesKeyedSources() {
        let m = SymairaTopoModel()
        m.ripple(at: .zero, key: "a")
        m.ripple(at: .zero, key: "a")
        XCTAssertEqual(m.ripples.count, 1)
        m.ripple(at: .zero)
        XCTAssertEqual(m.ripples.count, 2)
    }

    func testLayoutChangeAboveThresholdEmitsRipple() {
        let m = SymairaTopoModel()
        m.layoutChanged(id: "card", rect: CGRect(x: 0, y: 0, width: 100, height: 100))
        m.layoutChanged(id: "card", rect: CGRect(x: 5, y: 0, width: 100, height: 100))
        XCTAssertTrue(m.ripples.isEmpty, "kleine Bewegung darf keine Welle auslösen")
        m.layoutChanged(id: "card", rect: CGRect(x: 0, y: 0, width: 100, height: 160))
        XCTAssertEqual(m.ripples.count, 1)
    }

    func testProtectionOverflowKeepsEveryVisibleElementCovered() {
        let model = SymairaTopoModel()
        let viewport = CGRect(x: 272, y: 40, width: 1000, height: 800)
        for i in 0..<25 {
            model.rects["element-\(i)"] = (CGRect(x: 300 + i * 20, y: 80, width: 30, height: 30), true)
        }
        model.rects["offscreen"] = (CGRect(x: 5000, y: 0, width: 100, height: 100), true)
        let values = model.protectedRects(in: viewport)
        XCTAssertEqual(values.count, 5, "overflow must use a conservative union, not a truncated list")
        let union = CGRect(
            x: CGFloat(values[0]) + viewport.minX, y: CGFloat(values[1]) + viewport.minY,
            width: CGFloat(values[2]), height: CGFloat(values[3]))
        for i in 0..<25 { XCTAssertTrue(union.contains(model.rects["element-\(i)"]!.0)) }
        XCTAssertEqual(values[4], 0, "overflow union must not add a large decorative hill")
    }

    func testProtectionFiltersOffscreenBeforeApplyingBudgetAndConvertsCoordinates() {
        let model = SymairaTopoModel()
        for i in 0..<30 { model.rects["outside-\(i)"] = (CGRect(x: -1000, y: -1000, width: 50, height: 50), false) }
        model.rects["visible"] = (CGRect(x: 300, y: 80, width: 100, height: 50), true)
        XCTAssertEqual(model.protectedRects(in: CGRect(x: 272, y: 40, width: 500, height: 400)), [28, 40, 100, 50, 1])
    }

    #if os(macOS)
    func testOverlappingProtectionDoesNotAccumulateShadowOrHill() throws {
        let startPhase = SymairaTopoView.startPhase
        SymairaTopoView.startPhase = { 0 }
        defer { SymairaTopoView.startPhase = startPhase }
        func render(_ count: Int) throws -> [UInt8] {
            let model = SymairaTopoModel()
            for index in 0..<count {
                model.rects["zone-\(index)"] = (CGRect(x: 100, y: 60, width: 100, height: 80), true)
            }
            let view = SymairaTopoView(model: model, animationEnabled: false)
                .frame(width: 300, height: 200)
                .coordinateSpace(name: SymairaTopo.space)
                .environment(\.colorScheme, .dark)
            let renderer = ImageRenderer(content: view)
            renderer.scale = 1
            return try pixels(XCTUnwrap(renderer.cgImage))
        }
        XCTAssertEqual(
            try render(1), try render(2), "nested protection must not add a dark halo or stronger contour hill")
    }

    /// Rendert die echte View offscreen: Linien sichtbar außerhalb, keine Linien in der Schutzzone.
    func testShaderRendersLinesAndKeepsProtectedZoneClear() throws {
        let model = SymairaTopoModel()
        let size = CGSize(width: 480, height: 320)
        let zone = CGRect(x: 160, y: 110, width: 160, height: 100)
        model.rects["zone"] = (zone, false)
        let view = SymairaTopoView(model: model)
            .frame(width: size.width, height: size.height)
            .coordinateSpace(name: SymairaTopo.space)
            .environment(\.colorScheme, .dark)
        let renderer = ImageRenderer(content: view)
        renderer.scale = 1
        let cg = try XCTUnwrap(renderer.cgImage, "ImageRenderer lieferte kein Bild")
        let px = try pixels(cg)
        let canvas = (r: 0x1C, g: 0x1C, b: 0x1B)
        func deviates(_ x: Int, _ y: Int) -> Bool {
            let i = (y * cg.width + x) * 4
            return abs(Int(px[i]) - canvas.r) + abs(Int(px[i + 1]) - canvas.g) + abs(Int(px[i + 2]) - canvas.b) > 6
        }
        var outside = 0
        var inside = 0
        for y in 0..<cg.height {
            for x in 0..<cg.width where deviates(x, y) {
                if zone.insetBy(dx: 6, dy: 6).contains(CGPoint(x: x, y: y)) { inside += 1 } else { outside += 1 }
            }
        }
        XCTAssertGreaterThan(outside, 500, "keine Höhenlinien gerendert")
        XCTAssertEqual(inside, 0, "Linien in der Schutzzone")
        // Lines are thin: a uniformly tinted field (zero fragment derivatives)
        // would deviate almost everywhere and turn protected zones into halos.
        let outsideTotal = cg.width * cg.height - Int(zone.width * zone.height)
        XCTAssertLessThan(Double(outside) / Double(outsideTotal), 0.5, "flächige Tönung statt Höhenlinien")
    }

    /// Scrolling and clicks add ripples. Behind the wave front the ripple term
    /// must stay finite: a NaN height saturates every pixel to the alpha cap,
    /// turning the whole surface flat grey with "halo" protection cut-outs.
    func testRippleKeepsContourLinesThin() throws {
        let model = SymairaTopoModel()
        let size = CGSize(width: 480, height: 320)
        model.ripple(at: CGPoint(x: 240, y: 160), strength: 1)
        model.ripples = model.ripples.map { ($0.0, Date.now.addingTimeInterval(-0.8), $0.2) }
        let view = SymairaTopoView(model: model)
            .frame(width: size.width, height: size.height)
            .coordinateSpace(name: SymairaTopo.space)
            .environment(\.colorScheme, .dark)
        let renderer = ImageRenderer(content: view)
        renderer.scale = 1
        let cg = try XCTUnwrap(renderer.cgImage)
        let px = try pixels(cg)
        var deviating = 0
        for i in stride(from: 0, to: px.count, by: 4)
        where abs(Int(px[i]) - 0x1C) + abs(Int(px[i + 1]) - 0x1C) + abs(Int(px[i + 2]) - 0x1B) > 6 {
            deviating += 1
        }
        XCTAssertLessThan(Double(deviating) / Double(cg.width * cg.height), 0.5, "Ripple sättigt die Fläche (NaN)")
    }

    /// Between the lines the surface is plain canvas. A per-level tint lifted whole
    /// bands by a few levels and drew faint shading edges along single contours.
    func testSurfaceBetweenLinesIsPlainCanvas() throws {
        let startPhase = SymairaTopoView.startPhase
        SymairaTopoView.startPhase = { 0 }
        defer { SymairaTopoView.startPhase = startPhase }
        let view = SymairaTopoView(model: SymairaTopoModel(), animationEnabled: false)
            .frame(width: 480, height: 320)
            .coordinateSpace(name: SymairaTopo.space)
            .environment(\.colorScheme, .dark)
        let renderer = ImageRenderer(content: view)
        renderer.scale = 1
        let cg = try XCTUnwrap(renderer.cgImage)
        let px = try pixels(cg)
        let canvas = [0x1C, 0x1C, 0x1B]
        var plain = 0
        for i in stride(from: 0, to: px.count, by: 4)
        where (0..<3).map({ abs(Int(px[i + $0]) - canvas[$0]) }).reduce(0, +) <= 1 {
            plain += 1
        }
        XCTAssertGreaterThan(Double(plain) / Double(cg.width * cg.height), 0.45, "surface between lines is tinted")
    }

    private func pixels(_ cg: CGImage) throws -> [UInt8] {
        var buf = [UInt8](repeating: 0, count: cg.width * cg.height * 4)
        let ctx = try XCTUnwrap(
            CGContext(
                data: &buf, width: cg.width, height: cg.height, bitsPerComponent: 8,
                bytesPerRow: cg.width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
        return buf
    }
    #endif
}
