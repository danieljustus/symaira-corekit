import Observation
import SwiftUI
import XCTest
import os

@testable import SymairaTheme

#if os(macOS)
import AppKit
#endif

@MainActor
final class TopographyLayoutTests: XCTestCase {
    func testGeometryInvalidatesPausedShaderWithoutObservingFrameAccumulators() {
        let model = SymairaTopoModel()
        let viewport = CGRect(x: 64, y: 30, width: 600, height: 500)
        model.rects["card"] = (CGRect(x: 296, y: 70, width: 300, height: 100), true)

        for rect in [CGRect(x: 88, y: 70, width: 508, height: 100), nil] {
            let invalidated = OSAllocatedUnfairLock(initialState: false)
            withObservationTracking {
                _ = model.protectedRects(in: viewport)
            } onChange: {
                invalidated.withLock { $0 = true }
            }
            model.rects["card"] = rect.map { ($0, true) }
            XCTAssertTrue(invalidated.withLock { $0 }, "Layout/removal must redraw even when the timeline is paused")
            if rect != nil {
                XCTAssertEqual(model.protectedRects(in: viewport), [24, 40, 508, 100, 1])
            } else {
                XCTAssertTrue(model.protectedRects(in: viewport).isEmpty)
            }
        }

        let frameInvalidated = OSAllocatedUnfairLock(initialState: false)
        withObservationTracking {
            _ = model.pointer
            _ = model.ripples
        } onChange: {
            frameInvalidated.withLock { $0 = true }
        }
        model.pointer = .zero
        model.ripple(at: .zero)
        XCTAssertFalse(frameInvalidated.withLock { $0 }, "Render-path writes must not recreate the observation loop")
    }

    #if os(macOS)
    func testMountedProtectionFollowsSidebarAndResizeWhilePaused() async throws {
        _ = NSApplication.shared
        let model = SymairaTopoModel()
        let layout = LayoutState()
        let host = NSHostingView(rootView: MountedLayout(model: model, layout: layout))
        let window = NSWindow(
            contentRect: CGRect(x: 0, y: 0, width: 980, height: 360),
            styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = host
        defer { window.close() }
        for (sidebar, width) in [(272.0, 980.0), (64.0, 980.0), (272.0, 980.0), (64.0, 620.0)] {
            layout.sidebarWidth = sidebar
            window.setContentSize(CGSize(width: width, height: 360))
            host.layoutSubtreeIfNeeded()
            try await Task.sleep(for: .milliseconds(150))
            XCTAssertEqual(model.rects.count, 1, "Reflow must update the existing protection, not retain ghosts")
            XCTAssertEqual(model.protectedRects(in: layout.viewport), [24, 24, Float(width - sidebar - 48), 100, 1])
        }
    }
    #endif
}

#if os(macOS)
@MainActor @Observable
private final class LayoutState {
    var sidebarWidth: CGFloat = 272
    @ObservationIgnored var viewport = CGRect.zero
}

private struct MountedLayout: View {
    let model: SymairaTopoModel
    let layout: LayoutState

    var body: some View {
        HStack(spacing: 0) {
            Color.clear.frame(width: layout.sidebarWidth)
            ZStack {
                SymairaTopoView(model: model, animationEnabled: false)
                    .onGeometryChange(for: CGRect.self) {
                        $0.frame(in: .named(SymairaTopo.space))
                    } action: {
                        layout.viewport = $0
                    }
                ScrollView {
                    Color.clear.frame(height: 100)
                        .topoProtected(in: model, hill: true, id: "mounted-card")
                }
                .padding(24)
            }
            .coordinateSpace(name: SymairaTopo.space)
        }
    }
}
#endif
