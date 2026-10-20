import SwiftUI
import XCTest

@testable import SymairaTheme

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
    }

    func testAdaptiveButtonRendersAllRoles() {
        ThemeRenderHost.render(Button("Action") {}.symairaButtonStyle(.primary))
        ThemeRenderHost.render(Button("Action") {}.symairaButtonStyle(.secondary))
        ThemeRenderHost.render(Button("Action") {}.symairaButtonStyle(.toolbar))
    }

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
    /// Light `raised` equals `canvas`; without an outline secondary controls vanish on the page.
    func testRaisedControlsAreOutlinedOnlyWhereRaisedMatchesCanvas() {
        XCTAssertEqual(SymairaTheme.surfaceRaised(for: .light), Color(hex: "EEEDEA"))
        XCTAssertEqual(SymairaTheme.raisedOutline(for: .light), SymairaTheme.line(for: .light))
        XCTAssertEqual(SymairaTheme.raisedOutline(for: .dark), .clear)
    }

    func testSecondaryButtonOnLightCanvasDrawsItsOutline() throws {
        let host = ThemeRenderHost.render(
            // No label: anti-aliased glyph edges would otherwise pass for an outline.
            Button {
            } label: {
                Color.clear.frame(width: 120, height: 20)
            }.symairaButtonStyle(.secondary)
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
