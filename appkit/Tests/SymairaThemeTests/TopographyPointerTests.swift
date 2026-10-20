import SwiftUI
import XCTest

@testable import SymairaTheme

#if os(macOS)
import AppKit

/// Hosts put scrolling content over the whole panel; the topography must still see the pointer.
@MainActor
final class TopographyPointerTests: XCTestCase {
    func testPointerReachesTopographyBehindFullPanelScrollContent() async throws {
        _ = NSApplication.shared
        let model = SymairaTopoModel()
        let root = SymairaWorkspace(
            sidebar: .constant(SymairaSidebarState()), topography: model,
            navigation: { _ in Color.clear },
            content: {
                ScrollView {
                    Text("Content").frame(maxWidth: .infinity, minHeight: 900, alignment: .topLeading)
                }
            })
        let window = NSWindow(
            contentRect: CGRect(x: 0, y: 0, width: 900, height: 600),
            styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = NSHostingView(rootView: root)
        window.orderFront(nil)
        defer { window.close() }
        try await Task.sleep(for: .milliseconds(200))

        func move(to point: NSPoint) throws {
            let event = NSEvent.mouseEvent(
                with: .mouseMoved, location: point, modifierFlags: [], timestamp: 0,
                windowNumber: window.windowNumber, context: nil, eventNumber: 0, clickCount: 0, pressure: 0)
            NSApp.sendEvent(try XCTUnwrap(event))
        }

        // Window coordinates are bottom-left; the topography space is top-left at the panel origin.
        try move(to: NSPoint(x: 700, y: 450))
        let pointer = try XCTUnwrap(model.pointer, "Hover over full-panel content must reach the topography")
        let sidebar = SymairaSidebarState().width
        XCTAssertEqual(pointer.x, 700 - sidebar, accuracy: 1)
        XCTAssertEqual(pointer.y, 150, accuracy: 1)
        XCTAssertTrue(model.interactive, "Pointer over the surface renders at display rate")

        try move(to: NSPoint(x: 710, y: 440))
        XCTAssertGreaterThan(model.pointerVelocity, 0, "Movement drives the pointer response")

        try move(to: NSPoint(x: sidebar / 2, y: 300))
        XCTAssertNil(model.pointer, "The sidebar is outside the topography")
        XCTAssertFalse(model.interactive, "Without the pointer the idle frame cap applies again")
    }
}
#endif
