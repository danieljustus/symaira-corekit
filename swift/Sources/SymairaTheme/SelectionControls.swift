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
            // tvOS: a card is one stop for the remote; its button at the right end is reachable
            // from a control above it on the left.
            .symairaFocusSection(fillWidth: false)
    }
}

extension View {
    /// Opaque Liquid Topography card. Use for every content surface that carries text.
    public func symairaCard(padding: CGFloat = SymairaSpacing.large) -> some View {
        modifier(SymairaCardModifier(padding: padding))
    }
}

// MARK: - Segmented control

/// Single-choice segmented control (UI catalog E07, revised 2026-11-26): the native
/// segmented picker with the Symaira selection tint. The system draws the rail and
/// handles press, drag, keyboard focus and VoiceOver. In the `page` tier it is
/// extra-large (36 pt, `SymairaMetrics.segmentedControlHeight`) wherever it sits; in the
/// `workbench` tier it takes the region's control size like the controls next to it.
/// `.fixedSize()` keeps its natural width, so labels never truncate and the control does
/// not stretch inside forms or toolbars.
public struct SymairaSegmentedControl<Value: Hashable>: View {
    @Environment(\.symairaControlTier) private var tier
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
        Picker(title, selection: $selection) {
            ForEach(options.indices, id: \.self) { index in
                Text(options[index].label).tag(options[index].value)
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .tint(SymairaTokens.selected)
        #if !os(tvOS)
        .modifier(SymairaPageTierControlSize(isPage: tier == .page))
        #endif
        .fixedSize()
    }
}

#if !os(tvOS)
/// Extra-large in the `page` tier; otherwise the inherited control size stays.
private struct SymairaPageTierControlSize: ViewModifier {
    let isPage: Bool

    @ViewBuilder
    func body(content: Content) -> some View {
        if isPage { content.controlSize(.extraLarge) } else { content }
    }
}
#endif

/// Filter dropdown with the text-field silhouette: same height, fill, radius and
/// border as `SymairaTextFieldStyle`, so a row of search fields and filters reads
/// as one control set. The native popup button brings its own chrome instead.
/// The first option is the unfiltered default; any other choice is active and
/// carries the `selected` border, like every other active control.
@available(*, deprecated, message: "Use Picker(...).pickerStyle(.menu), E06/E09 (UI catalog 2026-11-25).")
public struct SymairaFilterMenu<Value: Hashable>: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.isEnabled) private var isEnabled

    private let title: String
    @Binding private var selection: Value
    private let options: [(value: Value, label: String)]

    /// - Parameters:
    ///   - title: Accessible name, for example "Status".
    ///   - options: First entry is the unfiltered default ("All statuses").
    public init(_ title: String, selection: Binding<Value>, options: [(value: Value, label: String)]) {
        self.title = title
        _selection = selection
        self.options = options
    }

    var isActive: Bool { options.first.map { $0.value != selection } ?? false }
    var currentLabel: String { options.first { $0.value == selection }?.label ?? title }

    public var body: some View {
        let shape = RoundedRectangle(cornerRadius: SymairaRadius.control, style: .continuous)
        Menu {
            Picker(title, selection: $selection) {
                ForEach(options.indices, id: \.self) { index in
                    Text(options[index].label).tag(options[index].value)
                }
            }
            .pickerStyle(.inline)
            .labelsHidden()
        } label: {
            SymairaIconHost(isPressed: false) { menuLabel(shape) }
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .opacity(isEnabled ? 1 : 0.55)
        .accessibilityLabel(title)
        .accessibilityValue(currentLabel)
    }

    private func menuLabel(_ shape: RoundedRectangle) -> some View {
        HStack(spacing: SymairaSpacing.small) {
            Text(currentLabel)
                .font(isActive ? SymairaTypography.bodyEmphasized : SymairaTypography.body)
                .lineLimit(1)
            Spacer(minLength: 0)
            SymairaIconView(.expand, size: 16)
                .foregroundStyle(SymairaTheme.foregroundMuted(for: colorScheme))
        }
        .foregroundStyle(SymairaTheme.foregroundPrimary(for: colorScheme))
        .padding(.horizontal, SymairaSpacing.medium)
        .frame(minHeight: SymairaMetrics.minimumControlHeight)
        .background(shape.fill(SymairaTheme.surfaceRaised(for: colorScheme)))
        .overlay(shape.stroke(border, lineWidth: isActive ? 1.5 : (contrast == .increased ? 1.5 : 1)))
        .contentShape(shape)
    }

    private var border: Color {
        if isActive { return SymairaTheme.selected(for: colorScheme) }
        if contrast == .increased { return SymairaTheme.foregroundMuted(for: colorScheme) }
        return SymairaTheme.line(for: colorScheme)
    }
}

