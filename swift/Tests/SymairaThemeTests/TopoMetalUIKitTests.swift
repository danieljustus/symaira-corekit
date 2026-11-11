#if canImport(UIKit)
import SwiftUI
import UIKit
import XCTest

@testable import SymairaTheme

/// Runs on iOS/tvOS simulators only (`swift test` on macOS compiles none of it).
@MainActor
final class TopoMetalUIKitTests: XCTestCase {
    private func attached(_ view: TopoMetalView) -> UIWindow {
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 300, height: 200))
        view.frame = window.bounds
        window.addSubview(view)
        window.isHidden = false
        return window
    }

    func testDisplayLinkFollowsPauseAndWindowLifecycle() {
        let model = SymairaTopoModel()
        let view = TopoMetalView()
        let window = attached(view)
        view.configure(model: model, origin: .zero, scheme: .dark, still: false, visible: true)
        if ProcessInfo.processInfo.isLowPowerModeEnabled {
            XCTAssertFalse(view.isDrawing, "Low Power Mode must not run a display link")
        } else {
            XCTAssertTrue(view.isDrawing, "unpaused view in a window runs a display link")
            view.configure(model: model, origin: .zero, scheme: .dark, still: true, visible: true)
            XCTAssertFalse(view.isDrawing, "Reduce Motion / animationEnabled=false stops the link")
            view.configure(model: model, origin: .zero, scheme: .dark, still: false, visible: true)
            XCTAssertTrue(view.isDrawing)
            view.configure(model: model, origin: .zero, scheme: .dark, still: false, visible: false)
            XCTAssertFalse(view.isDrawing, "background scene stops the link")
            view.configure(model: model, origin: .zero, scheme: .dark, still: false, visible: true)
            XCTAssertTrue(view.isDrawing)
            view.removeFromSuperview()
            XCTAssertFalse(view.isDrawing, "removal from the window invalidates the link")
        }
        view.stop()
        withExtendedLifetime(window) {}
    }

    func testStopInvalidatesDisplayLinkAndIgnoresLaterConfigure() {
        let model = SymairaTopoModel()
        let view = TopoMetalView()
        let window = attached(view)
        view.configure(model: model, origin: .zero, scheme: .light, still: false, visible: true)
        view.stop()
        XCTAssertFalse(view.isDrawing)
        view.configure(model: model, origin: .zero, scheme: .light, still: false, visible: true)
        XCTAssertFalse(view.isDrawing, "a stopped view never restarts")
        withExtendedLifetime(window) {}
    }

    func testDroppedViewDoesNotLeak() {
        weak var weakView: TopoMetalView?
        autoreleasepool {
            let view = TopoMetalView()
            let window = attached(view)
            view.configure(model: SymairaTopoModel(), origin: .zero, scheme: .dark, still: false, visible: true)
            weakView = view
            view.removeFromSuperview()
            withExtendedLifetime(window) {}
        }
        XCTAssertNil(weakView, "the display link must not retain the view")
    }

    func testStaticFrameDrawsOnDemandOnGeometryChange() throws {
        let model = SymairaTopoModel()
        let view = TopoMetalView()
        let window = attached(view)
        view.configure(model: model, origin: .zero, scheme: .dark, still: true, visible: true)
        view.layoutIfNeeded()
        let drawn = view.framesDrawn
        model.rects["zone"] = (CGRect(x: 0, y: 0, width: 50, height: 50), false)
        RunLoop.main.run(until: Date.now.addingTimeInterval(0.2))
        if drawn == 0 && view.framesDrawn == 0 { throw XCTSkip("No Metal drawable in this environment") }
        XCTAssertGreaterThan(view.framesDrawn, drawn, "protection changes redraw a static surface")
        XCTAssertFalse(view.isDrawing)
        view.stop()
        withExtendedLifetime(window) {}
    }
}
#endif
