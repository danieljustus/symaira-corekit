import Foundation

/// Platform-neutral frame-loop policy of the native Metal surfaces (macOS and
/// iOS/tvOS). Pure value logic, so the pause and pacing rules are unit tested
/// without a window, a display or a GPU.
enum TopoFramePacing {
    /// Frame-rate request for a display link: idle runs at the token cap,
    /// an interactive surface at the display's maximum.
    struct Rate: Equatable {
        var minimum: Float
        var maximum: Float
        var preferred: Float
    }

    /// The surface stops its frame loop when the animation is static
    /// (Reduce Motion, `animationEnabled == false`, Low Power Mode) or hidden
    /// (occluded window on macOS, background scene on iOS).
    static func isPaused(still: Bool, visible: Bool, lowPower: Bool) -> Bool {
        still || !visible || lowPower
    }

    /// Static frames also ignore the pointer and ripples; Low Power Mode
    /// freezes the field without the caller having to set `still`.
    static func isStill(still: Bool, lowPower: Bool) -> Bool { still || lowPower }

    /// A frame loop only runs while unpaused and attached to a window.
    static func runsFrameLoop(paused: Bool, hasWindow: Bool) -> Bool { !paused && hasWindow }

    /// The pointer over the surface and travelling ripples need every display frame; the slow
    /// contour drift alone moves less than a device pixel per idle frame.
    static func runsAtDisplayRate(interactive: Bool, rippling: Bool) -> Bool { interactive || rippling }

    /// Frames per second for a timer or display link. `displayMaximum` is the
    /// attached screen's `maximumFramesPerSecond`; 0 or negative means unknown.
    static func framesPerSecond(interactive: Bool, displayMaximum: Int) -> Double {
        interactive ? Double(displayMaximum > 0 ? displayMaximum : 60) : SymairaTokens.Topo.fps
    }

    /// Idle is pinned to the 20 fps cap (no range, so the system never raises
    /// it); interactive may run anywhere from half the idle cap up to the
    /// display maximum and prefers the maximum.
    static func rate(interactive: Bool, displayMaximum: Int) -> Rate {
        let fps = Float(framesPerSecond(interactive: interactive, displayMaximum: displayMaximum))
        if !interactive { return Rate(minimum: fps, maximum: fps, preferred: fps) }
        return Rate(minimum: min(fps, Float(SymairaTokens.Topo.fps)), maximum: fps, preferred: fps)
    }
}
