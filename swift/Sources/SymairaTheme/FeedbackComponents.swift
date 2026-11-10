import SwiftUI

public enum SymairaTone: Sendable {
    case neutral
    case positive
    case warning
    case critical
    case informative

    public var foreground: Color {
        switch self {
        case .neutral: SymairaTheme.textSecondary
        case .positive: SymairaTheme.positive
        case .warning: SymairaTheme.warning
        case .critical: SymairaTheme.critical
        case .informative: SymairaTheme.informative
        }
    }

    /// Liquid Topography status colours. Light values reach at least 4.5:1 on
    /// `surface`; dark values at least 8:1. Green is for live measurements only.
    public func foreground(for colorScheme: ColorScheme) -> Color {
        let dark = colorScheme == .dark
        switch self {
        case .neutral: return SymairaTheme.foregroundSecondary(for: colorScheme)
        case .positive: return Color(hex: dark ? "93C49F" : "34694A")
        case .warning: return Color(hex: dark ? "E9BC73" : "7E5310")
        case .critical: return Color(hex: dark ? "E39C8A" : "9A4634")
        case .informative: return Color(hex: dark ? "8CC8F2" : "245C86")
        }
    }

    /// Symaira icon for this tone (Notice, Badge `icon: tone.symairaIcon`).
    public var symairaIcon: SymairaIcon {
        switch self {
        case .neutral, .informative: .info
        case .positive: .success
        case .warning: .warning
        case .critical: .error
        }
    }

    public var systemImage: String {
        switch self {
        case .neutral: "info.circle"
        case .positive: "checkmark.circle.fill"
        case .warning: "exclamationmark.triangle.fill"
        case .critical: "xmark.octagon.fill"
        case .informative: "info.circle.fill"
        }
    }
}

public struct SymairaBadge: View {
    @Environment(\.colorScheme) private var colorScheme

    private let label: String
    private let tone: SymairaTone
    private let glyph: SymairaGlyph?

    public init(_ label: String, tone: SymairaTone = .neutral, systemImage: String? = nil) {
        self.label = label
        self.tone = tone
        self.glyph = systemImage.map(SymairaGlyph.system)
    }

    public init(_ label: String, tone: SymairaTone = .neutral, icon: SymairaIcon) {
        self.label = label
        self.tone = tone
        self.glyph = .symaira(icon)
    }

    public var body: some View {
        let toneColor = tone.foreground(for: colorScheme)
        Group {
            if let glyph {
                Label {
                    Text(label)
                } icon: {
                    SymairaGlyphView(glyph, size: 12)
                }
            } else {
                Text(label)
            }
        }
        .font(SymairaTypography.label)
        .padding(.horizontal, SymairaSpacing.small)
        .padding(.vertical, SymairaSpacing.xSmall)
        .foregroundStyle(toneColor)
        .background(toneColor.opacity(0.12), in: Capsule())
        .overlay(Capsule().stroke(toneColor.opacity(0.26), lineWidth: 1))
        .accessibilityElement(children: .combine)
    }
}

public struct SymairaNotice: View {
    @Environment(\.colorScheme) private var colorScheme

    private let title: String?
    private let message: String
    private let tone: SymairaTone
    private let onDismiss: (() -> Void)?

    public init(
        title: String? = nil,
        message: String,
        tone: SymairaTone = .informative,
        onDismiss: (() -> Void)? = nil
    ) {
        self.title = title
        self.message = message
        self.tone = tone
        self.onDismiss = onDismiss
    }

