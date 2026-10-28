import SwiftUI
import XCTest

@testable import SymairaTheme

@MainActor
final class PageScaffoldTests: XCTestCase {
    func testLoadStatePreservesValuesAndFailures() {
        XCTAssertEqual(SymairaPageLoadState<Int>.idle, .idle)
        XCTAssertNotEqual(SymairaPageLoadState<Int>.idle, .loading)
        XCTAssertEqual(SymairaPageLoadState.loaded([1, 2]), .loaded([1, 2]))
        XCTAssertEqual(SymairaPageLoadState<Int>.failed("Reconnect and retry."), .failed("Reconnect and retry."))
        XCTAssertNotEqual(SymairaPageLoadState<Int>.failed("Offline"), .loaded(0))
    }

    func testAllPlaceholderStatesRenderAtOneFixedHeight() throws {
        for scheme in [ColorScheme.light, .dark] {
            for state in [SymairaPageLoadState<Int>.idle, .loading, .failed("You are offline. Reconnect and retry.")] {
                let view = SymairaPageState(
                    state: state, loading: "Loading requests…", retry: {}, loaded: { _ in Text("Loaded") })
                XCTAssertEqual(
                    try height(view.environment(\.colorScheme, scheme)), SymairaPageLayout.stateHeight, accuracy: 1)
            }
            XCTAssertEqual(
                try height(
                    SymairaPageEmpty(icon: .info, title: "No Requests", message: "Create your first request.")
                        .environment(\.colorScheme, scheme)),
                SymairaPageLayout.stateHeight, accuracy: 1)
            XCTAssertEqual(
                try height(
                    SymairaPageEmpty(icon: .info, title: "No Requests", message: "Create your first request.") {
                        Button("Create Request") {}.symairaButtonStyle(.primary)
                    }.environment(\.colorScheme, scheme)),
                SymairaPageLayout.stateHeight, accuracy: 1)
        }
    }

    func testLoadedContentDoesNotReservePlaceholderHeight() throws {
        let view = SymairaPageState(
            state: .loaded(42), loading: "Loading requests…", retry: {},
            loaded: { value in
                Text("\(value)").frame(height: 80)
            })
        XCTAssertEqual(try height(view), 80, accuracy: 1)
    }

    func testPageAndSheetVariantsRender() {
        ThemeRenderHost.render(SymairaPage(title: "Requests") { Text("Content").symairaCard() })
        ThemeRenderHost.render(
            SymairaPage(title: "Requests", subtitle: "Manage your requests", scrolls: false, maxWidth: 1008) {
                Button("Refresh") {}.symairaButtonStyle(.secondary)
            } content: {
                Text("Self-scrolling table belongs here")
            })
        ThemeRenderHost.render(
            SymairaSheetScaffold(title: "Request Details", dismissTitle: "Close", dismiss: {}) { Text("Details") })
        ThemeRenderHost.render(
            SymairaSheetScaffold(
                title: "Create Request", dismiss: {}, primaryTitle: "Create Request", primaryDisabled: true, primary: {}
            ) {
                Text("Product-owned form")
            })
    }

    func testGeometryUsesSharedActionBudget() {
        XCTAssertEqual(SymairaPageLayout.toolbarHeight, 44)
        XCTAssertGreaterThanOrEqual(SymairaPageLayout.toolbarHeight, SymairaMetrics.contentActionHeight)
        XCTAssertEqual(SymairaMetrics.contentActionHorizontalPadding, 20)
    }

    private func height(_ view: some View) throws -> CGFloat {
        let renderer = ImageRenderer(content: view)
        renderer.proposedSize = ProposedViewSize(width: 600, height: nil)
        return try XCTUnwrap(renderer.nsImage).size.height
    }
}
