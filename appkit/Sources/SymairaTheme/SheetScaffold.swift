import SwiftUI

/// Heading, scrolling form content and a stable secondary/primary action footer.
/// The caller owns presentation, validation and any asynchronous task lifecycle.
public struct SymairaSheetScaffold<Content: View>: View {
    private let title: String
    private let dismissTitle: String
    private let dismiss: () -> Void
    private let primaryTitle: String?
    private let primaryDisabled: Bool
    private let primary: () -> Void
    private let content: Content

    public init(
        title: String, dismissTitle: String = "Cancel", dismiss: @escaping () -> Void,
        primaryTitle: String? = nil, primaryDisabled: Bool = false,
        primary: @escaping () -> Void = {}, @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.dismissTitle = dismissTitle
        self.dismiss = dismiss
        self.primaryTitle = primaryTitle
        self.primaryDisabled = primaryDisabled
        self.primary = primary
        self.content = content()
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: SymairaSpacing.medium) {
                Text(title)
                    .symairaText(.heading)
                    .foregroundStyle(SymairaTokens.ink)
                    .accessibilityAddTraits(.isHeader)
                Spacer()
                SymairaIconButton("Close", icon: .close, action: dismiss)
                    .frame(
                        minWidth: SymairaMetrics.minimumControlHeight, minHeight: SymairaMetrics.minimumControlHeight
                    )
                    .accessibilityIdentifier("symaira.sheet.close")
            }
            .padding(SymairaSpacing.xLarge)
            ScrollView {
                VStack(alignment: .leading, spacing: SymairaSpacing.large) { content }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, SymairaSpacing.xLarge)
                    .padding(.bottom, SymairaSpacing.large)
            }
            Divider().overlay(SymairaTokens.line)
            HStack(spacing: SymairaSpacing.medium) {
                Spacer()
                Button(dismissTitle, action: dismiss)
                    .symairaButtonStyle(.secondary)
                    .keyboardShortcut(.cancelAction)
                    .accessibilityIdentifier("symaira.sheet.dismiss")
                if let primaryTitle {
                    Button(primaryTitle, action: primary)
                        .symairaButtonStyle(.primary)
                        .keyboardShortcut(.defaultAction)
                        .disabled(primaryDisabled)
                        .accessibilityIdentifier("symaira.sheet.primary")
                }
            }
            .padding(SymairaSpacing.large)
        }
        .background(SymairaTokens.surface)
    }
}
