#if canImport(UIKit)
import QuartzCore
import SwiftUI
import UIKit

/// iOS/tvOS counterpart of the macOS `TopoMetalSurface`: a `CAMetalLayer` view
/// driven by a `CADisplayLink`, so frames never update the SwiftUI graph (no
/// `TimelineView` tick, no `Shader` rebuilt per frame). Frame integration,
/// input observation and pause rules live in the shared `TopoMetalDriver`.
struct TopoMetalSurface: UIViewRepresentable {
    let model: SymairaTopoModel
    let origin: CGPoint
    let scheme: ColorScheme
    let still: Bool
    let visible: Bool

    func makeUIView(context: Context) -> TopoMetalView { TopoMetalView() }
    func updateUIView(_ view: TopoMetalView, context: Context) {
        view.configure(model: model, origin: origin, scheme: scheme, still: still, visible: visible)
    }
    static func dismantleUIView(_ view: TopoMetalView, coordinator: ()) { view.stop() }
}

/// `CADisplayLink` retains its target. This proxy holds the view weakly, so the
/// view can be released without first invalidating the link; a link whose
/// view is gone invalidates itself on the next tick.
@MainActor
private final class TopoDisplayLinkProxy: NSObject {
    weak var target: TopoMetalView?
    @objc func tick(_ link: CADisplayLink) {
        guard let target else {
            link.invalidate()
            return
        }
        target.tick()
    }
}

@MainActor
final class TopoMetalView: UIView {
    override class var layerClass: AnyClass { CAMetalLayer.self }

    private let driver = TopoMetalDriver()
    private var displayLink: CADisplayLink?
    /// Whether the scheduled link runs at the display maximum rather than the idle cap.
    private var fastRate = false
    var framesDrawn: Int { driver.framesDrawn }
    /// Whether a display link is currently scheduled (test hook).
    var isDrawing: Bool { displayLink != nil }
    /// Whether the scheduled link asks for the display maximum (test hook).
    var isFast: Bool { displayLink != nil && fastRate }
    private var metalLayer: CAMetalLayer { layer as! CAMetalLayer }

    override init(frame: CGRect) {
        super.init(frame: frame)
        isOpaque = false
        backgroundColor = .clear
        isUserInteractionEnabled = false
        isAccessibilityElement = false
        driver.attach(metalLayer)
        driver.onRefresh = { [weak self] in self?.refresh() }
        driver.onRedraw = { [weak self] in self?.drawFrame() }
    }
    convenience init() { self.init(frame: .zero) }
    required init?(coder: NSCoder) { nil }

    func configure(model: SymairaTopoModel, origin: CGPoint, scheme: ColorScheme, still: Bool, visible: Bool) {
        driver.configure(model: model, origin: origin, scheme: scheme, still: still, visible: visible)
    }

    private var screenScale: CGFloat {
        let scale = window?.screen.scale ?? traitCollection.displayScale
        return scale > 0 ? scale : 1
    }

    private func refresh() {
        guard !driver.stopped else { return }
        driver.observeInputs()
        if TopoFramePacing.runsFrameLoop(paused: driver.paused, hasWindow: window != nil) {
            schedule(fast: currentlyFast)
        } else {
            invalidateDisplayLink()
        }
        drawFrame()
    }

    private var currentlyFast: Bool {
        TopoFramePacing.runsAtDisplayRate(interactive: driver.interactive, rippling: driver.rippling)
    }

    private func schedule(fast: Bool) {
        let rate = TopoFramePacing.rate(
            interactive: fast, displayMaximum: window?.screen.maximumFramesPerSecond ?? 60)
        let link = displayLink ?? makeDisplayLink()
        link.preferredFrameRateRange = CAFrameRateRange(
            minimum: rate.minimum, maximum: rate.maximum, preferred: rate.preferred)
        fastRate = fast
    }

    /// One display-link frame. Ripples are not observed, so their start and end switch the rate here.
    func tick() {
        if displayLink != nil, currentlyFast != fastRate { schedule(fast: !fastRate) }
        drawFrame()
    }

    private func makeDisplayLink() -> CADisplayLink {
        let proxy = TopoDisplayLinkProxy()
        proxy.target = self
        let link = CADisplayLink(target: proxy, selector: #selector(TopoDisplayLinkProxy.tick(_:)))
        link.add(to: .main, forMode: .common)
        displayLink = link
        return link
    }

    private func invalidateDisplayLink() {
        displayLink?.invalidate()
        displayLink = nil
    }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        driver.resetClock()
        refresh()
    }
    override func layoutSubviews() {
        super.layoutSubviews()
        drawFrame()
    }

    func drawFrame() {
        driver.draw(on: metalLayer, size: bounds.size, scale: screenScale)
    }

    func stop() {
        invalidateDisplayLink()
        driver.stop(layer: metalLayer)
    }
}
#endif
