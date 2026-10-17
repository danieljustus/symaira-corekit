import SwiftUI
import XCTest

@testable import SymairaTheme

#if os(macOS)
import AppKit
import Observation

@MainActor
final class WorkspaceFoundationTests: XCTestCase {
    func testSidebarPolicyKeepsWidthsAndContentBudget() {
        var state = SymairaSidebarState()
        state.resize(to: 328)
        state.expanded = false
        XCTAssertEqual(state.width, 64)
        state.expanded = true
        XCTAssertEqual(state.width, 328)
        state.resize(to: 1000)
        XCTAssertEqual(state.width, 360)
        state.resize(to: .nan)
        XCTAssertEqual(state.width, 360)
        state.availableWidth = 800
        XCTAssertEqual(state.width, 232)
        state.availableWidth = 620
        XCTAssertEqual(state.width, 64)
        state.availableWidth = 1080
        XCTAssertEqual(state.width, 360)
        state.resize(to: 80)
        XCTAssertFalse(state.showsLabels)
        state.step(1)
        XCTAssertEqual(state.width, 224)
        state.step(-1)
        XCTAssertEqual(state.width, 64)
    }

    func testMountedDragKeepsProtectionAlignedWhileAnimationIsPaused() async throws {
        _ = NSApplication.shared
        let state = WorkspaceFixtureState()
        let window = NSWindow(contentViewController: NSHostingController(rootView: WorkspaceFixture(state: state)))
        window.setContentSize(NSSize(width: 1080, height: 760))
        window.isReleasedWhenClosed = false
        window.makeKeyAndOrderFront(nil)
        defer { window.close() }
        try await Task.sleep(for: .milliseconds(150))
        let handle = try XCTUnwrap(
            descendants(window.contentView)
                .compactMap { $0 as? SymairaSidebarResizeHandle.Handle }.first)
        let slider = try XCTUnwrap(descendants(window.contentView).compactMap { $0 as? NSSlider }.first)
        for (distance, expected): (CGFloat, CGFloat) in [(56, 328), (200, 360), (-280, 64), (184, 248)] {
            let start = handle.convert(NSPoint(x: handle.bounds.midX, y: handle.bounds.midY), to: nil)
            XCTAssertTrue(window.contentView?.hitTest(start) === handle)
            for (type, x) in [
                (NSEvent.EventType.leftMouseDown, start.x),
                (.leftMouseDragged, start.x + distance), (.leftMouseUp, start.x + distance),
            ] {
                let event = try XCTUnwrap(
                    NSEvent.mouseEvent(
                        with: type, location: NSPoint(x: x, y: start.y), modifierFlags: [],
                        timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
                        context: nil, eventNumber: 0, clickCount: 1, pressure: 0))
                window.sendEvent(event)
                try await Task.sleep(for: .milliseconds(40))
            }
            XCTAssertEqual(state.sidebar.width, expected)
            XCTAssertTrue(descendants(window.contentView).contains { $0 === slider })
            XCTAssertEqual(slider.doubleValue, 0.43, accuracy: 0.001)
            XCTAssertEqual(state.topography.rects.count, 1, "No stale or duplicate protection after resize")
            let rect = try XCTUnwrap(state.topography.rects.values.first?.0)
            XCTAssertEqual(rect.minX, 24, accuracy: 0.5, "Protection stays local to the inset panel")
            XCTAssertEqual(rect.width, slider.bounds.width, accuracy: 0.5)
        }
    }

    func testContentActionRolesShareGeometryAndKeepDifferentColors() throws {
        _ = NSApplication.shared
        for scheme in [ColorScheme.light, .dark] {
            for fixedWidth in [false, true] {
                var images: [CGImage] = []
                for role in [SymairaButtonRole.primary, .secondary] {
                    let renderer = ImageRenderer(
                        content: Button {
                        } label: {
                            Text("Action").frame(maxWidth: fixedWidth ? .infinity : nil)
                        }
                        .symairaButtonStyle(role)
                        .frame(width: fixedWidth ? 280 : nil)
                        .environment(\.colorScheme, scheme))
                    renderer.scale = 2
                    images.append(try XCTUnwrap(renderer.cgImage))
                }
                XCTAssertEqual(images[0].width, images[1].width)
                XCTAssertEqual(images[0].height, images[1].height)
                XCTAssertEqual(images[0].height, 80)
                XCTAssertNotEqual(try sample(images[0]), try sample(images[1]))
            }
        }
        XCTAssertEqual(SymairaBarColors.track, SymairaTokens.ink3)
        XCTAssertEqual(SymairaBarColors.fill, SymairaTokens.ink)
    }

    func testAppearanceRestoresLiveSystemFollowing() {
        let app = NSApplication.shared
        let previous = app.appearance
        defer { app.appearance = previous }
        SymairaAppearance.dark.apply()
        XCTAssertEqual(app.appearance?.name, .darkAqua)
        SymairaAppearance.light.apply()
        XCTAssertEqual(app.appearance?.name, .aqua)
        SymairaAppearance.system.apply()
        XCTAssertNil(app.appearance)
        XCTAssertNil(SymairaAppearance.system.colorScheme)
    }

    private func descendants(_ view: NSView?) -> [NSView] {
        guard let view else { return [] }
        return [view] + view.subviews.flatMap { descendants($0) }
    }

    private func sample(_ image: CGImage) throws -> [UInt8] {
        var bytes = [UInt8](repeating: 0, count: image.width * image.height * 4)
        let context = try XCTUnwrap(
            CGContext(
                data: &bytes, width: image.width, height: image.height, bitsPerComponent: 8,
                bytesPerRow: image.width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        let offset = ((image.height / 2) * image.width + 10) * 4
        return Array(bytes[offset..<(offset + 3)])
    }
}

@MainActor @Observable
private final class WorkspaceFixtureState {
    var sidebar = SymairaSidebarState()
    let topography = SymairaTopoModel()
}

private struct WorkspaceFixture: View {
    @Bindable var state: WorkspaceFixtureState

    var body: some View {
        SymairaWorkspace(
            sidebar: $state.sidebar, topography: state.topography,
            animationEnabled: false,
            navigation: { labels in Text(labels ? "Navigation" : "N").frame(maxHeight: .infinity) },
            content: {
                VStack {
                    NativeSlider().frame(height: 40).topoProtected(hill: true)
                    Spacer()
                }.padding(24)
            }
        )

    }
}

private struct NativeSlider: NSViewRepresentable {
    func makeNSView(context: Context) -> NSSlider {
        NSSlider(value: 0.43, minValue: 0, maxValue: 1, target: nil, action: nil)
    }
    func updateNSView(_ view: NSSlider, context: Context) {}
}
#endif
