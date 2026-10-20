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

/// The enclosing control, not the icon's own frame, drives icon motion.
@MainActor
final class SymairaIconInteractionTests: XCTestCase {
    final class Recorder { var values: [SymairaIconInteraction?] = [] }

    struct Probe: View {
        let recorder: Recorder
        @Environment(\.symairaIconInteraction) private var interaction
        var body: some View {
            recorder.values.append(interaction)
            return Color.clear.frame(width: 10, height: 10)
        }
    }

    @Observable final class Press { var isPressed = false }

    struct Hosted: View {
        let press: Press
        let recorder: Recorder
        var body: some View {
            SymairaIconHost(isPressed: press.isPressed) { Probe(recorder: recorder) }
        }
    }

    func testHostCountsOnlyPressStartsOfItsOwnControl() async throws {
        let recorder = Recorder()
        let press = Press()
        let host = ThemeRenderHost.render(Hosted(press: press, recorder: recorder))
        func settle() async throws {
            host.layoutSubtreeIfNeeded()
            try await Task.sleep(for: .milliseconds(50))
            host.layoutSubtreeIfNeeded()
        }
        try await settle()
        XCTAssertEqual(recorder.values.last??.presses, 0)
        press.isPressed = true
        try await settle()
        press.isPressed = false
        try await settle()
        XCTAssertEqual(recorder.values.last??.presses, 1, "One press plays the full motion once")

        let standalone = Recorder()
        ThemeRenderHost.render(Probe(recorder: standalone))
        XCTAssertNil(standalone.values.last ?? nil, "Icons outside a Symaira control keep their own hover")
    }
}
