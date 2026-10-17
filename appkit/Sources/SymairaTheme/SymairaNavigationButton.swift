import SwiftUI

/// Navigation geometry and accessibility shared by Cockpit-style workspaces.
/// The product owns destination identity, selected state and activation.
public struct SymairaNavigationButton: View {
    private let title: String
    private let systemImage: String
    private let isSelected: Bool
    private let showsLabel: Bool
    private let action: () -> Void
    @FocusState private var isFocused: Bool

    public init(
        _ title: String, systemImage: String, isSelected: Bool,
        showsLabel: Bool = true, action: @escaping () -> Void
    ) {
        self.title = title
        self.systemImage = systemImage
        self.isSelected = isSelected
        self.showsLabel = showsLabel
        self.action = action
    }

    public var body: some View {
        let shape = RoundedRectangle(cornerRadius: SymairaRadius.control)
        Button(action: action) {
            HStack(spacing: SymairaSpacing.medium) {
                Image(systemName: systemImage)
                    .font(.system(size: 16, weight: SymairaTokens.iconWeight))
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
