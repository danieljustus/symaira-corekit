import Foundation

/// User-facing strings of shared SymairaTheme components, resolved from the
/// package's own `Localizable.strings` (English and German).
///
/// Lookup goes through ``SymairaThemeResources/bundle``, so a packaged app finds
/// the strings in its embedded resource bundle. The English text is the
/// fallback when a language or key is missing.
@usableFromInline
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

    static var close: String { string("common.close", "Close") }
    @usableFromInline static var cancel: String { string("common.cancel", "Cancel") }
    static var dismiss: String { string("common.dismiss", "Dismiss") }
    static var retry: String { string("common.retry", "Retry") }
    @usableFromInline static var locked: String { string("common.locked", "Locked") }
    static var settings: String { string("settings.title", "Settings") }
    static var appearance: String { string("appearance.title", "Appearance") }
    static var appearanceHelp: String { string("appearance.help", "Appearance: System, Light or Dark") }
    static var appearanceSystem: String { string("appearance.system", "System") }
    static var appearanceLight: String { string("appearance.light", "Light") }
    static var appearanceDark: String { string("appearance.dark", "Dark") }
    static var navigateMenu: String { string("navigate.menu", "Navigate") }
    static var onboardingBack: String { string("onboarding.back", "Back") }
    static var onboardingSkip: String { string("onboarding.skip", "Skip") }
    static var onboardingNext: String { string("onboarding.next", "Next") }
    static var onboardingFinish: String { string("onboarding.finish", "Finish") }
    static func onboardingStep(_ position: Int, of count: Int) -> String {
        String(format: string("onboarding.step", "Step %1$lld of %2$lld"), position, count)
    }

    static func string(_ key: String, _ english: String, bundle: Bundle = SymairaThemeResources.bundle) -> String {
        bundle.localizedString(forKey: key, value: english, table: nil)
    }
}
