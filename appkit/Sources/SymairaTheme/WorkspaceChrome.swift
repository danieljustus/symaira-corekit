import SwiftUI

#if os(macOS)
/// The approved workspace toolbar. Products provide state and the settings
/// destination, never a second placement or button-style implementation.
public struct SymairaWorkspaceToolbar: ToolbarContent {
    @Binding private var sidebar: SymairaSidebarState
    private let openSettings: () -> Void

    public init(
        sidebar: Binding<SymairaSidebarState>,
        openSettings: @escaping () -> Void
    ) {
        _sidebar = sidebar
        self.openSettings = openSettings
    }

    public var body: some ToolbarContent {
        ToolbarItem(placement: .navigation) {
            SymairaSidebarToggle(sidebar: $sidebar)
                .accessibilityIdentifier("symaira-sidebar-toggle")
        }
        ToolbarItem(placement: .primaryAction) {
            SymairaSettingsButton(openSettings: openSettings)
        }
    }
}

extension Scene {
    /// Match the native Cockpit window header. Hidden-title-bar scenes collapse
    /// the system chrome differently even when they host the same toolbar items.
    public func symairaWorkspaceWindow() -> some Scene {
        windowStyle(.titleBar)
            .windowToolbarStyle(.unified)
    }
}
#endif
