import SwiftUI
import XCTest

@testable import SymairaTheme

#if os(macOS)
import AppKit

@MainActor
final class SettingsMenuTests: XCTestCase {
    func testGearOpensSettingsWithOneActionAndNoSubmenu() async throws {
        guard #available(macOS 14.4, *) else { throw XCTSkip("NSHostingMenu requires macOS 14.4") }
        _ = NSApplication.shared
        var settingsOpened = 0
        let root = SymairaSettingsButton { settingsOpened += 1 }
        // A native menu host executes the production button action in-process.
        // It must expose one action, not appearance choices or another submenu.
        let menu = NSHostingMenu(rootView: root)
        menu.update()
        try await Task.sleep(for: .milliseconds(150))
        XCTAssertEqual(menu.items.count, 1)
        XCTAssertNil(try XCTUnwrap(menu.items.first).submenu)
        menu.performActionForItem(at: 0)
        XCTAssertEqual(settingsOpened, 1)
    }

    func testAppearancePickerUsesSharedSegmentsInsteadOfNativeControl() async throws {
        _ = NSApplication.shared
        XCTAssertEqual(SymairaAppearancePicker.options.map(\.value), SymairaAppearance.allCases)
        XCTAssertEqual(SymairaAppearancePicker.options.map(\.label), SymairaAppearance.allCases.map(\.title))
        let host = NSHostingView(rootView: SymairaAppearancePicker(selection: .constant(.system)))
        host.frame = NSRect(x: 0, y: 0, width: 360, height: 52)
        host.layoutSubtreeIfNeeded()
        try await Task.sleep(for: .milliseconds(150))
        func controls(_ view: NSView) -> [NSSegmentedControl] {
            (view as? NSSegmentedControl).map { [$0] } ?? view.subviews.flatMap(controls)
        }
        XCTAssertTrue(controls(host).isEmpty, "The native segmented control brings the system accent colour")
    }
}
#endif
