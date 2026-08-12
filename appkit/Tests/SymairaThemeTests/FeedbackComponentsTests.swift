import XCTest
import SwiftUI
@testable import SymairaTheme

@MainActor
final class FeedbackComponentsTests: XCTestCase {

    // MARK: - Tones

    func testToneForegroundsDifferBetweenAppearances() {
        for tone in [SymairaTone.neutral, .positive, .warning, .critical, .informative] {
            XCTAssertNotEqual(
                tone.foreground(for: .dark),
                tone.foreground(for: .light),
                "\(tone) must resolve differently in dark and light appearances"
            )
        }
    }

    func testToneSystemImagesAreDistinct() {
        let tones: [SymairaTone] = [.neutral, .positive, .warning, .critical, .informative]
        XCTAssertEqual(Set(tones.map(\.systemImage)).count, tones.count)
    }

    // MARK: - Badge

    func testBadgeEvaluatesBodyWithAndWithoutIcon() {
        XCTAssertNotNil(SymairaBadge("Beta").body)
        XCTAssertNotNil(SymairaBadge("Beta", tone: .positive).body)
        XCTAssertNotNil(SymairaBadge("Beta", systemImage: "flame").body)
    }

    func testBadgeRendersAllTonesWithAndWithoutIcon() {
        for tone in [SymairaTone.neutral, .positive, .warning, .critical, .informative] {
            ThemeRenderHost.render(SymairaBadge("Tag", tone: tone))
            ThemeRenderHost.render(SymairaBadge("Tag", tone: tone, systemImage: "circle"))
        }
    }

    // MARK: - Notice

    func testNoticeEvaluatesBodyVariants() {
        XCTAssertNotNil(SymairaNotice(message: "Plain message").body)
        XCTAssertNotNil(SymairaNotice(title: "Heads up", message: "Details", tone: .warning).body)
        XCTAssertNotNil(SymairaNotice(message: "Dismissable", onDismiss: {}).body)
        XCTAssertNotNil(SymairaNotice(title: "All", message: "Options", tone: .critical, onDismiss: {}).body)
    }

    func testNoticeRendersAllTonesWithAndWithoutDismiss() {
        for tone in [SymairaTone.neutral, .positive, .warning, .critical, .informative] {
            ThemeRenderHost.render(SymairaNotice(title: "Title", message: "Message", tone: tone))
            ThemeRenderHost.render(SymairaNotice(message: "Message", tone: tone, onDismiss: {}))
        }
    }

    /// A message long enough to wrap must not blow up the layout of a
    /// surrounding `NavigationSplitView`. Laying the message out with
    /// `.fixedSize(horizontal: false, vertical: true)` next to a `Spacer` gave
    /// the split view an unbounded height, which pushed every column off-screen
    /// and left the window blank (#68).
    func testNoticeWithWrappingMessageKeepsSplitViewWithinItsHost() {
        let longMessage = String(repeating: "Failed to load the profile index. ", count: 8)
        let size = CGSize(width: 720, height: 480)
        let hosting = ThemeRenderHost.render(
            NavigationSplitView {
                List { Text("Sidebar") }
            } detail: {
                VStack(alignment: .leading) {
                    SymairaNotice(title: "Error", message: longMessage, tone: .critical)
                    Spacer()
                }
                .padding()
            },
            size: size
        )

        let splitViews = Self.descendants(of: hosting).compactMap { $0 as? NSSplitView }
        XCTAssertFalse(splitViews.isEmpty, "expected NavigationSplitView to host an NSSplitView")
        for splitView in splitViews {
            XCTAssertLessThanOrEqual(
                splitView.frame.height,
                size.height,
                "a wrapping notice message must not stretch the split view beyond its host"
            )
        }
    }

    private static func descendants(of view: NSView) -> [NSView] {
        view.subviews + view.subviews.flatMap(descendants(of:))
    }

    // MARK: - Empty state

    func testEmptyStateEvaluatesBodyWithAndWithoutActions() {
        XCTAssertNotNil(
            SymairaEmptyState(systemImage: "tray", title: "No items", message: "Add one.").body
        )
        XCTAssertNotNil(
            SymairaEmptyState(systemImage: "tray", title: "No items", message: "Add one.") {
                Button("Add") {}
            }.body
        )
    }

    func testEmptyStateRendersWithAndWithoutActions() {
        ThemeRenderHost.render(
            SymairaEmptyState(systemImage: "tray", title: "No items", message: "Add your first item.") {
                Button("Add Item") {}
                    .symairaButtonStyle(.primary)
            }
        )
        ThemeRenderHost.render(
            SymairaEmptyState(systemImage: "tray", title: "No items", message: "Add your first item.")
        )
    }

    // MARK: - Loading state

    func testLoadingStateEvaluatesBodyAndRenders() {
        XCTAssertNotNil(SymairaLoadingState("Indexing…").body)
        ThemeRenderHost.render(SymairaLoadingState("Indexing…"))
    }
}
