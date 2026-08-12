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

    public func foreground(for colorScheme: ColorScheme) -> Color {
        guard colorScheme == .light else { return foreground }
        switch self {
        case .neutral: return Color(hex: "5F584F")
        case .positive: return Color(hex: "2E7D4C")
        case .warning: return Color(hex: "8A5B12")
        case .critical: return Color(hex: "B3261E")
        case .informative: return Color(hex: "245C86")
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
    private let systemImage: String?

    public init(_ label: String, tone: SymairaTone = .neutral, systemImage: String? = nil) {
        self.label = label
        self.tone = tone
        self.systemImage = systemImage
    }

    public var body: some View {
        let toneColor = tone.foreground(for: colorScheme)
        Group {
            if let systemImage {
                Label(label, systemImage: systemImage)
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
            Image(systemName: tone.systemImage)
                .foregroundStyle(toneColor)
                .imageScale(.large)
                .accessibilityHidden(true)

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
                Button(action: onDismiss) {
                    Image(systemName: "xmark")
                        .frame(minWidth: 24, minHeight: 24)
                }
                .buttonStyle(.plain)
                .foregroundStyle(SymairaTheme.foregroundMuted(for: colorScheme))
                .accessibilityLabel("Dismiss")
            }
        }
        .padding(SymairaSpacing.medium)
        .background(toneColor.opacity(0.10), in: RoundedRectangle(cornerRadius: SymairaRadius.control, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: SymairaRadius.control, style: .continuous)
                .stroke(toneColor.opacity(0.30), lineWidth: 1)
        )
        .accessibilityElement(children: onDismiss == nil ? .combine : .contain)
    }
}

public struct SymairaEmptyState<Actions: View>: View {
    @Environment(\.colorScheme) private var colorScheme

    private let systemImage: String
    private let title: String
    private let message: String
    private let actions: Actions

    public init(
        systemImage: String,
        title: String,
        message: String,
        @ViewBuilder actions: () -> Actions
    ) {
        self.systemImage = systemImage
        self.title = title
        self.message = message
        self.actions = actions()
    }

    public var body: some View {
        VStack(spacing: SymairaSpacing.medium) {
            Image(systemName: systemImage)
                .font(.system(size: SymairaMetrics.emptyStateSymbolSize, weight: .medium))
                .symbolRenderingMode(.hierarchical)
                .foregroundStyle(SymairaTheme.goldPrimary)
                .accessibilityHidden(true)
            Text(title)
                .font(SymairaTypography.heading)
                .foregroundStyle(SymairaTheme.foregroundPrimary(for: colorScheme))
            Text(message)
                .font(SymairaTypography.body)
                .foregroundStyle(SymairaTheme.foregroundSecondary(for: colorScheme))
                .multilineTextAlignment(.center)
                .frame(maxWidth: 440)
            actions
                .padding(.top, SymairaSpacing.xSmall)
        }
        .padding(SymairaSpacing.xLarge)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .contain)
    }
}

extension SymairaEmptyState where Actions == EmptyView {
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
                .tint(SymairaTheme.goldPrimary)
                .controlSize(.regular)
            Text(message)
                .font(SymairaTypography.callout)
                .foregroundStyle(SymairaTheme.foregroundSecondary(for: colorScheme))
        }
        .padding(SymairaSpacing.xLarge)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(message)
    }
}
