import SwiftUI
import XCTest

@testable import SymairaTheme

#if os(macOS)
import AppKit
#endif

@MainActor
final class ComponentsTests: XCTestCase {

    // MARK: - Grid & backdrop

    func testGridStylesAreDistinctCases() {
        XCTAssertNotEqual(SymairaGridStyle.lines, SymairaGridStyle.dots)
    }

    func testBlueprintGridEvaluatesBodyForDefaultsAndCustomParameters() {
        ThemeRenderHost.render(BlueprintGrid())
        ThemeRenderHost.render(BlueprintGrid(spacing: 12, style: .dots, color: .white))
    }

    func testBlueprintGridRendersBothStyles() {
        ThemeRenderHost.render(BlueprintGrid())
        ThemeRenderHost.render(BlueprintGrid(spacing: 16, style: .dots))
    }

    func testAmbientGlowsEvaluatesBodyAcrossIntensityRange() {
        ThemeRenderHost.render(AmbientGlows())
        ThemeRenderHost.render(AmbientGlows(intensity: 0))
        ThemeRenderHost.render(AmbientGlows(intensity: 2))
    }

    func testAmbientGlowsRenders() {
        ThemeRenderHost.render(AmbientGlows(intensity: 1.5))
    }

    func testBackdropEvaluatesBodyForGridStylesAndVisibility() {
        ThemeRenderHost.render(SymairaBackdrop())
        ThemeRenderHost.render(SymairaBackdrop(gridStyle: .dots, showsGrid: false))
    }

    func testBackdropRendersAcrossAppearances() {
        ThemeRenderHost.render(SymairaBackdrop().environment(\.colorScheme, .dark))
        ThemeRenderHost.render(SymairaBackdrop(gridStyle: .dots).environment(\.colorScheme, .light))
    }

    func testTelemetryCornersEvaluatesBodyAndRenders() {
        ThemeRenderHost.render(TelemetryCorners(color: .red, length: 12, lineWidth: 2))
        ThemeRenderHost.render(TelemetryCorners())
    }

    // MARK: - Glass surfaces

    func testGlassmorphicPanelRendersAcrossAppearances() {
        ThemeRenderHost.render(Text("panel").glassmorphicPanel())
        ThemeRenderHost.render(
            Text("panel").glassmorphicPanel(cornerRadius: 8, addCorners: false)
                .environment(\.colorScheme, .dark)
        )
    }

    func testGlassCardRendersAcrossHoverAndAppearance() {
        ThemeRenderHost.render(Text("card").glassCard())
        ThemeRenderHost.render(Text("card").glassCard(isHovered: true).environment(\.colorScheme, .dark))
        ThemeRenderHost.render(Text("card").glassCard(isHovered: true, cornerRadius: 20))
    }

    // MARK: - Liquid Glass chrome

    func testGlassVariantsAreDistinctCases() {
        XCTAssertNotEqual(SymairaGlassVariant.regular, SymairaGlassVariant.clear)
    }

    func testGlassChromeRendersAcrossVariants() {
        ThemeRenderHost.render(Text("chrome").symairaGlassChrome())
        ThemeRenderHost.render(
            Text("chrome").symairaGlassChrome(variant: .clear, tint: .blue, isInteractive: true)
        )
        ThemeRenderHost.render(
            Text("chrome").symairaGlassChrome(variant: .regular, cornerRadius: 6)
                .environment(\.colorScheme, .dark)
        )
    }

    func testGlassEffectContainerEvaluatesBodyAndRenders() {
        let container = SymairaGlassEffectContainer(spacing: 8) {
            Button("Refresh") {}
                .symairaButtonStyle(.toolbar)
        }
        ThemeRenderHost.render(container)
    }

    // MARK: - Buttons

