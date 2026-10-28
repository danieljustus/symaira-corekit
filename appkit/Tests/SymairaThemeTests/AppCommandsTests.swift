#if os(macOS)
import SwiftUI
import XCTest

@testable import SymairaTheme

@MainActor
final class AppCommandsTests: XCTestCase {
    func testFirstNineDestinationsReceiveNumericShortcutsInOrder() {
        XCTAssertEqual(
            (0..<9).compactMap { SymairaCommands<String>.shortcutCharacter(at: $0) },
            Array("123456789")
        )
    }

    func testOutOfRangeDestinationsHaveNoShortcut() {
        for index in [-1, 9, 10, Int.max] {
            XCTAssertNil(SymairaCommands<String>.shortcutCharacter(at: index))
        }
    }

    func testCommandsUpdateTheSameSelectionAsWorkspaceNavigation() {
        var selection = "overview"
        let commands = SymairaCommands(
            destinations: [(value: "overview", label: "Overview"), (value: "events", label: "Events")],
            selection: Binding(get: { selection }, set: { selection = $0 })
        )
        commands.selectDestination(at: 1)
        XCTAssertEqual(selection, "events")
        commands.selectDestination(at: 0)
        XCTAssertEqual(selection, "overview")
        commands.selectDestination(at: -1)
        commands.selectDestination(at: 2)
        XCTAssertEqual(selection, "overview")
    }

    func testEmptyDestinationsDoNotChangeSelection() {
        var selection = "overview"
        let commands = SymairaCommands<String>(
            destinations: [], selection: Binding(get: { selection }, set: { selection = $0 })
        )
        commands.selectDestination(at: 0)
        XCTAssertEqual(selection, "overview")
    }

    func testSettingsSceneBuildsProductContentOnce() {
        var builds = 0
        func content() -> Text {
            builds += 1
            return Text("Product Settings")
        }
        _ = SymairaSettingsScene { content() }
        XCTAssertEqual(builds, 1)
        _ = SymairaSettingsButton()
    }
}
#endif
