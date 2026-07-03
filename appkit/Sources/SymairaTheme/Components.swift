import SwiftUI

// MARK: - Blueprint Background Grid

public struct BlueprintGrid: View {
    public init() {}
    public var body: some View {
        GeometryReader { geo in
            Path { path in
                let spacing: CGFloat = 30
                var y: CGFloat = 0
                while y < geo.size.height {
                    path.move(to: CGPoint(x: 0, y: y))
                    path.addLine(to: CGPoint(x: geo.size.width, y: y))
                    y += spacing
                }
                var x: CGFloat = 0
                while x < geo.size.width {
                    path.move(to: CGPoint(x: x, y: 0))
                    path.addLine(to: CGPoint(x: x, y: geo.size.height))
                    x += spacing
                }
            }
            .stroke(Color.white.opacity(0.015), lineWidth: 0.5)
        }
    }
}

// MARK: - Ambient Glows Background

public struct AmbientGlows: View {
    public init() {}
    public var body: some View {
        ZStack {
            Circle()
                .fill(SymairaTheme.goldPrimary.opacity(0.04))
                .frame(width: 450, height: 450)
                .blur(radius: 90)
                .offset(x: -200, y: -200)

            Circle()
                .fill(SymairaTheme.goldSecondary.opacity(0.03))
                .frame(width: 550, height: 550)
                .blur(radius: 110)
                .offset(x: 250, y: 250)
        }
    }
}

// MARK: - Telemetry Corners

public struct TelemetryCorners: View {
    var color: Color
    var length: CGFloat
    var lineWidth: CGFloat

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
        GeometryReader { geo in
            Path { path in
                // Top-Left
                path.move(to: CGPoint(x: 0, y: length))
                path.addLine(to: CGPoint(x: 0, y: 0))
                path.addLine(to: CGPoint(x: length, y: 0))
                // Top-Right
                path.move(to: CGPoint(x: geo.size.width - length, y: 0))
                path.addLine(to: CGPoint(x: geo.size.width, y: 0))
                path.addLine(to: CGPoint(x: geo.size.width, y: length))
                // Bottom-Left
                path.move(to: CGPoint(x: 0, y: geo.size.height - length))
                path.addLine(to: CGPoint(x: 0, y: geo.size.height))
                path.addLine(to: CGPoint(x: length, y: geo.size.height))
                // Bottom-Right
                path.move(to: CGPoint(x: geo.size.width - length, y: geo.size.height))
                path.addLine(to: CGPoint(x: geo.size.width, y: geo.size.height))
                path.addLine(to: CGPoint(x: geo.size.width, y: geo.size.height - length))
            }
            .stroke(color, lineWidth: lineWidth)
        }
    }
}

// MARK: - Glassmorphic Panel

public struct GlassmorphicPanelModifier: ViewModifier {
    var cornerRadius: CGFloat
    var addCorners: Bool

    public init(cornerRadius: CGFloat = 12, addCorners: Bool = true) {
        self.cornerRadius = cornerRadius
        self.addCorners = addCorners
    }

    public func body(content: Content) -> some View {
        content
            .background(SymairaTheme.bgCard)
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(SymairaTheme.borderGlass, lineWidth: 1)
            )
            .overlay(
                Group {
                    if addCorners {
                        TelemetryCorners()
                    }
                }
            )
            .cornerRadius(cornerRadius)
            .shadow(color: Color.black.opacity(0.35), radius: 12, x: 0, y: 6)
    }
}

// MARK: - Glass Card (hoverable)

public struct GlassCardModifier: ViewModifier {
    var isHovered: Bool

    public init(isHovered: Bool = false) {
        self.isHovered = isHovered
    }

    public func body(content: Content) -> some View {
        content
            .background(isHovered ? SymairaTheme.bgCardHover : SymairaTheme.bgCard)
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(
                        isHovered ? SymairaTheme.borderGlassHover : SymairaTheme.borderGlass,
                        lineWidth: 1.2
                    )
            )
            .shadow(color: Color.black.opacity(0.4), radius: 10, x: 0, y: 5)
    }
}

extension View {
    public func glassmorphicPanel(cornerRadius: CGFloat = 12, addCorners: Bool = true) -> some View {
        modifier(GlassmorphicPanelModifier(cornerRadius: cornerRadius, addCorners: addCorners))
    }

    public func glassCard(isHovered: Bool = false) -> some View {
        modifier(GlassCardModifier(isHovered: isHovered))
    }
}

// MARK: - Button Styles

public struct SymairaPrimaryButtonStyle: ButtonStyle {
    public init() {}
    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline.weight(.semibold))
            .foregroundColor(.black)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(
                LinearGradient(
                    colors: [SymairaTheme.goldPrimary, SymairaTheme.goldSecondary],
                    startPoint: .leading,
                    endPoint: .trailing
                )
            )
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.white.opacity(0.15), lineWidth: 1)
            )
            .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
            .animation(.easeOut(duration: 0.15), value: configuration.isPressed)
            .shadow(
                color: SymairaTheme.goldPrimary.opacity(0.25),
                radius: configuration.isPressed ? 4 : 8,
                x: 0,
                y: 2
            )
    }
}

public struct SymairaSecondaryButtonStyle: ButtonStyle {
    public init() {}
    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline.weight(.medium))
            .foregroundColor(SymairaTheme.textPrimary)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(Color.white.opacity(0.04))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(SymairaTheme.borderGlass, lineWidth: 1)
            )
            .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
            .animation(.easeOut(duration: 0.15), value: configuration.isPressed)
    }
}