/// Reports one text line of height and centres its child on it. A macOS form row
/// aligns label and control at the top, so a control taller than a line (a 36 pt
/// segmented control, a 36 pt page action) would hang below the row title.
struct SymairaFormRowControlLayout: Layout {
    static let lineHeight: CGFloat = 17 * SymairaMetrics.platformScale

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let size = subviews.first?.sizeThatFits(ProposedViewSize(width: proposal.width, height: nil)) ?? .zero
        return CGSize(width: size.width, height: min(size.height, Self.lineHeight))
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard let child = subviews.first else { return }
        let size = child.sizeThatFits(ProposedViewSize(width: bounds.width, height: nil))
        child.place(at: CGPoint(x: bounds.midX, y: bounds.midY), anchor: .center, proposal: ProposedViewSize(size))
    }
}

extension View {
    /// Centres a control that is taller than one text line on the first line of a
    /// form row title (`LabeledContent` in a grouped `Form`, GUIDELINES FORM-10).
    /// The control keeps its full size and hit area; only the row sees one line.
    public func symairaFormRowControl() -> some View {
        SymairaFormRowControlLayout { self }
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
/// the `selected` role. Keeps native toggle semantics for accessibility. On
/// macOS 14, iOS 17 and tvOS 17, uses the native toggle to honor hidden labels.
@available(
    *, deprecated, message: "Use .toggleStyle(.switch).tint(SymairaTokens.selected), E08 (UI catalog 2026-11-25)."
)
public struct SymairaSwitchToggleStyle: ToggleStyle {
    public init() {}

    public func makeBody(configuration: Configuration) -> some View {
        if #available(macOS 15, iOS 18, tvOS 18, *) {
            SymairaSwitchBody(configuration: configuration)
        } else {
            // Earlier SwiftUI does not expose labelsVisibility to custom styles.
            #if os(tvOS)
            // tvOS 17 has no switch style; its native toggle is focusable.
            Toggle(isOn: configuration.$isOn) { configuration.label }
            #else
            Toggle(isOn: configuration.$isOn) { configuration.label }
                .toggleStyle(.switch)
            #endif
        }
    }
}

@available(macOS 15, iOS 18, tvOS 18, *)
struct SymairaSwitchBody: View {
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.labelsVisibility) private var labelsVisibility
    let configuration: ToggleStyleConfiguration

    static func showsLabel(_ visibility: Visibility) -> Bool {
        visibility != .hidden
    }

    var body: some View {
        HStack(spacing: SymairaSpacing.medium) {
            if Self.showsLabel(labelsVisibility) {
                configuration.label
            }
            SymairaSwitchButton(isOn: configuration.$isOn)
        }
        .opacity(isEnabled ? 1 : 0.55)
        .accessibilityRepresentation {
            Toggle(isOn: configuration.$isOn) { configuration.label }
                .toggleStyle(.switch)
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
                .frame(width: 24 * SymairaMetrics.platformScale, height: 24 * SymairaMetrics.platformScale)
                .padding(4 * SymairaMetrics.platformScale)
        }
        .frame(width: 56 * SymairaMetrics.platformScale, height: 32 * SymairaMetrics.platformScale)
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

@available(
    *, deprecated, message: "Use .toggleStyle(.switch).tint(SymairaTokens.selected), E08 (UI catalog 2026-11-25)."
)
extension ToggleStyle where Self == SymairaSwitchToggleStyle {
    @available(
        *, deprecated, message: "Use .toggleStyle(.switch).tint(SymairaTokens.selected), E08 (UI catalog 2026-11-25)."
    )
    public static var symairaSwitch: SymairaSwitchToggleStyle { SymairaSwitchToggleStyle() }
}

// MARK: - Lock label

/// "Locked" marker (localized) next to a control that cannot be used right now (missing
/// sensor data, no permission). Opacity alone is not a disabled cue.
public struct SymairaLockedLabel: View {
    let text: String

    public init(_ text: String = SymairaStrings.locked) {
        self.text = text
    }

    public var body: some View {
        Label {
            Text(text)
        } icon: {
            SymairaIconView(.lock)
        }
        .labelStyle(.titleAndIcon)
        .symairaText(.caption)
    }
}
