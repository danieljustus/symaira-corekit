import SwiftUI

// MARK: - Backgrounds

public enum SymairaGridStyle: Sendable {
    case lines
    case dots
}

/// Decorative blueprint grid shared by Symaira application backgrounds.
public struct BlueprintGrid: View {
    private let spacing: CGFloat
    private let style: SymairaGridStyle
    private let color: Color

    public init(
        spacing: CGFloat = 24,
        style: SymairaGridStyle = .lines,
        color: Color = Color.white.opacity(0.022)
    ) {
        self.spacing = max(spacing, 8)
        self.style = style
        self.color = color
    }

    public var body: some View {
        Canvas { context, size in
            switch style {
            case .lines:
                var path = Path()
                for x in stride(from: 0.0, through: size.width, by: spacing) {
                    path.move(to: CGPoint(x: x, y: 0))
                    path.addLine(to: CGPoint(x: x, y: size.height))
                }
                for y in stride(from: 0.0, through: size.height, by: spacing) {
                    path.move(to: CGPoint(x: 0, y: y))
                    path.addLine(to: CGPoint(x: size.width, y: y))
                }
                context.stroke(path, with: .color(color), lineWidth: 0.75)
            case .dots:
                for x in stride(from: 0.0, through: size.width, by: spacing) {
                    for y in stride(from: 0.0, through: size.height, by: spacing) {
                        let dot = CGRect(x: x - 0.75, y: y - 0.75, width: 1.5, height: 1.5)
                        context.fill(Path(ellipseIn: dot), with: .color(color))
                    }
                }
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// Ambient brand light that scales with its container instead of relying on
/// window-specific offsets.
public struct AmbientGlows: View {
    private let intensity: Double

    public init(intensity: Double = 1) {
        self.intensity = min(max(intensity, 0), 2)
    }

    public var body: some View {
        GeometryReader { geometry in
            ZStack {
                RadialGradient(
                    colors: [SymairaTheme.goldPrimary.opacity(0.10 * intensity), .clear],
                    center: .topLeading,
                    startRadius: 0,
                    endRadius: max(geometry.size.width, geometry.size.height) * 0.7
                )
                RadialGradient(
                    colors: [SymairaTheme.iceSecondary.opacity(0.07 * intensity), .clear],
                    center: .bottomTrailing,
                    startRadius: 0,
                    endRadius: max(geometry.size.width, geometry.size.height) * 0.8
                )
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// Full-window, appearance-aware Symaira background.
public struct SymairaBackdrop: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    private let gridStyle: SymairaGridStyle
    private let showsGrid: Bool

    public init(gridStyle: SymairaGridStyle = .lines, showsGrid: Bool = true) {
        self.gridStyle = gridStyle
        self.showsGrid = showsGrid
    }

    public var body: some View {
        ZStack {
            SymairaTheme.backgroundPrimary(for: colorScheme)
            if showsGrid && !reduceTransparency {
                BlueprintGrid(
                    style: gridStyle,
                    color: gridColor
                )
            }
            if !reduceTransparency {
                AmbientGlows()
            }
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    private var gridColor: Color {
        colorScheme == .dark
            ? Color.white.opacity(0.022)
            : SymairaTheme.goldShadow.opacity(0.055)
    }
}

// MARK: - Telemetry detail

public struct TelemetryCorners: View {
    private let color: Color
    private let length: CGFloat
    private let lineWidth: CGFloat

    public init(
        color: Color = SymairaTheme.goldPrimary.opacity(0.35),
        length: CGFloat = 8,
        lineWidth: CGFloat = 1
    ) {
        self.color = color
        self.length = length
        self.lineWidth = lineWidth
    }

    public var body: some View {
        GeometryReader { geometry in
            Path { path in
                path.move(to: CGPoint(x: 0, y: length))
                path.addLine(to: .zero)
                path.addLine(to: CGPoint(x: length, y: 0))

                path.move(to: CGPoint(x: geometry.size.width - length, y: 0))
                path.addLine(to: CGPoint(x: geometry.size.width, y: 0))
                path.addLine(to: CGPoint(x: geometry.size.width, y: length))

                path.move(to: CGPoint(x: 0, y: geometry.size.height - length))
                path.addLine(to: CGPoint(x: 0, y: geometry.size.height))
                path.addLine(to: CGPoint(x: length, y: geometry.size.height))

                path.move(to: CGPoint(x: geometry.size.width - length, y: geometry.size.height))
                path.addLine(to: CGPoint(x: geometry.size.width, y: geometry.size.height))
                path.addLine(to: CGPoint(x: geometry.size.width, y: geometry.size.height - length))
            }
            .stroke(color, lineWidth: lineWidth)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

// MARK: - Content surfaces

/// Standard-material panel for content. Liquid Glass is intentionally reserved
/// for controls and navigation, matching Apple's material hierarchy.
public struct GlassmorphicPanelModifier: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    private let cornerRadius: CGFloat
    private let addCorners: Bool

    public init(cornerRadius: CGFloat = SymairaRadius.card, addCorners: Bool = true) {
        self.cornerRadius = cornerRadius
        self.addCorners = addCorners
    }

    public func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        content
            .background {
                if reduceTransparency {
                    shape.fill(SymairaTheme.surfaceOpaque(for: colorScheme))
                } else {
                    shape
                        .fill(.regularMaterial)
                        .overlay(shape.fill(surfaceTint))
                }
            }
            .overlay(shape.stroke(borderColor, lineWidth: contrast == .increased ? 1.5 : 1))
            .overlay {
                if addCorners {
                    TelemetryCorners()
                        .padding(1)
                }
            }
            .clipShape(shape)
            .shadow(color: shadowColor, radius: 12, x: 0, y: 6)
    }

    private var surfaceTint: Color {
        colorScheme == .dark ? SymairaTheme.bgCard : Color.white.opacity(0.32)
    }

    private var borderColor: Color {
        if contrast == .increased {
            return colorScheme == .dark ? Color.white.opacity(0.22) : Color.black.opacity(0.18)
        }
        return colorScheme == .dark ? SymairaTheme.borderGlass : Color.black.opacity(0.08)
    }

    private var shadowColor: Color {
        colorScheme == .dark ? Color.black.opacity(0.28) : Color.black.opacity(0.10)
    }
}

public struct GlassCardModifier: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    private let isHovered: Bool
    private let cornerRadius: CGFloat

    public init(isHovered: Bool = false, cornerRadius: CGFloat = SymairaRadius.card) {
        self.isHovered = isHovered
        self.cornerRadius = cornerRadius
    }

    public func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        content
            .background {
                if reduceTransparency {
                    shape.fill(SymairaTheme.surfaceOpaque(for: colorScheme))
                } else {
                    shape
                        .fill(.regularMaterial)
                        .overlay(shape.fill(surfaceTint))
                }
            }
            .overlay(shape.stroke(borderColor, lineWidth: contrast == .increased ? 1.5 : 1))
            .clipShape(shape)
            .shadow(color: shadowColor, radius: isHovered ? 14 : 9, x: 0, y: isHovered ? 7 : 4)
    }

    private var surfaceTint: Color {
        if colorScheme == .dark {
            return isHovered ? SymairaTheme.bgCardHover : SymairaTheme.bgCard
        }
        return isHovered ? Color.white.opacity(0.62) : Color.white.opacity(0.38)
    }

    private var borderColor: Color {
        if isHovered {
            return SymairaTheme.borderGlassHover
        }
        if contrast == .increased {
            return colorScheme == .dark ? Color.white.opacity(0.22) : Color.black.opacity(0.18)
        }
        return colorScheme == .dark ? SymairaTheme.borderGlass : Color.black.opacity(0.08)
    }

    private var shadowColor: Color {
        guard isHovered else { return Color.black.opacity(colorScheme == .dark ? 0.22 : 0.08) }
        return SymairaTheme.goldShadow.opacity(colorScheme == .dark ? 0.15 : 0.10)
    }
}

extension View {
    public func glassmorphicPanel(
        cornerRadius: CGFloat = SymairaRadius.card,
        addCorners: Bool = true
    ) -> some View {
        modifier(GlassmorphicPanelModifier(cornerRadius: cornerRadius, addCorners: addCorners))
    }

    public func glassCard(
        isHovered: Bool = false,
        cornerRadius: CGFloat = SymairaRadius.card
    ) -> some View {
        modifier(GlassCardModifier(isHovered: isHovered, cornerRadius: cornerRadius))
    }
}

// MARK: - Liquid Glass chrome

public enum SymairaGlassVariant: Sendable {
    case regular
    case clear
}

/// Liquid Glass for custom navigation and control chrome. On pre-26 systems it
/// falls back to a standard material, and Reduce Transparency gets an opaque
/// high-legibility surface.
public struct SymairaGlassChromeModifier: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    private let variant: SymairaGlassVariant
    private let tint: Color?
    private let isInteractive: Bool
    private let cornerRadius: CGFloat

    public init(
        variant: SymairaGlassVariant = .regular,
        tint: Color? = nil,
        isInteractive: Bool = false,
        cornerRadius: CGFloat = SymairaRadius.control
    ) {
        self.variant = variant
        self.tint = tint
        self.isInteractive = isInteractive
        self.cornerRadius = cornerRadius
    }

    public func body(content: Content) -> some View {
        Group {
            if reduceTransparency {
                opaqueFallback(content)
            } else {
                adaptiveGlass(content)
            }
        }
    }

    @ViewBuilder
    private func adaptiveGlass(_ content: Content) -> some View {
        #if compiler(>=6.2)
        if #available(macOS 26.0, iOS 26.0, tvOS 26.0, *) {
            switch variant {
            case .regular:
                content.glassEffect(
                    .regular.tint(tint).interactive(isInteractive),
                    in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                )
            case .clear:
                content.glassEffect(
                    .clear.tint(tint).interactive(isInteractive),
                    in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                )
            }
        } else {
            materialFallback(content)
        }
        #else
        materialFallback(content)
        #endif
    }

    private func opaqueFallback(_ content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        return
            content
            .background(SymairaTheme.surfaceOpaque(for: colorScheme), in: shape)
            .overlay(shape.stroke(fallbackBorder, lineWidth: contrast == .increased ? 1.5 : 1))
    }

    private func materialFallback(_ content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        return
            content
            .background(.ultraThinMaterial, in: shape)
            .background((tint ?? .clear).opacity(0.10), in: shape)
            .overlay(shape.stroke(fallbackBorder, lineWidth: contrast == .increased ? 1.5 : 1))
    }

    private var fallbackBorder: Color {
        contrast == .increased
            ? SymairaTheme.foregroundMuted(for: colorScheme)
            : SymairaTheme.line(for: colorScheme)
    }
}

extension View {
    public func symairaGlassChrome(
        variant: SymairaGlassVariant = .regular,
        tint: Color? = nil,
        isInteractive: Bool = false,
        cornerRadius: CGFloat = SymairaRadius.control
    ) -> some View {
        modifier(
            SymairaGlassChromeModifier(
                variant: variant,
                tint: tint,
                isInteractive: isInteractive,
                cornerRadius: cornerRadius
            )
        )
    }
}

/// Groups multiple Liquid Glass controls so the system can render and morph
/// them efficiently. It is a transparent wrapper on older operating systems.
public struct SymairaGlassEffectContainer<Content: View>: View {
    private let spacing: CGFloat
    private let content: Content

    public init(
        spacing: CGFloat = SymairaMetrics.glassGroupSpacing,
        @ViewBuilder content: () -> Content
    ) {
        self.spacing = spacing
        self.content = content()
    }

    @ViewBuilder
    public var body: some View {
        #if compiler(>=6.2)
        if #available(macOS 26.0, iOS 26.0, tvOS 26.0, *) {
            GlassEffectContainer(spacing: spacing) {
                content
            }
        } else {
            content
        }
        #else
        content
        #endif
    }
}

// MARK: - Control tiers

/// Which of the three control tiers (GUIDELINES CTRL-1) the controls of a region belong to.
/// The third tier, navigation, is the workspace shell itself (`SymairaNavigationButton`,
/// `SymairaWorkspaceToolbar`) and needs no value.
///
/// - `page`: actions about the whole page or sheet (page toolbar, sheet footer, empty-state
///   actions). Extra-large controls, glass secondary actions, the opaque primary action.
/// - `workbench`: tools that work on content (inspectors, panels, lists, forms). Native
///   controls in `.large`, solid instead of glass, so every control of a row has one height.
public enum SymairaControlTier: Sendable {
    case page
    case workbench
}

private struct SymairaControlTierKey: EnvironmentKey {
    static let defaultValue = SymairaControlTier.page
}

extension EnvironmentValues {
    /// Read by `symairaButtonStyle` and `SymairaSegmentedControl`. Set it with `symairaControlTier(_:)`.
    public var symairaControlTier: SymairaControlTier {
        get { self[SymairaControlTierKey.self] }
        set { self[SymairaControlTierKey.self] = newValue }
    }
}

extension View {
    /// Puts a region in a control tier and gives its native controls the tier's size:
    /// `.extraLarge` (36 pt) for `page`, `.large` (28 pt) for `workbench`. A later
    /// `.controlSize` inside the region still wins. `SymairaPage` sets `page` on its toolbar
    /// and `workbench` on its content; sheets and other windows set it themselves.
    public func symairaControlTier(_ tier: SymairaControlTier) -> some View {
        environment(\.symairaControlTier, tier)
            #if !os(tvOS)
        .controlSize(tier == .page ? .extraLarge : .large)
            #endif
    }
}

// MARK: - Buttons

public enum SymairaButtonRole: Sendable {
    case primary
    case secondary
    case toolbar
    /// A visible destructive action (ACTION-4): opaque `critical` with an `on-critical` label in
    /// the primary's geometry. Pair it with `Button(role: .destructive)`; it counts as the
    /// screen's one opaque action.
    case destructive
}

/// Preferred button API.
///
/// In the `page` tier (the default), `primary` is the one opaque Symaira action of a
/// screen, `secondary` native Liquid Glass in the same geometry (UI catalog E02, revised
/// 2026-11-26) and `toolbar` the native glass button. In the `workbench` tier all three
/// are the native solid buttons at the region's control size, so they line up with the
/// menus, segments and switches next to them: `primary` filled with `ink`, `destructive`
/// filled with `critical`, `secondary` and `toolbar` bordered. Every role stays neutral: a
/// window-wide `.tint(SymairaTokens.selected)` colors selection states only (COLOR-2).
public struct SymairaAdaptiveButtonModifier: ViewModifier {
    @Environment(\.symairaControlTier) private var tier
    @Environment(\.colorScheme) private var colorScheme
    private let role: SymairaButtonRole
    private let onPressChange: ((Bool) -> Void)?

    public init(role: SymairaButtonRole, onPressChange: ((Bool) -> Void)? = nil) {
        self.role = role
        self.onPressChange = onPressChange
    }

    @ViewBuilder
    public func body(content: Content) -> some View {
        #if os(tvOS)
        // The remote moves a focus that only the system styles show (lift, highlight, motion);
        // the drawn Symaira styles would leave the focused button looking like the others.
        switch role {
        case .primary:
            content.buttonStyle(.borderedProminent).tint(SymairaTokens.primary)
                .foregroundStyle(SymairaTokens.onPrimary)
        case .destructive:
            content.buttonStyle(.borderedProminent).tint(SymairaTokens.critical)
                .foregroundStyle(SymairaTokens.onCritical)
        case .secondary, .toolbar:
            content.buttonStyle(.bordered)
        }
        #else
        if tier == .workbench {
            workbenchButton(content)
        } else {
            pageButton(content)
        }
        #endif
    }

    @ViewBuilder
    private func workbenchButton(_ content: Content) -> some View {
        switch role {
        case .primary:
            content.buttonStyle(.borderedProminent)
                .tint(SymairaTheme.foregroundPrimary(for: colorScheme))
                .foregroundStyle(SymairaTheme.surfaceOpaque(for: colorScheme))
        case .destructive:
            // A light tint would put the system's white label on salmon (2.2:1 in dark), so the
            // label takes `on-critical` like the page style.
            content.buttonStyle(.borderedProminent)
                .tint(SymairaTokens.Palette.critical.color(for: colorScheme))
                .foregroundStyle(SymairaTokens.Palette.onCritical.color(for: colorScheme))
        case .secondary, .toolbar:
            content.buttonStyle(.bordered).tint(nil)
        }
    }

    @ViewBuilder
    private func pageButton(_ content: Content) -> some View {
        switch role {
        case .primary:
            content.buttonStyle(SymairaPrimaryButtonStyle(onPressChange: onPressChange))
        case .destructive:
            content.buttonStyle(SymairaPrimaryButtonStyle(onPressChange: onPressChange, isDestructive: true))
        case .secondary:
            content.buttonStyle(SymairaSecondaryButtonStyle(onPressChange: onPressChange))
        case .toolbar:
            toolbarButton(content)
        }
    }

    @ViewBuilder
    private func toolbarButton(_ content: Content) -> some View {
        #if compiler(>=6.2)
        if #available(macOS 26.0, iOS 26.0, tvOS 26.0, *) {
            // `.glass` fills itself with the environment tint; a product's window-wide selection
            // tint would turn every icon button champagne.
            content.buttonStyle(.glass).tint(nil)
        } else {
            content.buttonStyle(.borderless)
        }
        #else
        content.buttonStyle(.borderless)
        #endif
    }
}

extension View {
    /// Observes press and release for primary and secondary styles of the `page` tier on
    /// macOS and iOS. The native styles (toolbar, workbench tier, tvOS) do not invoke it.
    public func symairaButtonStyle(
        _ role: SymairaButtonRole, onPressChange: ((Bool) -> Void)? = nil
    ) -> some View {
        modifier(SymairaAdaptiveButtonModifier(role: role, onPressChange: onPressChange))
    }
}

/// Primary action: filled `ink` capsule with `surface` text and a bold label, as high as
/// the extra-large native controls beside it. At most one per view. The destructive role
/// draws the same capsule in `critical` with an `on-critical` label (ACTION-4).
public struct SymairaPrimaryButtonStyle: ButtonStyle {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private let onPressChange: ((Bool) -> Void)?
    private let isDestructive: Bool

    public init(onPressChange: ((Bool) -> Void)? = nil) {
        self.init(onPressChange: onPressChange, isDestructive: false)
    }

    init(onPressChange: ((Bool) -> Void)?, isDestructive: Bool) {
        self.onPressChange = onPressChange
        self.isDestructive = isDestructive
    }

    public func makeBody(configuration: Configuration) -> some View {
        let shape = Capsule()
        let fill = isDestructive ? SymairaTokens.Palette.critical : SymairaTokens.Palette.ink
        let label = isDestructive ? SymairaTokens.Palette.onCritical : SymairaTokens.Palette.surface
        SymairaIconHost(isPressed: configuration.isPressed) {
            configuration.label
                .font(SymairaTypography.bodyEmphasized)
                .lineLimit(1)
                .foregroundStyle(label.color(for: colorScheme))
                .padding(.horizontal, SymairaMetrics.contentActionHorizontalPadding)
                .frame(minHeight: SymairaMetrics.contentActionHeight)
                .background(fill.color(for: colorScheme), in: shape)
                .contentShape(shape)
                .brightness(configuration.isPressed ? -0.05 : 0)
                .scaleEffect(configuration.isPressed && !reduceMotion ? 0.98 : 1)
                .opacity(isEnabled ? 1 : 0.55)
                .animation(reduceMotion ? nil : .easeOut(duration: 0.15), value: configuration.isPressed)
        }
        .onChange(of: configuration.isPressed) { _, isPressed in onPressChange?(isPressed) }
    }
}

/// Secondary action: native interactive Liquid Glass on macOS/iOS 26+, in the
/// primary button's geometry (font, padding, height, capsule), so the two
/// roles still line up. Reduce Transparency and older systems get the opaque
/// `raised` fill with its outline.
public struct SymairaSecondaryButtonStyle: ButtonStyle {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    private let onPressChange: ((Bool) -> Void)?
    /// Tests reach the opaque fallback with `false`; Reduce Transparency is read-only on macOS.
    let allowsGlass: Bool

    public init(onPressChange: ((Bool) -> Void)? = nil) {
        self.init(onPressChange: onPressChange, allowsGlass: true)
    }

    init(onPressChange: ((Bool) -> Void)? = nil, allowsGlass: Bool) {
        self.onPressChange = onPressChange
        self.allowsGlass = allowsGlass
    }

    public func makeBody(configuration: Configuration) -> some View {
        let shape = Capsule()
        SymairaIconHost(isPressed: configuration.isPressed) {
            surface(
                configuration.label
                    .font(SymairaTypography.bodyEmphasized)
                    .lineLimit(1)
                    .foregroundStyle(SymairaTheme.foregroundPrimary(for: colorScheme))
                    .padding(.horizontal, SymairaMetrics.contentActionHorizontalPadding)
                    .frame(minHeight: SymairaMetrics.contentActionHeight),
                shape: shape,
                isPressed: configuration.isPressed
            )
            .contentShape(shape)
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.98 : 1)
            .opacity(isEnabled ? 1 : 0.5)
            .animation(reduceMotion ? nil : .easeOut(duration: 0.15), value: configuration.isPressed)
        }
        .onChange(of: configuration.isPressed) { _, isPressed in onPressChange?(isPressed) }
    }

    @ViewBuilder
    private func surface(
        _ label: some View, shape: Capsule, isPressed: Bool
    ) -> some View {
        #if compiler(>=6.2)
        if #available(macOS 26.0, iOS 26.0, tvOS 26.0, *), allowsGlass, !reduceTransparency {
            label.glassEffect(.regular.interactive(isEnabled), in: shape)
        } else {
            opaque(label, shape: shape, isPressed: isPressed)
        }
        #else
        opaque(label, shape: shape, isPressed: isPressed)
        #endif
    }

    private func opaque(_ label: some View, shape: Capsule, isPressed: Bool) -> some View {
        label
            .background(
                isPressed
                    ? SymairaTheme.navigationSelection(for: colorScheme)
                    : SymairaTheme.surfaceRaised(for: colorScheme),
                in: shape
            )
            .overlay(shape.stroke(SymairaTheme.raisedOutline(for: colorScheme), lineWidth: 1))
    }
}
