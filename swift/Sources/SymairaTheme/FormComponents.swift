import SwiftUI

// MARK: - Text fields

/// Opaque Liquid Topography input surface and appearance-aware focus ring.
///
/// Six of the client apps style their text fields inline today, each with its own
/// padding and border. This is the one place that decision should live.
public struct SymairaTextFieldStyle: TextFieldStyle {
    private let focusOverride: Bool?

    /// Use the native field's keyboard focus to drive the focus ring.
    public init() {
        focusOverride = nil
    }

    /// Override the focus ring, for example with the host's `@FocusState`.
    public init(isFocused: Bool) {
        focusOverride = isFocused
    }

    public func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .textFieldStyle(.plain)
            .modifier(SymairaTextFieldChrome(focusOverride: focusOverride))
    }
}

private struct SymairaTextFieldChrome: ViewModifier {
    @Environment(\.symairaControlTier) private var tier
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.isEnabled) private var isEnabled
    @FocusState private var hasKeyboardFocus: Bool

    let focusOverride: Bool?

    nonisolated init(focusOverride: Bool?) {
        self.focusOverride = focusOverride
    }

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: SymairaRadius.control, style: .continuous)
        Group {
            if focusOverride != nil {
                content
            } else {
                content.focused($hasKeyboardFocus)
            }
        }
        .font(SymairaTypography.body)
        .padding(.horizontal, SymairaSpacing.medium)
        // A field lines up with the controls of its tier (CTRL-1): the native `.large` controls in
        // the workbench, the 36 pt page actions in a page toolbar.
        .padding(.vertical, tier == .workbench ? SymairaSpacing.xSmall : SymairaSpacing.small)
        .frame(
            minHeight: tier == .workbench ? SymairaMetrics.workbenchControlHeight : SymairaMetrics.contentActionHeight
        )
        .background(shape.fill(fill))
        .overlay(shape.stroke(border, lineWidth: borderWidth))
        .opacity(isEnabled ? 1 : 0.55)
    }

    private var isFocused: Bool { focusOverride ?? hasKeyboardFocus }

    private var fill: Color {
        SymairaTheme.surfaceRaised(for: colorScheme)
    }

    private var border: Color {
        if isFocused {
            return SymairaTokens.focus
        }
        if contrast == .increased {
            return SymairaTheme.foregroundMuted(for: colorScheme)
        }
        // A control boundary needs 3:1 against its fill and the surface below (COLOR-4).
        return SymairaTheme.controlOutline(for: colorScheme)
    }

    private var borderWidth: CGFloat {
        if isFocused { return 2 }
        return contrast == .increased ? 1.5 : 1
    }
}

extension TextFieldStyle where Self == SymairaTextFieldStyle {
    /// Symaira text field chrome that tracks keyboard focus automatically.
    public static var symaira: SymairaTextFieldStyle { SymairaTextFieldStyle() }

    /// Symaira text field chrome with an explicit focus state.
    public static func symaira(isFocused: Bool) -> SymairaTextFieldStyle {
        SymairaTextFieldStyle(isFocused: isFocused)
    }
}

/// An inline text field with Symaira chrome and a contrast-safe prompt.
public struct SymairaTextField: View {
    private let title: String
    @Binding private var text: String
    private let prompt: String

    public init(_ title: String, text: Binding<String>, prompt: String) {
        self.title = title
        self._text = text
        self.prompt = prompt
    }

    public var body: some View {
        TextField(title, text: $text, prompt: Text(prompt).foregroundColor(SymairaTokens.ink3))
            .textFieldStyle(.symaira)
    }
}

// MARK: - Section scaffold

/// A titled group of rows on an opaque shared content card.
///
/// Five client apps build their own settings scaffold. The differences between
/// them are accidental — heading size, gap above the card, whether a footer is
/// muted — and they are exactly what makes the apps look unrelated.
@available(
    *, deprecated,
    message: "Use Form { Section { ... } }.formStyle(.grouped) with native fields, E17 (UI catalog 2026-11-25)."
)
public struct SymairaFormSection<Content: View>: View {
    private let title: String?
    private let footer: String?
    private let content: Content

