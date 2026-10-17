#if os(macOS)
import AppKit
import SwiftUI

/// Shared layout policy, not navigation or product state. Width changes never
/// replace the workspace's content. A toolbar toggle retains the chosen width.
public struct SymairaSidebarState {
    public static let compactWidth: CGFloat = 64
    public static let minimumWidth: CGFloat = 224
    public static let contentReserve: CGFloat = 568
    public internal(set) var availableWidth: CGFloat = 1080
    public private(set) var preferredWidth: CGFloat = 272
    public var expanded = true

    public init() {}

    public var canExpand: Bool { availableWidth >= Self.minimumWidth + Self.contentReserve }
    public var showsLabels: Bool { expanded && canExpand }
    public var maximumWidth: CGFloat { max(Self.minimumWidth, min(360, availableWidth - Self.contentReserve)) }
    public var width: CGFloat { showsLabels ? min(preferredWidth, maximumWidth) : Self.compactWidth }

    public mutating func resize(to proposed: CGFloat) {
        guard canExpand, proposed.isFinite else { return }
        // Snap between the icon rail and readable labels, not clipped half-labels.
        expanded = proposed >= (Self.compactWidth + Self.minimumWidth) / 2
        if expanded { preferredWidth = min(max(proposed, Self.minimumWidth), maximumWidth) }
    }

    mutating func step(_ direction: Int) {
        if direction < 0, width <= Self.minimumWidth {
            resize(to: Self.compactWidth)
        } else if direction > 0, !showsLabels {
            resize(to: Self.minimumWidth)
        } else {
            resize(to: width + CGFloat(direction) * 16)
        }
    }
}

/// Toolbar/keyboard alternative to dragging. Put in a navigation ToolbarItem.
public struct SymairaSidebarToggle: View {
    @Binding private var sidebar: SymairaSidebarState

    public init(sidebar: Binding<SymairaSidebarState>) { _sidebar = sidebar }

    public var body: some View {
        Button {
            sidebar.expanded.toggle()
        } label: {
            Image(systemName: "sidebar.left")
        }
        .disabled(!sidebar.canExpand)
        .accessibilityLabel(sidebar.showsLabels ? "Collapse sidebar" : "Expand sidebar")
        .help(sidebar.canExpand ? "Toggle sidebar (⌃⌘S)" : "Sidebar is compact at this window width")
        .keyboardShortcut("s", modifiers: [.control, .command])
    }
}

/// A native hit target on the existing panel edge keeps one hosting root and
/// its shared scroll/toolbar environment. Cursor rects need no global monitor.
struct SymairaSidebarResizeHandle: NSViewRepresentable {
    let width: CGFloat
    let isEnabled: Bool
    let onResize: (CGFloat) -> Void
    let onStep: (Int) -> Void

    func makeNSView(context: Context) -> Handle {
        let view = Handle()
        view.setAccessibilityElement(true)
        view.setAccessibilityRole(.splitter)
        view.setAccessibilityLabel("Resize sidebar")
        view.setAccessibilityIdentifier("symaira-sidebar-resize")
        view.setAccessibilityOrientation(.vertical)
        view.toolTip = "Drag to resize or collapse the sidebar. Arrow keys adjust its width."
        return view
    }

    func updateNSView(_ view: Handle, context: Context) {
        view.sidebarWidth = width
        view.enabled = isEnabled
        view.onResize = onResize
        view.onStep = onStep
        view.setAccessibilityValue(Int(width))
        view.setAccessibilityEnabled(isEnabled)
    }

    final class Handle: NSView {
        var sidebarWidth: CGFloat = 272
        var enabled = true {
            didSet { if enabled != oldValue { window?.invalidateCursorRects(for: self) } }
        }
        var onResize: ((CGFloat) -> Void)?
        var onStep: ((Int) -> Void)?
        private var dragOrigin: (x: CGFloat, width: CGFloat)?

        override var acceptsFirstResponder: Bool { enabled }
        override func acceptsFirstMouse(for event: NSEvent?) -> Bool { enabled }
        override func resetCursorRects() {
            if enabled { addCursorRect(bounds, cursor: .resizeLeftRight) }
        }
        override func mouseDown(with event: NSEvent) {
            guard enabled else { return }
            window?.makeFirstResponder(self)
            dragOrigin = (event.locationInWindow.x, sidebarWidth)
        }
        override func mouseDragged(with event: NSEvent) {
            guard enabled, let start = dragOrigin else { return }
            // Window coordinates stay fixed as the handle itself moves.
            onResize?(start.width + event.locationInWindow.x - start.x)
        }
        override func mouseUp(with event: NSEvent) {
            if dragOrigin != nil { mouseDragged(with: event) }
            dragOrigin = nil
        }
        override func keyDown(with event: NSEvent) {
            switch event.keyCode {
            case 123: _ = accessibilityPerformDecrement()
            case 124: _ = accessibilityPerformIncrement()
            default: super.keyDown(with: event)
            }
        }
        override func accessibilityPerformIncrement() -> Bool {
            guard enabled else { return false }
            onStep?(1)
            return true
        }
        override func accessibilityPerformDecrement() -> Bool {
            guard enabled else { return false }
            onStep?(-1)
            return true
        }
    }
}
#endif