    func testButtonRolesAreDistinctCases() {
        XCTAssertNotEqual(SymairaButtonRole.primary, SymairaButtonRole.secondary)
        XCTAssertNotEqual(SymairaButtonRole.primary, SymairaButtonRole.toolbar)
        XCTAssertNotEqual(SymairaButtonRole.secondary, SymairaButtonRole.toolbar)
        XCTAssertNotEqual(SymairaButtonRole.primary, SymairaButtonRole.destructive)
    }

    func testAdaptiveButtonRendersAllRoles() {
        ThemeRenderHost.render(Button("Action") {}.symairaButtonStyle(.primary))
        ThemeRenderHost.render(Button("Action") {}.symairaButtonStyle(.secondary))
        ThemeRenderHost.render(Button("Action") {}.symairaButtonStyle(.toolbar))
        ThemeRenderHost.render(Button("Action", role: .destructive) {}.symairaButtonStyle(.destructive))
        ThemeRenderHost.render(
            Button("Action", role: .destructive) {}.symairaButtonStyle(.destructive).symairaControlTier(.workbench))
    }

    #if !os(tvOS)
    func testContentActionLabelsStayOnOneLineInNarrowPair() throws {
        var oneLineHeight: CGFloat?
        var cancelHeight: CGFloat?
        var deleteHeight: CGFloat?
        ThemeRenderHost.render(
            VStack {
                Text("Abbrechen").font(SymairaTypography.bodyEmphasized)
                    .onGeometryChange(for: CGFloat.self, of: { $0.size.height }) { oneLineHeight = $0 }
                HStack {
                    // Reserve leading space to force both labels below their ideal widths.
                    Spacer(minLength: 164)
                    Button {
                    } label: {
                        Text("Abbrechen")
                            .onGeometryChange(for: CGFloat.self, of: { $0.size.height }) { cancelHeight = $0 }
                    }
                    .symairaButtonStyle(.secondary)
                    Button {
                    } label: {
                        Text("Löschen")
                            .onGeometryChange(for: CGFloat.self, of: { $0.size.height }) { deleteHeight = $0 }
                    }
                    .symairaButtonStyle(.primary)
                }
                .frame(width: 340)
            })
        let expected = try XCTUnwrap(oneLineHeight)
        XCTAssertGreaterThan(expected, 0)
        XCTAssertEqual(try XCTUnwrap(cancelHeight), expected, accuracy: 0.5)
        XCTAssertEqual(try XCTUnwrap(deleteHeight), expected, accuracy: 0.5)
    }

    #if os(macOS)
    /// CTRL-1: in the workbench tier buttons and segments share the native `.large` height;
    /// the page tier gives actions and the segmented control one 36 pt height.
    func testControlTiersGiveEachTierOneHeight() throws {
        for tier in [SymairaControlTier.page, .workbench] {
            var heights: [String: CGFloat] = [:]
            ThemeRenderHost.render(
                HStack {
                    Button("Anwenden") {}.symairaButtonStyle(.primary)
                        .onGeometryChange(for: CGFloat.self, of: { $0.size.height }) { heights["primary"] = $0 }
                    Button("Probe") {}.symairaButtonStyle(.secondary)
                        .onGeometryChange(for: CGFloat.self, of: { $0.size.height }) { heights["secondary"] = $0 }
                    Button("Löschen", role: .destructive) {}.symairaButtonStyle(.destructive)
                        .onGeometryChange(for: CGFloat.self, of: { $0.size.height }) { heights["destructive"] = $0 }
                    SymairaSegmentedControl("Ansicht", selection: .constant(0), options: [(0, "Audio"), (1, "Text")])
                        .onGeometryChange(for: CGFloat.self, of: { $0.size.height }) { heights["segmented"] = $0 }
                    TextField("Name", text: .constant("")).textFieldStyle(SymairaTextFieldStyle())
                        .onGeometryChange(for: CGFloat.self, of: { $0.size.height }) { heights["field"] = $0 }
                }
                .symairaControlTier(tier))
            let page = tier == .page
            let tool = SymairaMetrics.workbenchControlHeight
            let action = page ? SymairaMetrics.contentActionHeight : tool
            XCTAssertEqual(try XCTUnwrap(heights["primary"]), action, accuracy: 0.5, "\(tier)")
            XCTAssertEqual(try XCTUnwrap(heights["secondary"]), action, accuracy: 0.5, "\(tier)")
            XCTAssertEqual(try XCTUnwrap(heights["destructive"]), action, accuracy: 0.5, "\(tier)")
            XCTAssertEqual(
                try XCTUnwrap(heights["segmented"]), page ? SymairaMetrics.segmentedControlHeight : tool,
                accuracy: 0.5, "\(tier)")
            // A Symaira field in a page toolbar is as high as the page actions beside it (#514).
            XCTAssertEqual(try XCTUnwrap(heights["field"]), action, accuracy: 0.5, "\(tier)")
        }
    }
    #endif

