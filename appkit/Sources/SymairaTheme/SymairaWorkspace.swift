import SwiftUI

#if os(macOS)
/// Shared macOS chrome: one rounded content surface, resizable sidebar and a
/// continuous toolbar/sidebar background. Products own navigation and content.
/// Supply nil topography for dense lists/settings; no renderer is then mounted.
public struct SymairaWorkspace<Navigation: View, Content: View>: View {
    @Binding private var sidebar: SymairaSidebarState
    private let topography: SymairaTopoModel?
    private let animationEnabled: Bool
    private let navigation: (Bool) -> Navigation
    private let content: Content
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    public init(
        sidebar: Binding<SymairaSidebarState>, topography: SymairaTopoModel? = nil,
        animationEnabled: Bool = true,
        @ViewBuilder navigation: @escaping (Bool) -> Navigation,
        @ViewBuilder content: () -> Content
    ) {
        _sidebar = sidebar
        self.topography = topography
        self.animationEnabled = animationEnabled
        self.navigation = navigation
        self.content = content()
    }

    public var body: some View {
        HStack(spacing: 0) {
            navigation(sidebar.showsLabels)
                .frame(width: sidebar.width)
                .overlay(alignment: .trailing) {
                    SymairaSidebarResizeHandle(
                        width: sidebar.width, isEnabled: sidebar.canExpand,
                        onResize: { sidebar.resize(to: $0) }, onStep: { sidebar.step($0) }
                    )
                    .frame(width: 10)
                }
            ZStack {
                if let topography {
                    SymairaTopoView(model: topography, animationEnabled: animationEnabled)
                } else {
                    SymairaTokens.canvas
                }
                content.environment(\.symairaTopography, topography)
            }
            .coordinateSpace(name: SymairaTopo.space)
            .clipShape(panel)
            .overlay(
                panel.strokeBorder(
                    SymairaTokens.line.opacity(contrast == .increased ? 1 : 0.6),
                    lineWidth: contrast == .increased ? 1.5 : 1)
            )
            .padding([.trailing, .bottom], SymairaSpacing.small)
        }
        .background { chrome.ignoresSafeArea() }
        .onGeometryChange(for: CGFloat.self) {
            $0.size.width
        } action: {
            sidebar.availableWidth = $0
        }
    }

    private var panel: RoundedRectangle {
        RoundedRectangle(cornerRadius: SymairaRadius.panel, style: .continuous)
    }

    @ViewBuilder private var chrome: some View {
        if reduceTransparency {
            SymairaTokens.sidebar
        } else {
            Color.clear.symairaGlassChrome(tint: SymairaTokens.sidebar, cornerRadius: 0)
        }
    }
}
#endif

/// Shared hover/pressed/selected palette; destinations and focus ownership stay
/// in the product. Pair selection with a label weight and accessibility trait.
public struct SymairaNavigationButtonStyle: ButtonStyle {
    private let isSelected: Bool

    public init(isSelected: Bool = false) { self.isSelected = isSelected }

    public func makeBody(configuration: Configuration) -> some View {
        NavigationLabel(configuration: configuration, isSelected: isSelected)
    }
}

private struct NavigationLabel: View {
    let configuration: ButtonStyleConfiguration
    let isSelected: Bool
    @State private var hovered = false

    var body: some View {
        configuration.label
            .foregroundStyle(isSelected ? SymairaTokens.ink : SymairaTokens.ink2)
            .background(
                isSelected
                    ? SymairaTokens.selection
                    : (hovered || configuration.isPressed ? SymairaTokens.raised : Color.clear)
            )
            .clipShape(RoundedRectangle(cornerRadius: SymairaRadius.control))
            .onHover { hovered = $0 }
    }
}
