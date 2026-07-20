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
        if #available(macOS 26.0, iOS 26.0, *) {
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
        return content
            .background(SymairaTheme.surfaceOpaque(for: colorScheme), in: shape)
            .overlay(shape.stroke(fallbackBorder, lineWidth: contrast == .increased ? 1.5 : 1))
    }

    private func materialFallback(_ content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        return content
            .background(.ultraThinMaterial, in: shape)
            .background((tint ?? .clear).opacity(0.10), in: shape)
            .overlay(shape.stroke(fallbackBorder, lineWidth: contrast == .increased ? 1.5 : 1))
    }

    private var fallbackBorder: Color {
        contrast == .increased
            ? SymairaTheme.goldPrimary.opacity(0.45)
            : SymairaTheme.borderGlass
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
        if #available(macOS 26.0, iOS 26.0, *) {
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

// MARK: - Buttons

public enum SymairaButtonRole: Sendable {
    case primary
    case secondary
    case toolbar
}

/// Preferred button API. It adopts Apple's native Liquid Glass button styles
/// on macOS/iOS 26 and preserves the Symaira appearance on older systems.
public struct SymairaAdaptiveButtonModifier: ViewModifier {
    private let role: SymairaButtonRole

    public init(role: SymairaButtonRole) {
        self.role = role
    }

    @ViewBuilder
    public func body(content: Content) -> some View {
        #if compiler(>=6.2)
        if #available(macOS 26.0, iOS 26.0, *) {
            switch role {
            case .primary:
                content
                    .buttonStyle(.glassProminent)
                    .tint(SymairaTheme.goldPrimary)
            case .secondary, .toolbar:
                content
                    .buttonStyle(.glass)
                    .tint(role == .secondary ? SymairaTheme.goldPrimary : nil)
            }
        } else {
            legacyButton(content)
        }
        #else
        legacyButton(content)
        #endif
    }

    @ViewBuilder
    private func legacyButton(_ content: Content) -> some View {
        switch role {
        case .primary:
            content.buttonStyle(SymairaPrimaryButtonStyle())
        case .secondary:
            content.buttonStyle(SymairaSecondaryButtonStyle())
        case .toolbar:
            content.buttonStyle(.borderless)
        }
    }
}

extension View {
    public func symairaButtonStyle(_ role: SymairaButtonRole) -> some View {
        modifier(SymairaAdaptiveButtonModifier(role: role))
    }
}

public struct SymairaPrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init() {}

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body.weight(.semibold))
            .foregroundStyle(Color.black.opacity(isEnabled ? 0.88 : 0.55))
            .padding(.horizontal, SymairaSpacing.large)
            .frame(minHeight: SymairaMetrics.minimumControlHeight)
            .background(
                LinearGradient(
                    colors: [SymairaTheme.goldPrimary, SymairaTheme.goldSecondary],
                    startPoint: .leading,
                    endPoint: .trailing
                ),
                in: RoundedRectangle(cornerRadius: SymairaRadius.control, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: SymairaRadius.control, style: .continuous)
                    .stroke(Color.white.opacity(0.18), lineWidth: 1)
            )
            .contentShape(RoundedRectangle(cornerRadius: SymairaRadius.control, style: .continuous))
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.97 : 1)
            .opacity(isEnabled ? 1 : 0.55)
            .animation(reduceMotion ? nil : .easeOut(duration: 0.15), value: configuration.isPressed)
            .shadow(
                color: SymairaTheme.goldPrimary.opacity(isEnabled ? 0.20 : 0),
                radius: configuration.isPressed ? 4 : 8,
                x: 0,
                y: 2
            )
    }
}

public struct SymairaSecondaryButtonStyle: ButtonStyle {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    public init() {}

    public func makeBody(configuration: Configuration) -> some View {
        let shape = RoundedRectangle(cornerRadius: SymairaRadius.control, style: .continuous)
        configuration.label
            .font(.body.weight(.medium))
            .foregroundStyle(SymairaTheme.foregroundPrimary(for: colorScheme))
            .padding(.horizontal, SymairaSpacing.large)
            .frame(minHeight: SymairaMetrics.minimumControlHeight)
            .background {
                if reduceTransparency {
                    shape.fill(SymairaTheme.surfaceOpaque(for: colorScheme))
                } else {
                    shape.fill(.ultraThinMaterial)
                }
            }
            .overlay(shape.stroke(SymairaTheme.borderGlass, lineWidth: 1))
            .contentShape(shape)
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.97 : 1)
            .opacity(isEnabled ? 1 : 0.5)
            .animation(reduceMotion ? nil : .easeOut(duration: 0.15), value: configuration.isPressed)
    }
}
