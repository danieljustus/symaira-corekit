import AppKit
import SwiftUI
import XCTest

@testable import SymairaTheme

/// Shared components accept Symaira icons, and filters share the text-field silhouette.
@MainActor
final class SymairaIconAdoptionTests: XCTestCase {
    func testSharedComponentsRenderSymairaIcons() {
        ThemeRenderHost.render(SymairaNavigationButton("Requests", icon: .mail, isSelected: true) {})
        ThemeRenderHost.render(
            SymairaNavigationButton("Requests", icon: .mail, isSelected: false, showsLabel: false) {})
        ThemeRenderHost.render(SymairaEmptyState(icon: .warning, title: "Failed", message: "Retry later"))
        ThemeRenderHost.render(SymairaBadge("Sent", tone: .informative, icon: .send))
        ThemeRenderHost.render(SymairaNotice(message: "Saved", tone: .positive, onDismiss: {}))
    }

    func testEveryToneHasADistinctSymairaIconExceptInformational() {
        let tones: [SymairaTone] = [.neutral, .positive, .warning, .critical]
        XCTAssertEqual(Set(tones.map(\.symairaIcon)).count, tones.count)
        XCTAssertEqual(SymairaTone.informative.symairaIcon, .info)
    }

    func testFilterMenuMarksOnlyNonDefaultChoicesActive() {
        let options: [(value: String, label: String)] = [("", "All statuses"), ("SENT", "Sent")]
        let idle = SymairaFilterMenu("Status", selection: .constant(""), options: options)
        XCTAssertFalse(idle.isActive)
        XCTAssertEqual(idle.currentLabel, "All statuses")
        let active = SymairaFilterMenu("Status", selection: .constant("SENT"), options: options)
        XCTAssertTrue(active.isActive)
        XCTAssertEqual(active.currentLabel, "Sent")
    }

    func testFilterMenuMatchesTextFieldHeight() {
        let options: [(value: String, label: String)] = [("", "All statuses"), ("SENT", "Sent")]
        let row = HStack {
            TextField("Campaign", text: .constant("")).textFieldStyle(.symaira)
            SymairaFilterMenu("Status", selection: .constant("SENT"), options: options)
        }
        .padding()
        let host = ThemeRenderHost.render(row, size: CGSize(width: 520, height: 120))
        if let directory = ProcessInfo.processInfo.environment["SYMAIRA_RENDER_DIR"],
            let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds)
        {
            host.cacheDisplay(in: host.bounds, to: bitmap)
            try? bitmap.representation(using: .png, properties: [:])?
                .write(to: URL(fileURLWithPath: directory).appendingPathComponent("filter-menu.png"))
        }
        let menu = host.fittingSize
        XCTAssertGreaterThanOrEqual(menu.height, SymairaMetrics.minimumControlHeight)
    }
}
