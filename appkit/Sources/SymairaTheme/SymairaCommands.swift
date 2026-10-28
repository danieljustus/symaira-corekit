#if os(macOS)
import SwiftUI

/// Native destination commands. Use the same ordered destinations and selection
/// as the workspace's navigation buttons. Sidebar state owns layout only;
/// product-owned selection stays outside `SymairaSidebarState`.
///
/// The first nine entries receive Command-1 through Command-9. Further entries
/// remain available in the Navigate menu without a numeric shortcut. Add
/// product-specific primary actions and refresh commands alongside this helper.
public struct SymairaCommands<Destination: Hashable>: Commands {
    private let destinations: [(value: Destination, label: String)]
    @Binding private var selection: Destination

    public init(
        destinations: [(value: Destination, label: String)],
        selection: Binding<Destination>
    ) {
        self.destinations = destinations
        _selection = selection
    }

    public var body: some Commands {
        CommandMenu("Navigate") {
            ForEach(destinations.indices, id: \.self) { index in
                destinationButton(at: index)
            }
        }
    }

    @ViewBuilder private func destinationButton(at index: Int) -> some View {
        let button = Button(destinations[index].label) {
            selectDestination(at: index)
        }
        if let character = Self.shortcutCharacter(at: index) {
            button.keyboardShortcut(KeyEquivalent(character), modifiers: .command)
        } else {
            button
        }
    }

    static func shortcutCharacter(at index: Int) -> Character? {
        guard (0..<9).contains(index) else { return nil }
        return Character(String(index + 1))
    }

    func selectDestination(at index: Int) {
        guard destinations.indices.contains(index) else { return }
        selection = destinations[index].value
    }
}

/// Registers the native Settings scene, including the standard Command-comma
/// menu item. The product owns the content, appearance binding and persistence.
public struct SymairaSettingsScene<Content: View>: Scene {
    private let content: Content

    public init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    public var body: some Scene {
        Settings { content }
    }
}
#endif
