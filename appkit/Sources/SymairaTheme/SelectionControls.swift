import SwiftUI

// Liquid Topography selection controls, as approved in the Cockpit design pilot.
// Selection is a filled `selected` surface plus bold text, never a border or
// shadow: champagne in dark appearance, ink in light appearance (decision A).

// MARK: - Card

/// Opaque content card: `surface` fill, 1 px `line` outline, 14 pt radius.
public struct SymairaCardModifier: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme
    private let padding: CGFloat

    public init(padding: CGFloat = SymairaSpacing.large) {
        self.padding = padding
    }

    public func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: SymairaTokens.Radius.lg, style: .continuous)
        content
            .padding(padding)
            .background(SymairaTheme.surfaceOpaque(for: colorScheme), in: shape)
            .overlay(shape.stroke(SymairaTheme.line(for: colorScheme), lineWidth: 1))
    }
}

extension View {
    /// Opaque Liquid Topography card. Use for every content surface that carries text.
    public func symairaCard(padding: CGFloat = SymairaSpacing.large) -> some View {
        modifier(SymairaCardModifier(padding: padding))
    }
}

// MARK: - Segmented control

/// Single-choice segmented control. Replaces `Picker(.segmented)`, whose native
/// selection on light surfaces is too faint for the Symaira palette.
///
/// Each segment is a button with the `isSelected` accessibility trait, so
/// VoiceOver announces the choice and keyboard focus moves between segments.
public struct SymairaSegmentedControl<Value: Hashable>: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled

    private let title: String
    @Binding private var selection: Value
    private let options: [(value: Value, label: String)]

    /// - Parameter title: Accessible name of the whole group, for example "Fan profile".
    public init(_ title: String, selection: Binding<Value>, options: [(value: Value, label: String)]) {
        self.title = title
        _selection = selection
        self.options = options
    }

    public var body: some View {
        HStack(spacing: SymairaSpacing.xSmall) {
            ForEach(options.indices, id: \.self) { index in
                segment(options[index])
            }
        }
        .padding(SymairaSpacing.xSmall)
        .background(
            SymairaTheme.surfaceRaised(for: colorScheme),
            in: RoundedRectangle(cornerRadius: SymairaTokens.Radius.lg, style: .continuous)
        )
        .opacity(isEnabled ? 1 : 0.55)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(title)
    }

    private func segment(_ option: (value: Value, label: String)) -> some View {
        SymairaSegmentButton(
            label: option.label,
            isSelected: option.value == selection,
            colorScheme: colorScheme,
            action: { selection = option.value }
        )
    }
}

private struct SymairaSegmentButton: View {
    let label: String
    let isSelected: Bool
    let colorScheme: ColorScheme
    let action: () -> Void
    @FocusState private var isFocused: Bool

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(isSelected ? SymairaTypography.bodyEmphasized : SymairaTypography.bodyMedium)
                .lineLimit(1)
                .minimumScaleFactor(0.85)
                .frame(maxWidth: .infinity, minHeight: SymairaMetrics.minimumControlHeight - 2)
                .foregroundStyle(
                    isSelected
                        ? SymairaTheme.onSelected(for: colorScheme)
                        : SymairaTheme.foregroundSecondary(for: colorScheme)
                )
                .background {
                    if isSelected {
                        RoundedRectangle(cornerRadius: SymairaTokens.Radius.md, style: .continuous)
                            .fill(SymairaTheme.selected(for: colorScheme))
                    }
                }
                .contentShape(RoundedRectangle(cornerRadius: SymairaTokens.Radius.md, style: .continuous))
        }
        .buttonStyle(.plain)
        .focused($isFocused)
        .symairaKeyboardFocusRing(
            RoundedRectangle(cornerRadius: SymairaTokens.Radius.md, style: .continuous),
            isFocused: isFocused
        )
        .accessibilityAddTraits(isSelected ? [.isSelected] : [])
    }
}

private struct SymairaKeyboardFocusRing<S: Shape>: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme

    let shape: S
    let isFocused: Bool

    func body(content: Content) -> some View {
        content.overlay {
            if isFocused {
                shape
                    .stroke(SymairaTheme.focus(for: colorScheme), lineWidth: 2)
                    .padding(-3)
            }
        }
    }
}

extension View {
    fileprivate func symairaKeyboardFocusRing<S: Shape>(_ shape: S, isFocused: Bool) -> some View {
        modifier(SymairaKeyboardFocusRing(shape: shape, isFocused: isFocused))
    }
}

// MARK: - Switch

/// Switch with the approved silhouette: 56 × 32 pt track, 24 pt knob. On uses
/// the `selected` role. Keeps native toggle semantics for accessibility.
public struct SymairaSwitchToggleStyle: ToggleStyle {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init() {}

    public func makeBody(configuration: Configuration) -> some View {
        // No spacer: the switch sits next to its label like the native style, so it
        // also fits rows that hide the label or already align it themselves.
        HStack(spacing: SymairaSpacing.medium) {
            configuration.label
            // A button keeps the switch keyboard-operable (Space) on macOS.
            SymairaSwitchButton(isOn: configuration.$isOn)
        }
        .opacity(isEnabled ? 1 : 0.55)
        .accessibilityRepresentation {
            Toggle(isOn: configuration.$isOn) { configuration.label }
        }
    }
}

private struct SymairaSwitchButton: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Binding private var isOn: Bool
    @FocusState private var isFocused: Bool

    init(isOn: Binding<Bool>) {
        _isOn = isOn
    }

    var body: some View {
        Button {
            isOn.toggle()
        } label: {
            track
        }
        .buttonStyle(.plain)
        .focused($isFocused)
        .symairaKeyboardFocusRing(Capsule(), isFocused: isFocused)
    }

    private var track: some View {
        ZStack(alignment: isOn ? .trailing : .leading) {
            Capsule().fill(isOn ? SymairaTheme.selected(for: colorScheme) : offTrack)
            Circle()
                .fill(isOn ? SymairaTheme.onSelected(for: colorScheme) : offKnob)
                .frame(width: 24, height: 24)
                .padding(4)
        }
        .frame(width: 56, height: 32)
        .contentShape(Capsule())
        .animation(reduceMotion ? nil : .easeOut(duration: 0.16), value: isOn)
    }

    // Off: dark mode keeps a neutral track with a canvas knob; light mode uses the
    // line track with an ink knob so the knob position stays readable (13.9:1).
    private var offTrack: Color {
        colorScheme == .dark ? SymairaTheme.foregroundMuted(for: .dark) : SymairaTheme.line(for: .light)
    }

    private var offKnob: Color {
        colorScheme == .dark ? SymairaTheme.backgroundPrimary(for: .dark) : SymairaTheme.foregroundPrimary(for: .light)
    }
}

extension ToggleStyle where Self == SymairaSwitchToggleStyle {
    public static var symairaSwitch: SymairaSwitchToggleStyle { SymairaSwitchToggleStyle() }
}

// MARK: - Lock label

/// "Locked" marker next to a control that cannot be used right now (missing
/// sensor data, no permission). Opacity alone is not a disabled cue.
public struct SymairaLockedLabel: View {
    @Environment(\.colorScheme) private var colorScheme
    private let text: String

    public init(_ text: String = "Gesperrt") {
        self.text = text
    }

    public var body: some View {
        Label(text, systemImage: "lock.fill")
            .labelStyle(.titleAndIcon)
            .font(SymairaTypography.caption)
            .foregroundStyle(SymairaTheme.foregroundMuted(for: colorScheme))
    }
}
