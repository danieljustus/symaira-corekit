import SwiftUI

/// One dashboard summary value: the figure in ``SymairaTypography/stat``, its
/// label beneath and an optional one-line detail (LAYOUT-8).
///
/// By default the tile is an opaque `.symairaCard()` with full topography
/// protection, for tiles that sit directly on the page (an overview row). Pass
/// `showsCard: false` when the tile is placed inside a card or sheet that
/// already provides the surface.
///
/// A tile without `detail` keeps the line reserved, so tiles in one row share
/// one height. VoiceOver reads one element: the label, then the value (and the
/// detail when present).
@available(
    *, deprecated,
    message:
        "Use Gauge(value:) with currentValueLabel for bounded values, LabeledContent otherwise, E33 (UI catalog 2026-11-25)."
)
public struct SymairaStatTile: View {
    private let value: String
    private let label: String
    private let detail: String?
    private let showsCard: Bool

    /// - Parameters:
    ///   - value: The figure, already formatted ("42", "3 of 5", "12:04").
    ///   - label: What the figure counts, in Title Case ("Profiles").
    ///   - detail: Optional one-line caption under the label.
    ///   - showsCard: Draws the opaque card surface. Default `true`.
    public init(value: String, label: String, detail: String? = nil, showsCard: Bool = true) {
        self.value = value
        self.label = label
        self.detail = detail
        self.showsCard = showsCard
    }

    public var body: some View {
        if showsCard {
            content
                .symairaCard()
                .topoProtected(hill: true)
        } else {
            content
        }
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: SymairaSpacing.xSmall) {
            Text(verbatim: value)
                .font(SymairaTypography.stat)
                .foregroundStyle(SymairaTokens.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text(verbatim: label)
                .symairaText(.secondary)
            Text(verbatim: detail ?? " ")
                .symairaText(.caption)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(label)
        .accessibilityValue(accessibilityValue)
    }

    private var accessibilityValue: String {
        guard let detail, !detail.isEmpty else { return value }
        return "\(value), \(detail)"
    }
}
