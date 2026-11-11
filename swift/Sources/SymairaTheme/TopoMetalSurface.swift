#if os(macOS)
import AppKit
import SwiftUI

/// No SwiftUI state or hosting view participates in the native frame loop.
struct TopoMetalSurface: NSViewRepresentable {
    let model: SymairaTopoModel
    let origin: CGPoint
    let scheme: ColorScheme
    let still: Bool
    let visible: Bool

    func makeNSView(context: Context) -> TopoMetalView { TopoMetalView() }
    func updateNSView(_ view: TopoMetalView, context: Context) {
        view.configure(model: model, origin: origin, scheme: scheme, still: still, visible: visible)
    }
    static func dismantleNSView(_ view: TopoMetalView, coordinator: ()) { view.stop() }
}

@MainActor
final class TopoMetalView: NSView {
    private let driver = TopoMetalDriver()
    private var timer: Timer?
    var framesDrawn: Int { driver.framesDrawn }
    private var metalLayer: CAMetalLayer { layer as! CAMetalLayer }
    override var isFlipped: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
    override func makeBackingLayer() -> CALayer { CAMetalLayer() }

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        driver.attach(metalLayer)
        driver.onRefresh = { [weak self] in self?.refresh() }
    }
    convenience init() { self.init(frame: .zero) }
    required init?(coder: NSCoder) { nil }

    func configure(model: SymairaTopoModel, origin: CGPoint, scheme: ColorScheme, still: Bool, visible: Bool) {
        driver.configure(model: model, origin: origin, scheme: scheme, still: still, visible: visible)
    }

    private func refresh() {
        guard !driver.stopped else { return }
        driver.observeInputs()
        timer?.invalidate()
        timer = nil
        if TopoFramePacing.runsFrameLoop(paused: driver.paused, hasWindow: window != nil) {
            let fps = TopoFramePacing.framesPerSecond(
                interactive: driver.interactive, displayMaximum: window?.screen?.maximumFramesPerSecond ?? 60)
            let timer = Timer(timeInterval: 1 / fps, repeats: true) { [weak self] _ in
                MainActor.assumeIsolated { self?.drawFrame() }
            }
            RunLoop.main.add(timer, forMode: .common)
            self.timer = timer
        }
        drawFrame()
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        driver.resetClock()
        refresh()
    }
    override func viewDidChangeBackingProperties() {
        super.viewDidChangeBackingProperties()
        drawFrame()
    }
    override func layout() {
        super.layout()
        drawFrame()
    }

    func drawFrame() {
        driver.draw(on: metalLayer, size: bounds.size, scale: window?.backingScaleFactor ?? 1)
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        driver.stop(layer: metalLayer)
    }
}
#endif