    public init(
        _ title: String? = nil,
        footer: String? = nil,
        @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.footer = footer
        self.content = content()
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: SymairaSpacing.small) {
            if let title {
                Text(title)
                    .symairaText(.sectionLabel)
                    .accessibilityAddTraits(.isHeader)
                    .topoProtected()
            }

            VStack(alignment: .leading, spacing: 0) {
                content
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .symairaCard()
            .topoProtected(hill: true)

            if let footer {
                Text(footer)
                    .symairaText(.caption)
                    .fixedSize(horizontal: false, vertical: true)
                    .topoProtected()
            }
        }
    }
}

private enum FormRowLabelCenter: AlignmentID {
    static func defaultValue(in dimensions: ViewDimensions) -> CGFloat {
        dimensions[VerticalAlignment.center]
    }
}

extension VerticalAlignment {
    fileprivate static let formRowLabelCenter = VerticalAlignment(FormRowLabelCenter.self)
}

/// A single labelled row inside a content card.
///
/// The trailing closure holds the control — a toggle, a picker, a value, a button.
public struct SymairaFormRow<Trailing: View>: View {
    private let label: String
    private let description: String?
    private let trailing: Trailing

    public init(
        _ label: String,
        description: String? = nil,
        @ViewBuilder trailing: () -> Trailing
    ) {
        self.label = label
        self.description = description
        self.trailing = trailing()
    }

    public var body: some View {
        HStack(alignment: .formRowLabelCenter, spacing: SymairaSpacing.large) {
            VStack(alignment: .leading, spacing: SymairaSpacing.xSmall) {
                Text(label)
                    .symairaText(.body)
                    .alignmentGuide(.formRowLabelCenter) { dimensions in
                        // Drop the distance between baselines to isolate the first line's height.
                        let remainingLines = dimensions[.lastTextBaseline] - dimensions[.firstTextBaseline]
                        return (dimensions.height - remainingLines) / 2
                    }
                if let description {
                    Text(description)
                        .symairaText(.caption)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Spacer(minLength: SymairaSpacing.medium)

            trailing
        }
        .padding(.vertical, SymairaSpacing.small)
        .frame(minHeight: SymairaMetrics.minimumControlHeight)
    }
}

extension SymairaFormRow where Trailing == EmptyView {
    /// A row that carries only a label and description.
    public init(_ label: String, description: String? = nil) {
        self.init(label, description: description) { EmptyView() }
    }
}

/// Hairline between rows of a ``SymairaFormSection``.
public struct SymairaFormDivider: View {
    @Environment(\.colorScheme) private var colorScheme

    public init() {}

    public var body: some View {
        Rectangle()
            .fill(SymairaTheme.line(for: colorScheme))
            .frame(height: 1)
            .accessibilityHidden(true)
    }
}

// MARK: - Status

/// A small tone-coloured dot with an accessible label.
///
/// Colour alone never carries the meaning: the dot always ships a label for
/// VoiceOver, and callers are expected to place visible text beside it.
public struct SymairaStatusDot: View {
    @Environment(\.colorScheme) private var colorScheme

    private let tone: SymairaTone
    private let accessibilityLabel: String
    private let diameter: CGFloat

    public init(tone: SymairaTone, accessibilityLabel: String, diameter: CGFloat = 8) {
        self.tone = tone
        self.accessibilityLabel = accessibilityLabel
        self.diameter = diameter
    }

    public var body: some View {
        Circle()
            .fill(tone.foreground(for: colorScheme))
            .frame(width: diameter, height: diameter)
            .accessibilityElement()
            .accessibilityLabel(accessibilityLabel)
    }
}

/// A status dot paired with its own text, so the state is never colour-only.
public struct SymairaStatusLabel: View {
    private let tone: SymairaTone
    private let text: String

    public init(_ text: String, tone: SymairaTone) {
        self.tone = tone
        self.text = text
    }

    public var body: some View {
        HStack(spacing: SymairaSpacing.small) {
            SymairaStatusDot(tone: tone, accessibilityLabel: text)
                .accessibilityHidden(true)
            // Primary text next to the dot (UI catalog E22 B); colour never carries the state alone.
            Text(text)
                .symairaText(.body)
        }
        .accessibilityElement(children: .combine)
    }
}
