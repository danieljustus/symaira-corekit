import SwiftUI

#if os(macOS)
import AppKit
#endif

/// Shared appearance vocabulary. Hosts own persistence keys and preview isolation.
public enum SymairaAppearance: String, CaseIterable, Sendable {
    case system, light, dark

    public var title: String {
        switch self {
        case .system: "System"
        case .light: "Light"
        case .dark: "Dark"
        }
    }

    /// Use with preferredColorScheme on iOS. Nil follows system changes live.
    public var colorScheme: ColorScheme? {
        switch self {
        case .system: nil
        case .light: .light
        case .dark: .dark
        }
    }

    #if os(macOS)
    @MainActor public var nativeAppearance: NSAppearance? {
        switch self {
        case .system: nil
        case .light: NSAppearance(named: .aqua)
        case .dark: NSAppearance(named: .darkAqua)
        }
    }

    /// Apply to every existing/new native window, popover and control. System
    /// clears the override; it must not freeze a snapshot of the current mode.
    @MainActor public func apply() { NSApplication.shared.appearance = nativeAppearance }
    #endif
}

/// One click opens the host's settings window. No intermediate toolbar menu.
public struct SymairaSettingsButton: View {
    private let openSettings: () -> Void

    public init(openSettings: @escaping () -> Void) {
        self.openSettings = openSettings
    }

    public var body: some View {
        Button(action: openSettings) {
            Label("Settings", systemImage: "gearshape")
        }
        .labelStyle(.iconOnly)
        .accessibilityLabel("Settings")
        .accessibilityIdentifier("symaira-settings-button")
        .help("Settings")
    }
}

/// Source-compatible entry for existing consumers; the gear now opens settings directly.
@available(*, deprecated, message: "Use SymairaSettingsButton and place SymairaAppearancePicker in settings.")
public struct SymairaSettingsMenu: View {
    private let openSettings: () -> Void

    public init(selection _: Binding<SymairaAppearance>, openSettings: @escaping () -> Void) {
        self.openSettings = openSettings
    }

    public var body: some View { SymairaSettingsButton(openSettings: openSettings) }
}

/// Shared appearance control for a settings form. The host retains its preference key.
public struct SymairaAppearancePicker: View {
    @Binding private var selection: SymairaAppearance

    public init(selection: Binding<SymairaAppearance>) { _selection = selection }

    static let options = SymairaAppearance.allCases.map { (value: $0, label: $0.title) }

    public var body: some View {
        // Shared segments, not the native segmented picker with its system accent.
        SymairaSegmentedControl(
            "Appearance", selection: $selection,
            options: Self.options
        )
        .frame(maxWidth: 360)
        .accessibilityIdentifier("symaira-appearance-picker")
    }
}

public struct SymairaAppearanceMenu: View {
    @Binding private var selection: SymairaAppearance

    public init(selection: Binding<SymairaAppearance>) { _selection = selection }

    public var body: some View {
        Menu {
            Picker("Appearance", selection: $selection) {
                ForEach(SymairaAppearance.allCases, id: \.self) { option in
                    Text(option.title).tag(option)
                }
            }
            .pickerStyle(.inline)
        } label: {
            Label("Appearance", systemImage: "circle.lefthalf.filled")
                .labelStyle(.titleAndIcon)
        }
        .help("Appearance: System, Light or Dark")
    }
}
