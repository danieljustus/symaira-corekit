import SwiftUI

/// Navigation geometry and accessibility shared by Cockpit-style workspaces.
/// The product owns destination identity, selected state and activation.
public struct SymairaNavigationButton: View {
    private let title: String
    private let glyph: SymairaGlyph
    private let isSelected: Bool
    private let showsLabel: Bool
    private let action: () -> Void
    @FocusState private var isFocused: Bool

    /// Symaira icon; it plays its click motion when the destination becomes selected.
    public init(
        _ title: String, icon: SymairaIcon, isSelected: Bool,
        showsLabel: Bool = true, action: @escaping () -> Void
    ) {
        self.init(title, glyph: .symaira(icon), isSelected: isSelected, showsLabel: showsLabel, action: action)
    }

    public init(
        _ title: String, systemImage: String, isSelected: Bool,
        showsLabel: Bool = true, action: @escaping () -> Void
    ) {
        self.init(title, glyph: .system(systemImage), isSelected: isSelected, showsLabel: showsLabel, action: action)
    }

    private init(
        _ title: String, glyph: SymairaGlyph, isSelected: Bool, showsLabel: Bool, action: @escaping () -> Void
    ) {
        self.title = title
        self.glyph = glyph
        self.isSelected = isSelected
        self.showsLabel = showsLabel
        self.action = action
    }

    public var body: some View {
        let shape = RoundedRectangle(cornerRadius: SymairaRadius.control)
        Button(action: action) {
            HStack(spacing: SymairaSpacing.medium) {
                SymairaGlyphView(glyph: glyph, size: 20, trigger: isSelected)
                    .frame(width: 24)
                    .accessibilityHidden(true)
                if showsLabel {
                    Text(title)
                        .symairaText(isSelected ? .subheading : .body, respectsForeground: false)
                        .lineLimit(1)
                    Spacer(minLength: 0)
                }
            }
            .frame(minHeight: 44)
            .padding(.horizontal, SymairaSpacing.medium)
            .contentShape(shape)
            .accessibilityElement(children: .ignore)
        }
        .buttonStyle(SymairaNavigationButtonStyle(isSelected: isSelected))
        .focused($isFocused)
        .overlay {
            if isFocused {
                shape.stroke(SymairaTokens.focus, lineWidth: 2).padding(-2)
            }
        }
        .accessibilityLabel(title)
        .accessibilityAddTraits(isSelected ? [.isButton, .isSelected] : [.isButton])
        .help(title)
    }
}