    /// ACTION-2: the glass secondary keeps the opaque primary's height, so a row can mix them.
    func testSecondaryGlassKeepsPrimaryHeight() throws {
        var heights: [SymairaButtonRole: CGFloat] = [:]
        for role in [SymairaButtonRole.primary, .secondary, .destructive] {
            ThemeRenderHost.render(
                Button("Export…") {}
                    .symairaButtonStyle(role)
                    .onGeometryChange(for: CGFloat.self, of: { $0.size.height }) { heights[role] = $0 })
        }
        let primary = try XCTUnwrap(heights[.primary])
        XCTAssertEqual(primary, SymairaMetrics.contentActionHeight, accuracy: 0.5)
        XCTAssertEqual(try XCTUnwrap(heights[.secondary]), primary, accuracy: 0.5)
        XCTAssertEqual(try XCTUnwrap(heights[.destructive]), primary, accuracy: 0.5)
    }

    func testContentActionsStillFillAvailableWidth() throws {
        for role in [SymairaButtonRole.primary, .secondary] {
            var buttonWidth: CGFloat?
            ThemeRenderHost.render(
                Button {
                } label: {
                    Text("Action").frame(maxWidth: .infinity)
                }
                .symairaButtonStyle(role)
                .onGeometryChange(for: CGFloat.self, of: { $0.size.width }) { buttonWidth = $0 }
                .frame(width: 340))
            XCTAssertEqual(try XCTUnwrap(buttonWidth), 340, accuracy: 0.5, "\(role)")
        }
    }
    #endif

    #if os(macOS)
    func testContentActionsReportPressAndRelease() async throws {
        for role in [SymairaButtonRole.primary, .secondary] {
            var pressChanges: [Bool] = []
            let size = CGSize(width: 340, height: 200)
            let host = ThemeRenderHost.render(
                ScrollView {
                    Button("Action") {}
                        .symairaButtonStyle(role, onPressChange: { pressChanges.append($0) })
                        .frame(width: size.width, height: size.height)
                    Spacer(minLength: size.height)
                }, size: size)
            let window = try XCTUnwrap(host.window)
            window.makeKeyAndOrderFront(nil)
            defer { window.orderOut(nil) }
            let point = host.convert(NSPoint(x: host.bounds.midX, y: host.bounds.midY), to: nil)
            XCTAssertTrue(pressChanges.isEmpty)
            for (type, expected) in [(NSEvent.EventType.leftMouseDown, [true]), (.leftMouseUp, [true, false])] {
                let event = try XCTUnwrap(
                    NSEvent.mouseEvent(
                        with: type, location: point, modifierFlags: [],
                        timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
                        context: nil, eventNumber: 0, clickCount: 1, pressure: 0))
                window.sendEvent(event)
                let deadline = ContinuousClock.now + .seconds(1)
                while pressChanges.count < expected.count && ContinuousClock.now < deadline {
                    try await Task.sleep(for: .milliseconds(10))
                }
                XCTAssertEqual(pressChanges, expected, "\(role)")
            }
        }
    }
    #endif

