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
