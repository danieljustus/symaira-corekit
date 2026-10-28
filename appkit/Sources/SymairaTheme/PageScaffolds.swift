import SwiftUI

/// Shared page geometry. Placeholder states reserve the same content height.
public enum SymairaPageLayout {
    public static let stateHeight: CGFloat = 240
    public static let toolbarHeight: CGFloat = 44
}

/// Stable header and toolbar, with optional page scrolling. Tables should use `scrolls: false`.
public struct SymairaPage<Toolbar: View, Content: View>: View {
    private let title: String
    private let subtitle: String?
    private let scrolls: Bool
    private let maxWidth: CGFloat
    private let toolbar: Toolbar
    private let content: Content
    @ScaledMetric private var toolbarHeight = SymairaPageLayout.toolbarHeight

    public init(
        title: String, subtitle: String? = nil, scrolls: Bool = true,
        maxWidth: CGFloat = SymairaMetrics.readableContentWidth,
        @ViewBuilder toolbar: () -> Toolbar, @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.subtitle = subtitle
        self.scrolls = scrolls
        self.maxWidth = maxWidth
        self.toolbar = toolbar()
        self.content = content()
    }

    public var body: some View {
        if scrolls {
            ScrollView { column }
        } else {
            column
        }
    }

    private var column: some View {
        VStack(alignment: .leading, spacing: SymairaSpacing.large) {
            VStack(alignment: .leading, spacing: SymairaSpacing.xSmall) {
                Text(title)
                    .symairaText(.display)
                    .foregroundStyle(SymairaTokens.ink)
                    .topoProtected()
                    .accessibilityAddTraits(.isHeader)
                Text(subtitle ?? " ")
                    .symairaText(.caption)
                    .foregroundStyle(SymairaTokens.ink3)
                    .lineLimit(1)
                    .topoProtected()
                    .accessibilityHidden(subtitle == nil)
            }
            HStack(spacing: SymairaSpacing.medium) { toolbar }
                .frame(maxWidth: .infinity, alignment: .leading)
                .frame(height: toolbarHeight)
                .accessibilityIdentifier("symaira.page.toolbar")
            content
        }
        .padding(SymairaSpacing.xLarge)
        .frame(maxWidth: maxWidth, maxHeight: scrolls ? nil : .infinity, alignment: .topLeading)
        .frame(maxWidth: .infinity, alignment: .top)
    }
}

extension SymairaPage where Toolbar == EmptyView {
    public init(
        title: String, subtitle: String? = nil, scrolls: Bool = true,
        maxWidth: CGFloat = SymairaMetrics.readableContentWidth,
        @ViewBuilder content: () -> Content
    ) {
        self.init(
            title: title, subtitle: subtitle, scrolls: scrolls, maxWidth: maxWidth, toolbar: { EmptyView() },
            content: content)
    }
}

/// Product-owned state; no loading tasks or domain models are retained by the scaffold.
public enum SymairaPageLoadState<Value> {
    case idle
    case loading
    case failed(String)
    case loaded(Value)
}

extension SymairaPageLoadState: Equatable where Value: Equatable {}
extension SymairaPageLoadState: Sendable where Value: Sendable {}

/// Idle/loading and failure reserve one fixed state height. Loaded content decides empty vs populated.
public struct SymairaPageState<Value, Loaded: View>: View {
    private let state: SymairaPageLoadState<Value>
    private let loading: String
    private let retry: () -> Void
    private let loaded: (Value) -> Loaded

    public init(
        state: SymairaPageLoadState<Value>, loading: String, retry: @escaping () -> Void,
        @ViewBuilder loaded: @escaping (Value) -> Loaded
    ) {
        self.state = state
        self.loading = loading
        self.retry = retry
        self.loaded = loaded
    }

    public var body: some View {
        switch state {
        case .idle, .loading:
            SymairaPageStateFrame {
                SymairaLoadingState(loading)
            }
        case .failed(let message):
            SymairaPageStateFrame {
                VStack(spacing: SymairaSpacing.medium) {
                    SymairaNotice(message: message, tone: .critical)
                    Button(SymairaStrings.retry, action: retry)
                        .symairaButtonStyle(.secondary)
                        .accessibilityIdentifier("symaira.page.retry")
                }
                .padding(SymairaSpacing.medium)
            }
        case .loaded(let value):
            loaded(value)
        }
    }
}

/// Empty result using exactly the loading/error content budget, with an optional next action.
public struct SymairaPageEmpty<Actions: View>: View {
    private let icon: SymairaIcon
    private let title: String
    private let message: String
    private let actions: Actions

    public init(icon: SymairaIcon, title: String, message: String, @ViewBuilder actions: () -> Actions) {
        self.icon = icon
        self.title = title
        self.message = message
        self.actions = actions()
    }

    public var body: some View {
        SymairaPageStateFrame {
            SymairaEmptyState(icon: icon, title: title, message: message) { actions }
        }
    }
}

extension SymairaPageEmpty where Actions == EmptyView {
    public init(icon: SymairaIcon, title: String, message: String) {
        self.init(icon: icon, title: title, message: message) { EmptyView() }
    }
}

/// A single implementation prevents loading, error and empty geometry from drifting.
/// Scales with Dynamic Type while keeping the same budget across states.
struct SymairaPageStateFrame<Content: View>: View {
    @ScaledMetric private var height = SymairaPageLayout.stateHeight
    @ViewBuilder let content: Content

    var body: some View {
        content
            .frame(maxWidth: .infinity)
            .frame(height: height)
            .accessibilityIdentifier("symaira.page.state")
    }
}