    func testPrimaryButtonStyleRendersEnabledAndDisabled() {
        ThemeRenderHost.render(Button("Save") {}.buttonStyle(SymairaPrimaryButtonStyle()))
        ThemeRenderHost.render(
            Button("Save") {}
                .buttonStyle(SymairaPrimaryButtonStyle())
                .environment(\.isEnabled, false)
        )
    }

    func testSecondaryButtonStyleRendersAcrossAppearances() {
        ThemeRenderHost.render(Button("Cancel") {}.buttonStyle(SymairaSecondaryButtonStyle()))
        ThemeRenderHost.render(
            Button("Cancel") {}.buttonStyle(SymairaSecondaryButtonStyle())
                .environment(\.colorScheme, .dark)
        )
        ThemeRenderHost.render(
            Button("Cancel") {}.buttonStyle(SymairaSecondaryButtonStyle())
                .environment(\.isEnabled, false)
        )
    }
}

@MainActor
final class SelectionControlsTests: XCTestCase {
    /// Light `raised` equals `canvas`, and dark `raised` sits at 1.3:1 on `surface`: opaque
    /// controls carry the 3:1 control outline in both appearances (COLOR-4, #515), not `line`.
    func testRaisedControlsCarryTheControlOutlineInBothAppearances() {
        XCTAssertEqual(SymairaTheme.surfaceRaised(for: .light), Color(hex: "EEEDEA"))
        for scheme in [ColorScheme.light, .dark] {
            XCTAssertEqual(SymairaTheme.raisedOutline(for: scheme), SymairaTheme.controlOutline(for: scheme))
            XCTAssertNotEqual(SymairaTheme.raisedOutline(for: scheme), SymairaTheme.line(for: scheme))
        }
    }

    #if os(macOS)
    /// The opaque fallback (Reduce Transparency, before macOS 26) keeps its outline; native glass
    /// draws its own edge and does not render into an offscreen bitmap at all.
    func testSecondaryButtonOnLightCanvasDrawsItsOutline() throws {
        let host = ThemeRenderHost.render(
            // No label: anti-aliased glyph edges would otherwise pass for an outline.
            Button {
            } label: {
                Color.clear.frame(width: 120, height: 20)
            }.buttonStyle(SymairaSecondaryButtonStyle(allowsGlass: false))
                .padding(24)
                .background(Color(hex: "EEEDEA"))
                .environment(\.colorScheme, .light),
            size: CGSize(width: 200, height: 100))
        let bitmap = try XCTUnwrap(host.bitmapImageRepForCachingDisplay(in: host.bounds))
        host.cacheDisplay(in: host.bounds, to: bitmap)
        var outlined = 0
        for x in 0..<bitmap.pixelsWide {
            for y in 0..<bitmap.pixelsHigh {
                guard let c = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.sRGB) else { continue }
                // Without a label, only the outline is darker than the canvas.
                if c.brightnessComponent < 0.85 && c.brightnessComponent > 0.6 { outlined += 1 }
            }
        }
        XCTAssertGreaterThan(outlined, 100, "secondary button has no visible edge on the light canvas")
    }
    #endif

    private enum Profile: Hashable { case system, cool, max }

    func testSelectionControlsRenderInBothAppearances() {
        var profile = Profile.system
        let binding = Binding(get: { profile }, set: { profile = $0 })
        var isOn = true
        let toggle = Binding(get: { isOn }, set: { isOn = $0 })
        for scheme in [ColorScheme.light, .dark] {
            ThemeRenderHost.render(
                VStack {
                    SymairaSegmentedControl(
                        "Lüfterprofil", selection: binding,
                        options: [(.system, "Standard"), (.cool, "Cool"), (.max, "Max")])
                    Toggle("Wachhalten", isOn: toggle).toggleStyle(.symairaSwitch)
                    Text("Karte").symairaCard()
                    SymairaLockedLabel()
                    Button("Anwenden") {}.symairaButtonStyle(.primary)
                    Button("Abbrechen") {}.symairaButtonStyle(.secondary)
                }
                .environment(\.colorScheme, scheme)
            )
        }
    }
}