    public var body: some View {
        let toneColor = tone.foreground(for: colorScheme)
        HStack(alignment: .top, spacing: SymairaSpacing.medium) {
            SymairaIconView(tone.symairaIcon, size: 20)
                .foregroundStyle(toneColor)

            // The message must take its width from the container rather than
            // from `.fixedSize(horizontal: false, vertical: true)` next to a
            // `Spacer`: that combination has no solution inside a
            // NavigationSplitView detail column on macOS 26, and a message long
            // enough to wrap leaves the whole window blank (#68).
            VStack(alignment: .leading, spacing: SymairaSpacing.xSmall) {
                if let title {
                    Text(title)
                        .font(SymairaTypography.subheading)
                        .foregroundStyle(SymairaTheme.foregroundPrimary(for: colorScheme))
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                Text(message)
                    .font(SymairaTypography.callout)
                    .foregroundStyle(SymairaTheme.foregroundSecondary(for: colorScheme))
                    .multilineTextAlignment(.leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            if let onDismiss {
                SymairaIconButton(SymairaStrings.dismiss, icon: .close, size: 16, action: onDismiss)
                    .frame(minWidth: 24, minHeight: 24)
                    .foregroundStyle(SymairaTheme.foregroundMuted(for: colorScheme))
            }
        }
        .padding(SymairaSpacing.medium)
        .background(
            SymairaTheme.surfaceOpaque(for: colorScheme),
            in: RoundedRectangle(cornerRadius: SymairaRadius.control, style: .continuous)
        )
        .overlay(
            RoundedRectangle(cornerRadius: SymairaRadius.control, style: .continuous)
                .stroke(toneColor.opacity(0.30), lineWidth: 1)
        )
        .accessibilityElement(children: onDismiss == nil ? .combine : .contain)
        .topoProtected(hill: true)
    }
}

public struct SymairaEmptyState<Actions: View>: View {
    @Environment(\.colorScheme) private var colorScheme

    private let glyph: SymairaGlyph
    private let title: String
    private let message: String
    private let actions: Actions

    public init(
        icon: SymairaIcon,
        title: String,
        message: String,
        @ViewBuilder actions: () -> Actions
    ) {
        self.init(glyph: .symaira(icon), title: title, message: message, actions: actions)
    }

    public init(
        systemImage: String,
        title: String,
        message: String,
        @ViewBuilder actions: () -> Actions
    ) {
        self.init(glyph: .system(systemImage), title: title, message: message, actions: actions)
    }

    private init(glyph: SymairaGlyph, title: String, message: String, @ViewBuilder actions: () -> Actions) {
        self.glyph = glyph
        self.title = title
        self.message = message
        self.actions = actions()
    }

    public var body: some View {
        VStack(spacing: SymairaSpacing.medium) {
            SymairaGlyphView(glyph, size: SymairaMetrics.emptyStateSymbolSize)
                .foregroundStyle(SymairaTheme.foregroundMuted(for: colorScheme))
                .accessibilityHidden(true)
                .topoProtected()
            Text(title)
                .font(SymairaTypography.heading)
                .foregroundStyle(SymairaTheme.foregroundPrimary(for: colorScheme))
                .topoProtected()
            Text(message)
                .font(SymairaTypography.body)
                .foregroundStyle(SymairaTheme.foregroundSecondary(for: colorScheme))
                .multilineTextAlignment(.center)
                .topoProtected()
                .frame(maxWidth: 440)
            actions
                .topoProtected()
                .padding(.top, SymairaSpacing.xSmall)
        }
        .padding(SymairaSpacing.xLarge)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .contain)
    }
}

extension SymairaEmptyState where Actions == EmptyView {
    public init(icon: SymairaIcon, title: String, message: String) {
        self.init(icon: icon, title: title, message: message) {
            EmptyView()
        }
    }

    public init(systemImage: String, title: String, message: String) {
        self.init(systemImage: systemImage, title: title, message: message) {
            EmptyView()
        }
    }
}

public struct SymairaLoadingState: View {
    @Environment(\.colorScheme) private var colorScheme

    private let message: String

    public init(_ message: String) {
        self.message = message
    }

    public var body: some View {
        VStack(spacing: SymairaSpacing.medium) {
            ProgressView()
                .tint(SymairaTheme.selected(for: colorScheme))
                .controlSize(.regular)
            Text(message)
                .font(SymairaTypography.callout)
                .foregroundStyle(SymairaTheme.foregroundSecondary(for: colorScheme))
        }
        .topoProtected()
        .padding(SymairaSpacing.xLarge)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(message)
    }
}
