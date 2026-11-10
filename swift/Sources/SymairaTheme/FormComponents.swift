import SwiftUI

// MARK: - Text fields

/// Opaque Liquid Topography input surface and appearance-aware focus ring.
///
/// Six of the client apps style their text fields inline today, each with its own
/// padding and border. This is the one place that decision should live.
public struct SymairaTextFieldStyle: TextFieldStyle {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.isEnabled) private var isEnabled

    private let isFocused: Bool

    /// - Parameter isFocused: drives the focus ring. Wire it to a `@FocusState`
    ///   binding; SwiftUI does not expose focus to a `TextFieldStyle` directly.
    public init(isFocused: Bool = false) {
        self.isFocused = isFocused
    }

    public func _body(configuration: TextField<Self._Label>) -> some View {
        let shape = RoundedRectangle(cornerRadius: SymairaRadius.control, style: .continuous)
        configuration
            .textFieldStyle(.plain)
            // The role modifier is main-actor isolated and `_body` is not, so the
            // font token is applied directly here. Colour stays with the field.
            .font(SymairaTypography.body)
            .padding(.horizontal, SymairaSpacing.medium)
            .padding(.vertical, SymairaSpacing.small)
            .frame(minHeight: SymairaMetrics.minimumControlHeight)
            .background(shape.fill(fill))
            .overlay(shape.stroke(border, lineWidth: borderWidth))
            .opacity(isEnabled ? 1 : 0.55)
    }

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
        return SymairaTheme.line(for: colorScheme)
    }

    private var borderWidth: CGFloat {
        if isFocused { return 2 }
        return contrast == .increased ? 1.5 : 1
    }
}

extension TextFieldStyle where Self == SymairaTextFieldStyle {
    /// Symaira text field chrome without a focus ring.
    public static var symaira: SymairaTextFieldStyle { SymairaTextFieldStyle() }

    /// Symaira text field chrome with an explicit focus state.
    public static func symaira(isFocused: Bool) -> SymairaTextFieldStyle {
        SymairaTextFieldStyle(isFocused: isFocused)
    }
}

// MARK: - Section scaffold

/// A titled group of rows on an opaque shared content card.
///
/// Five client apps build their own settings scaffold. The differences between
/// them are accidental — heading size, gap above the card, whether a footer is
/// muted — and they are exactly what makes the apps look unrelated.
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

/// A single labelled row inside a ``SymairaFormSection``.
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
        HStack(alignment: .firstTextBaseline, spacing: SymairaSpacing.large) {
            VStack(alignment: .leading, spacing: SymairaSpacing.xSmall) {
                Text(label)
                    .symairaText(.body)
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
            Text(text)
                .symairaText(.secondary)
        }
        .accessibilityElement(children: .combine)
    }
}
