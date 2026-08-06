import XCTest
import SwiftUI
@testable import SymairaTheme

@MainActor
final class ComponentsTests: XCTestCase {

    // MARK: - Grid & backdrop

    func testGridStylesAreDistinctCases() {
        XCTAssertNotEqual(SymairaGridStyle.lines, SymairaGridStyle.dots)
    }

    func testBlueprintGridEvaluatesBodyForDefaultsAndCustomParameters() {
        XCTAssertNotNil(BlueprintGrid().body)
        XCTAssertNotNil(BlueprintGrid(spacing: 12, style: .dots, color: .white).body)
    }

    func testBlueprintGridRendersBothStyles() {
        ThemeRenderHost.render(BlueprintGrid())
        ThemeRenderHost.render(BlueprintGrid(spacing: 16, style: .dots))
    }

    func testAmbientGlowsEvaluatesBodyAcrossIntensityRange() {
        XCTAssertNotNil(AmbientGlows().body)
        XCTAssertNotNil(AmbientGlows(intensity: 0).body)
        XCTAssertNotNil(AmbientGlows(intensity: 2).body)
    }

    func testAmbientGlowsRenders() {
        ThemeRenderHost.render(AmbientGlows(intensity: 1.5))
    }

    func testBackdropEvaluatesBodyForGridStylesAndVisibility() {
        XCTAssertNotNil(SymairaBackdrop().body)
        XCTAssertNotNil(SymairaBackdrop(gridStyle: .dots, showsGrid: false).body)
    }

    func testBackdropRendersAcrossAppearances() {
        ThemeRenderHost.render(SymairaBackdrop().environment(\.colorScheme, .dark))
        ThemeRenderHost.render(SymairaBackdrop(gridStyle: .dots).environment(\.colorScheme, .light))
    }

    func testTelemetryCornersEvaluatesBodyAndRenders() {
        XCTAssertNotNil(TelemetryCorners().body)
        XCTAssertNotNil(TelemetryCorners(color: .red, length: 12, lineWidth: 2).body)
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
        XCTAssertNotNil(container.body)
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
