import SwiftUI

/// Neutral tracks/fills shared by native sliders and SwiftUI meters. Semantic
/// warnings belong in accompanying text/icons, not a second meter palette.
public enum SymairaBarColors {
    public static let track = SymairaTokens.ink3
    public static let fill = SymairaTokens.ink
}

/// Determinate, neutral meter. Native linear progress styles do not reliably
/// honor tint. A missing fraction displays an empty track, not simulated progress.
public struct SymairaProgressStyle: ProgressViewStyle {
    private let height: CGFloat
    @Environment(\.isEnabled) private var isEnabled

    public init(height: CGFloat = 8) { self.height = height }

    public func makeBody(configuration: Configuration) -> some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                Capsule().fill(SymairaBarColors.track)
                Capsule().fill(SymairaBarColors.fill)
                    .frame(width: geometry.size.width * min(1, max(0, configuration.fractionCompleted ?? 0)))
            }
        }
        .frame(height: height)
        .opacity(isEnabled ? 1 : 0.4)
    }
}
