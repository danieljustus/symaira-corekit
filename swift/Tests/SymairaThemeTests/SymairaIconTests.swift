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

    func testNewIconsHaveExpectedNamesAndMotion() {
        let icons: [(SymairaIcon, String)] = [
            (.operate, "operate"), (.restart, "restart"), (.memory, "memory"), (.battery, "battery"),
            (.keepAwake, "keep-awake"), (.expired, "expired"), (.externalDrive, "external-drive"),
        ]
        for (icon, rawValue) in icons {
            XCTAssertEqual(icon.rawValue, rawValue)
            XCTAssertEqual(SymairaIcon(rawValue: rawValue), icon)
            XCTAssertTrue(icon.spec.contains { !$0.click.isEmpty }, "\(icon) needs click motion")
            XCTAssertTrue(
                icon.spec.contains {
                    $0.hover.x != 0 || $0.hover.y != 0 || $0.hover.r != 0
                        || $0.hover.s != 1 || $0.hover.sx != 1 || $0.hover.sy != 1
                },
                "\(icon) needs hover motion")
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
