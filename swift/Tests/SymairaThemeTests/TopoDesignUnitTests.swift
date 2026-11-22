import SwiftUI
import XCTest

@testable import SymairaTheme

/// The topography works in the Symaira scale: on tvOS (`platformScale` 2) one topography
/// point spans two screen points, so terrain, lines, ripples and protection margins grow
/// together with every other Symaira size.
@MainActor
final class TopoDesignUnitTests: XCTestCase {
    private func model(_ k: CGFloat) -> SymairaTopoModel {
        let model = SymairaTopoModel()
        model.rects["card"] = (CGRect(x: 110 * k, y: 70 * k, width: 80 * k, height: 40 * k), true)
        model.pointer = CGPoint(x: 150 * k, y: 90 * k)
        model.askPoint = CGPoint(x: 60 * k, y: 30 * k)
        model.ripples = [(CGPoint(x: 40 * k, y: 50 * k), Date(timeIntervalSinceReferenceDate: 99), 1)]
        return model
    }

    func testUnitScalesEveryFrameValueTogether() {
        let previous = SymairaTopoView.startPhase
        SymairaTopoView.startPhase = { 0 }
        defer { SymairaTopoView.startPhase = previous }
        let now = Date(timeIntervalSinceReferenceDate: 100)
        let desk = TopoFrameIntegrator().frame(
            model: model(1), size: CGSize(width: 300, height: 200), origin: CGPoint(x: 10, y: 20), now: now,
            scheme: .dark, displayScale: 4, still: false, paused: true, unit: 1)
        let couch = TopoFrameIntegrator().frame(
            model: model(2), size: CGSize(width: 600, height: 400), origin: CGPoint(x: 20, y: 40), now: now,
            scheme: .dark, displayScale: 2, still: false, paused: true, unit: 2)
        // Same device pixels per topography point (4), same terrain, rects, ripples and pointer.
        XCTAssertEqual(couch.vectors, desk.vectors)
        XCTAssertEqual(couch.rects, desk.rects)
        XCTAssertEqual(couch.ripples, desk.ripples)
        XCTAssertFalse(couch.rects.isEmpty)
        XCTAssertFalse(couch.ripples.isEmpty)
    }

    func testDefaultUnitIsThePlatformScale() {
        let frame = TopoFrameIntegrator().frame(
            model: SymairaTopoModel(), size: CGSize(width: 600, height: 400), origin: .zero, now: .now,
            scheme: .light, displayScale: 2, still: true, paused: true)
        let scale = Float(SymairaMetrics.platformScale)
        XCTAssertEqual(frame.vectors[0].x, 600 / scale, "shader size is in topography points")
        XCTAssertEqual(frame.vectors[3].w, 2 * scale, "device pixels per topography point")
    }

    func testProtectedRectsKeepTheHillFlagWhenScaled() {
        let model = SymairaTopoModel()
        model.rects["a"] = (CGRect(x: 40, y: 60, width: 100, height: 20), true)
        XCTAssertEqual(
            model.protectedRects(in: CGRect(x: 20, y: 20, width: 400, height: 300), unit: 2), [10, 20, 50, 10, 1])
    }
}
