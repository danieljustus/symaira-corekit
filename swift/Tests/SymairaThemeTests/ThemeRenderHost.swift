import AppKit
import SwiftUI

/// Renders a SwiftUI view in an offscreen AppKit window so its body is
/// evaluated with a live environment — Canvas closures run, `@Environment`
/// reads resolve, button styles execute `makeBody`, and layout/drawing pass
/// actually happen. This is how the Symaira design-system components are
/// exercised without a third-party inspection library (issue #48).
@MainActor
enum ThemeRenderHost {
    /// Windows are retained for the lifetime of the test process so the
    /// rendered views stay attached and keep their render state.
    private static var retainedWindows: [NSWindow] = []

    @discardableResult
    static func render<V: View>(
        _ view: V,
        size: CGSize = CGSize(width: 480, height: 360)
    ) -> NSHostingView<V> {
        _ = NSApplication.shared
        let hosting = NSHostingView(rootView: view)
        hosting.frame = NSRect(origin: .zero, size: size)
        let window = NSWindow(
            contentRect: NSRect(origin: .zero, size: size),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        window.contentView = hosting
        window.layoutIfNeeded()
        hosting.layoutSubtreeIfNeeded()
        hosting.displayIfNeeded()
        retainedWindows.append(window)
        return hosting
    }
}
