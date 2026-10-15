import SwiftUI

/// A font recipe resolved by the receiving view, not a cached point-sized `Font`.
/// Apply with `.font(SymairaTypography.body)` or `.symairaText(.body)`.
/// Unlike `Text.font(Font)`, the role overload returns a `View`, not a `Text`.
public struct SymairaFontRole: Hashable, Sendable {
    enum Source: Hashable, Sendable {
        case brand(size: CGFloat, weight: Double, relativeTo: Font.TextStyle)
        case system(Font)
    }

    let source: Source
    private(set) var tabularDigits = false

    /// Uses equal-width digits without changing the typeface or scaling curve.
    public func monospacedDigit() -> Self {
        var result = self
        result.tabularDigits = true
        return result
    }
}

private struct SymairaBrandFontModifier: ViewModifier {
    #if os(iOS)
    @ScaledMetric private var scaledSize: CGFloat
    #endif
    private let size: CGFloat
    private let weight: Double
    private let tabularDigits: Bool

    nonisolated init(size: CGFloat, weight: Double, relativeTo textStyle: Font.TextStyle, tabularDigits: Bool) {
        self.size = size
        self.weight = weight
        self.tabularDigits = tabularDigits
        #if os(iOS)
        _scaledSize = ScaledMetric(wrappedValue: size, relativeTo: textStyle)
        #endif
    }

    func body(content: Content) -> some View {
        #if os(iOS)
        let pointSize = scaledSize
        #else
        let pointSize = size
        #endif
        let font = SymairaFont.resolvedFont(size: pointSize, weight: weight)
        content.font(tabularDigits ? font.monospacedDigit() : font)
    }
}

extension View {
    /// Resolves a Symaira font role against this view's live Dynamic Type environment.
    /// Keeps the fixed optical-size axis and also scales the missing-font fallback.
    @ViewBuilder
    nonisolated public func font(_ role: SymairaFontRole) -> some View {
        switch role.source {
        case .brand(let size, let weight, let textStyle):
            modifier(
                SymairaBrandFontModifier(
                    size: size, weight: weight, relativeTo: textStyle, tabularDigits: role.tabularDigits))
        case .system(let font):
            self.font(role.tabularDigits ? font.monospacedDigit() : font)
        }
    }
}
