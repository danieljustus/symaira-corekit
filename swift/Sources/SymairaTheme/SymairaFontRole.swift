import SwiftUI

/// A font recipe resolved by the receiving view, not a cached point-sized `Font`.
/// Apply with `.font(SymairaTypography.body)` or `.symairaText(.body)`.
/// Unlike `Text.font(Font)`, the role overload returns a `View`, not a `Text`.
public struct SymairaFontRole: Hashable, Sendable {
    enum Source: Hashable, Sendable {
        case bundled(family: SymairaFont.Family, size: CGFloat, weight: Double, relativeTo: Font.TextStyle)
        case system(Font)
    }

    let source: Source
    private(set) var tabularDigits = false
    /// Line height of wrapped text as a multiple of the point size (DESIGN.md `lineHeight`);
    /// `nil` keeps the typeface's own line height.
    private(set) var lineHeight: CGFloat?

    /// Uses equal-width digits without changing the typeface or scaling curve.
    public func monospacedDigit() -> Self {
        var result = self
        result.tabularDigits = true
        return result
    }

    /// Sets the line height of wrapped text; single lines keep their height.
    func lineHeight(_ multiple: CGFloat) -> Self {
        var result = self
        result.lineHeight = multiple
        return result
    }
}

private struct SymairaBrandFontModifier: ViewModifier {
    #if os(iOS)
    @ScaledMetric private var scaledSize: CGFloat
    #endif
    private let family: SymairaFont.Family
    private let size: CGFloat
    private let weight: Double
    private let tabularDigits: Bool
    private let lineHeight: CGFloat?

    nonisolated init(
        family: SymairaFont.Family, size: CGFloat, weight: Double, relativeTo textStyle: Font.TextStyle,
        tabularDigits: Bool, lineHeight: CGFloat? = nil
    ) {
        self.family = family
        self.size = size
        self.weight = weight
        self.tabularDigits = tabularDigits
        self.lineHeight = lineHeight
        #if os(iOS)
        _scaledSize = ScaledMetric(wrappedValue: size * SymairaMetrics.textScale, relativeTo: textStyle)
        #endif
    }

    func body(content: Content) -> some View {
        #if os(iOS)
        let pointSize = scaledSize
        #else
        let pointSize = size * SymairaMetrics.textScale
        #endif
        let font = SymairaFont.resolvedFont(size: pointSize, weight: weight, family: family)
        let styled = content.font(tabularDigits ? font.monospacedDigit() : font)
        // A role without a line height leaves a surrounding `.lineSpacing` alone.
        if lineHeight != nil {
            styled.lineSpacing(Self.extraLeading(pointSize: pointSize, lineHeight: lineHeight, family: family))
        } else {
            styled
        }
    }

    /// Spacing added between wrapped lines so they sit `lineHeight` times the point size apart.
    nonisolated static func extraLeading(pointSize: CGFloat, lineHeight: CGFloat?, family: SymairaFont.Family)
        -> CGFloat
    {
        guard let lineHeight else { return 0 }
        return max(0, pointSize * (lineHeight - family.naturalLineHeight))
    }
}

extension View {
    /// Resolves a Symaira font role against this view's live Dynamic Type environment.
    /// Keeps the fixed optical-size axis and also scales the missing-font fallback.
    @ViewBuilder
    nonisolated public func font(_ role: SymairaFontRole) -> some View {
        switch role.source {
        case .bundled(let family, let size, let weight, let textStyle):
            modifier(
                SymairaBrandFontModifier(
                    family: family, size: size, weight: weight, relativeTo: textStyle,
                    tabularDigits: role.tabularDigits,
                    lineHeight: role.lineHeight
                ))
        case .system(let font):
            self.font(role.tabularDigits ? font.monospacedDigit() : font)
        }
    }
}
