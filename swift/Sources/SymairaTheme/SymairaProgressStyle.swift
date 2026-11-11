import SwiftUI

/// Neutral tracks/fills shared by native sliders and SwiftUI meters. Semantic
/// warnings belong in accompanying text/icons, not a second meter palette.
///
/// The track is a quiet groove, not a bright bar: `raised` with a 1 pt `line`
/// outline reads as empty on `surface` and `canvas` in both appearances, while
/// the `ink` fill is the only element that reads as progress. `ink3` is a text
/// role and is too bright for a rail (an empty meter looked completely filled).
public enum SymairaBarColors {
    /// Empty groove of a meter or slider rail. Pair it with ``trackOutline``.
    public static let track = SymairaTokens.raised
    /// 1 pt outline of the groove; keeps it visible where `raised` equals the
    /// background (light appearance on `canvas`).
    public static let trackOutline = SymairaTokens.line
    public static let fill = SymairaTokens.ink
}

/// Determinate, neutral meter. Native linear progress styles do not reliably
/// honor tint. A missing fraction displays an empty track, not simulated progress.
public struct SymairaProgressStyle: ProgressViewStyle {
    private let height: CGFloat
    private let track: Color
    @Environment(\.isEnabled) private var isEnabled

    /// - Parameters:
    ///   - height: Meter thickness in points.
    ///   - track: Fill of the empty groove; defaults to ``SymairaBarColors/track``.
    ///     The 1 pt ``SymairaBarColors/trackOutline`` is always drawn.
    public init(height: CGFloat = 8, track: Color = SymairaBarColors.track) {
        self.height = height
        self.track = track
    }

    public func makeBody(configuration: Configuration) -> some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                Capsule().fill(track)
                Capsule().fill(SymairaBarColors.fill)
                    .frame(width: geometry.size.width * min(1, max(0, configuration.fractionCompleted ?? 0)))
                Capsule().strokeBorder(SymairaBarColors.trackOutline, lineWidth: 1)
            }
        }
        .frame(height: height)
        .opacity(isEnabled ? 1 : 0.4)
    }
}
