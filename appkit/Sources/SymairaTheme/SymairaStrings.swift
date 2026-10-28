import Foundation

/// User-facing strings of shared SymairaTheme components, resolved from the
/// package's own `Localizable.strings` (English and German).
///
/// Lookup goes through ``SymairaThemeResources/bundle``, so a packaged app finds
/// the strings in its embedded resource bundle. The English text is the
/// fallback when a language or key is missing.
enum SymairaStrings {
    static var sidebarResizeLabel: String {
        string("sidebar.resize.label", "Resize sidebar")
    }
    static var sidebarResizeHelp: String {
        string("sidebar.resize.help", "Drag to resize or collapse the sidebar. Arrow keys adjust its width.")
    }
    static var sidebarCollapse: String { string("sidebar.toggle.collapse", "Collapse sidebar") }
    static var sidebarExpand: String { string("sidebar.toggle.expand", "Expand sidebar") }
    static var sidebarToggleHelp: String { string("sidebar.toggle.help", "Toggle sidebar (⌃⌘S)") }
    static var sidebarCompactHelp: String {
        string("sidebar.toggle.compact", "Sidebar is compact at this window width")
    }

    static func string(_ key: String, _ english: String, bundle: Bundle = SymairaThemeResources.bundle) -> String {
        bundle.localizedString(forKey: key, value: english, table: nil)
    }
}
