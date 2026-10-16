import SwiftUI
import XCTest

@testable import SymairaTheme

@MainActor
final class SymairaIconTests: XCTestCase {
    func testEveryIconHasDrawableGeometry() {
        for icon in SymairaIcon.allCases {
            let paths = icon.spec.flatMap { $0.strokes + $0.fills }.map(IconPart.path)
            XCTAssertFalse(paths.isEmpty, "\(icon) has no geometry")
            for path in paths {
                let box = path.boundingRect
                XCTAssertTrue(
                    CGRect(x: 0, y: 0, width: 24, height: 24).insetBy(dx: -0.5, dy: -0.5).contains(box),
                    "\(icon) leaves the 24 pt grid: \(box)")
            }
        }
    }

    func testMotionsSettleBackToRest() {
        for icon in SymairaIcon.allCases {
            for track in icon.spec.flatMap(\.click) {
                let end = track.pose(at: track.delay + track.duration + 0.01)
                XCTAssertEqual(end.s, 1)
                XCTAssertEqual(end.x, 0)
                XCTAssertEqual(end.o, 1)
                XCTAssertEqual(end.d, 1)
            }
        }
    }

    func testCubicBezierMatchesEndpointsAndLinear() {
        XCTAssertEqual(cubicBezier((0, 0, 1, 1), 0.3), 0.3, accuracy: 0.001)
        XCTAssertEqual(cubicBezier((0.34, 1.56, 0.64, 1), 1), 1)
        XCTAssertGreaterThan(cubicBezier((0.34, 1.56, 0.64, 1), 0.6), 1, "spring must overshoot")
    }

    func testViewsRender() {
        for icon in SymairaIcon.allCases {
            ThemeRenderHost.render(SymairaIconView(icon, trigger: 1))
        }
        ThemeRenderHost.render(SymairaIconButton("Delete", icon: .delete) {})
        ThemeRenderHost.render(Label("Sync", symairaIcon: .refresh))
    }
}
