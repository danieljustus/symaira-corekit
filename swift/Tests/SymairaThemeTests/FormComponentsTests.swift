import SwiftUI
import XCTest

@testable import SymairaTheme

#if os(macOS)
import AppKit
#endif

@MainActor
final class FormComponentsTests: XCTestCase {
    func testSwitchLabelVisibilityDecision() {
        if #available(macOS 15, iOS 18, tvOS 18, *) {
            XCTAssertTrue(SymairaSwitchBody.showsLabel(.automatic))
            XCTAssertTrue(SymairaSwitchBody.showsLabel(.visible))
            XCTAssertFalse(SymairaSwitchBody.showsLabel(.hidden))
        }
    }

    func testTextFieldStyleShorthandIsAvailable() {
        let plain: SymairaTextFieldStyle = .symaira
        let focused: SymairaTextFieldStyle = .symaira(isFocused: true)
        XCTAssertNotNil(plain)
        XCTAssertNotNil(focused)
    }

    #if os(macOS)
    func testTextFieldDrawsFocusRingWhenTextEntryGainsFocus() async throws {
        for scheme in [ColorScheme.light, .dark] {
            let host = ThemeRenderHost.render(
                HStack(spacing: 0) {
                    TextField("Endpoint", text: .constant(""))
                        .textFieldStyle(.symaira)
                        .frame(width: 240)
                    SymairaTokens.focus.frame(width: 20, height: 20)
                }
                .frame(width: 300, height: 100)
                .background(SymairaTheme.surfaceOpaque(for: scheme))
                .environment(\.colorScheme, scheme),
                size: CGSize(width: 300, height: 100))
            let window = try XCTUnwrap(host.window)
            window.orderFront(nil)
            window.makeKey()
            defer { window.orderOut(nil) }
            XCTAssertTrue(window.makeFirstResponder(nil))
            try await Task.sleep(for: .milliseconds(50))
            let unfocused = try bitmap(of: host)
            try capture(unfocused, name: "field-\(scheme)-unfocused")
            XCTAssertEqual(try focusStrokePixels(in: unfocused), 0)

            window.selectNextKeyView(nil)
            try await Task.sleep(for: .milliseconds(50))
            XCTAssertTrue((window.firstResponder as? NSTextView)?.isFieldEditor == true)
            let focused = try bitmap(of: host)
            try capture(focused, name: "field-\(scheme)-focused")
            let scale = CGFloat(focused.pixelsHigh) / host.bounds.height
            XCTAssertEqual(CGFloat(try focusStrokePixels(in: focused)) / scale, 4, accuracy: 1)

            XCTAssertTrue(window.makeFirstResponder(nil))
            try await Task.sleep(for: .milliseconds(50))
            XCTAssertEqual(try focusStrokePixels(in: bitmap(of: host)), 0)
        }
    }

    func testTextFieldPromptMeetsContrastOnRaisedInBothAppearances() throws {
        for scheme in [ColorScheme.light, .dark] {
            let host = ThemeRenderHost.render(
                HStack(spacing: 0) {
                    SymairaTextField("Field", text: .constant(""), prompt: "HHMMMWBHHMMMWB")
                        .frame(width: 240)
                    SymairaTokens.ink3.frame(width: 20, height: 20)
                }
                .frame(width: 300, height: 100)
                .background(SymairaTheme.surfaceOpaque(for: scheme))
                .environment(\.colorScheme, scheme),
                size: CGSize(width: 300, height: 100))
            let image = try bitmap(of: host)
            try capture(image, name: "field-\(scheme)-prompt")
            let midY = image.pixelsHigh / 2
            let raised = try color(in: image, x: image.pixelsWide * 3 / 4, y: midY)
            let ink = try color(in: image, x: image.pixelsWide * 9 / 10, y: midY)
            var highestContrast: CGFloat = 0
            for x in (image.pixelsWide / 10)..<(image.pixelsWide * 2 / 5) {
                for y in (image.pixelsHigh * 2 / 5)..<(image.pixelsHigh * 3 / 5) {
                    highestContrast = max(highestContrast, contrast(raised, try color(in: image, x: x, y: y)))
                }
            }
            XCTAssertGreaterThanOrEqual(highestContrast, 4.5, "Rendered prompt in \(scheme)")
            XCTAssertEqual(highestContrast, contrast(raised, ink), accuracy: 0.2, "Prompt uses ink3 in \(scheme)")
        }
    }

    private func capture(_ image: NSBitmapImageRep, name: String) throws {
        guard let directory = ProcessInfo.processInfo.environment["SYMAIRA_FORM_CAPTURE_DIR"] else { return }
        let png = try XCTUnwrap(image.representation(using: .png, properties: [:]))
        try png.write(to: URL(fileURLWithPath: directory).appendingPathComponent("\(name).png"))
    }

    private func bitmap(of host: NSView) throws -> NSBitmapImageRep {
        host.layoutSubtreeIfNeeded()
        let image = try XCTUnwrap(host.bitmapImageRepForCachingDisplay(in: host.bounds))
        host.cacheDisplay(in: host.bounds, to: image)
        return image
    }

    private func color(in image: NSBitmapImageRep, x: Int, y: Int) throws -> NSColor {
        let components = try XCTUnwrap(image.colorAt(x: x, y: y))
        let tagged = NSColor(
            colorSpace: image.colorSpace,
            components: [components.redComponent, components.greenComponent, components.blueComponent, 1],
            count: 4)
        return try XCTUnwrap(tagged.usingColorSpace(.sRGB))
    }

    private func focusStrokePixels(in image: NSBitmapImageRep) throws -> Int {
        let swatch = try color(in: image, x: image.pixelsWide * 9 / 10, y: image.pixelsHigh / 2)
        return try (0..<image.pixelsHigh).count { y in
            let pixel = try color(in: image, x: image.pixelsWide / 2, y: y)
            return abs(pixel.redComponent - swatch.redComponent) < 0.03
                && abs(pixel.greenComponent - swatch.greenComponent) < 0.03
                && abs(pixel.blueComponent - swatch.blueComponent) < 0.03
        }
    }

    private func contrast(_ first: NSColor, _ second: NSColor) -> CGFloat {
        func luminance(_ color: NSColor) -> CGFloat {
            let channels = [color.redComponent, color.greenComponent, color.blueComponent]
            return zip(channels, [0.2126, 0.7152, 0.0722]).reduce(0) { result, pair in
                let (value, weight) = pair
                let linear = value <= 0.04045 ? value / 12.92 : pow((value + 0.055) / 1.055, 2.4)
                return result + linear * weight
            }
        }
        let a = luminance(first)
        let b = luminance(second)
        return (max(a, b) + 0.05) / (min(a, b) + 0.05)
    }
    #endif

    func testFormSectionAcceptsTitleAndFooter() {
        let section = SymairaFormSection("Storage", footer: "Kept on this Mac.") {
            Text("row")
        }
        ThemeRenderHost.render(section)
    }

    func testFormSectionWorksWithoutTitleOrFooter() {
        let section = SymairaFormSection { Text("row") }
        ThemeRenderHost.render(section)
    }

    func testFormRowSupportsALabelOnlyVariant() {
        let row = SymairaFormRow("Model", description: "Used for search.")
        ThemeRenderHost.render(row)
    }

    func testFormRowSupportsATrailingControl() {
        let row = SymairaFormRow("Enabled") { Toggle("", isOn: .constant(true)) }
        ThemeRenderHost.render(row)
    }

    #if os(macOS)
    func testFormRowCentersControlsOnFirstLabelLine() throws {
        for label in ["Sync automatically", "Sync automatically\nAcross devices"] {
            for description in [nil, "Apply after the next sync."] {
                try assertFormRowAlignment(label, description: description, control: "switch") {
                    Toggle("Sync", isOn: .constant(true)).toggleStyle(.switch).labelsHidden()
                }
                try assertFormRowAlignment(label, description: description, control: "segments") {
                    Picker("Mode", selection: .constant(0)) {
                        Text("Auto").tag(0)
                        Text("Manual").tag(1)
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                }
                try assertFormRowAlignment(label, description: description, control: "text field") {
                    TextField("Value", text: .constant(""))
                        .textFieldStyle(.symaira)
                        .frame(width: 120)
                }
            }
        }
    }

    private func assertFormRowAlignment<Control: View>(
        _ label: String, description: String?, control: String, @ViewBuilder trailing: () -> Control
    ) throws {
        let host = ThemeRenderHost.render(
            SymairaFormRow(label, description: description) {
                trailing().overlay(alignment: .trailing) { Color.blue.frame(width: 2) }
            }
            .frame(width: 340, height: 140)
            .background(.white)
            .environment(\.colorScheme, .light),
            size: CGSize(width: 340, height: 140))
        let image = try bitmap(of: host)
        let scale = CGFloat(image.pixelsHigh) / host.bounds.height
        let inkRows = try (0..<image.pixelsHigh).filter { y in
            try (0..<(image.pixelsWide / 3)).contains { x in
                try color(in: image, x: x, y: y).brightnessComponent < 0.5
            }
        }
        let firstInk = try XCTUnwrap(inkRows.first)
        let firstLine = try XCTUnwrap(inkRows.enumerated().prefix { $0.element == firstInk + $0.offset }.last?.element)
        let markerRows = try (0..<image.pixelsHigh).filter { y in
            try ((image.pixelsWide * 2 / 3)..<image.pixelsWide).contains { x in
                let pixel = try color(in: image, x: x, y: y)
                return pixel.blueComponent > 0.8 && pixel.redComponent < 0.2
            }
        }
        let controlTop = try XCTUnwrap(markerRows.first)
        let controlBottom = try XCTUnwrap(markerRows.last)
        XCTAssertGreaterThan(controlBottom - controlTop, 10, "Missing control extent for \(control)")
        XCTAssertEqual(
            CGFloat(firstInk + firstLine) / (2 * scale), CGFloat(controlTop + controlBottom) / (2 * scale),
            accuracy: 2, "\(control), description: \(description ?? "none"), label: \(label)")
    }
    #endif

    func testFormRowClearsTheMinimumControlHeight() {
        XCTAssertGreaterThanOrEqual(SymairaMetrics.minimumControlHeight, 34)
    }

    func testStatusDotRequiresAnAccessibilityLabel() {
        let dot = SymairaStatusDot(tone: .positive, accessibilityLabel: "Connected")
        ThemeRenderHost.render(dot)
    }

    func testStatusLabelPairsToneWithVisibleText() {
        let label = SymairaStatusLabel("Disconnected", tone: .critical)
        ThemeRenderHost.render(label)
    }

    func testStatusTonesResolveToDistinctColours() {
        let tones: [SymairaTone] = [.neutral, .positive, .warning, .critical]
        let dark = Set(tones.map { $0.foreground(for: .dark) })
        let light = Set(tones.map { $0.foreground(for: .light) })
        XCTAssertEqual(dark.count, tones.count)
        XCTAssertEqual(light.count, tones.count)
    }

    /// Liquid Topography has no informational hue (#505): `.informative` is neutral.
    func testInformativeToneIsNeutral() {
        for scheme in [ColorScheme.light, .dark] {
            XCTAssertEqual(SymairaTone.informative.foreground(for: scheme), SymairaTone.neutral.foreground(for: scheme))
        }
        XCTAssertEqual(SymairaTone.informative.foreground, SymairaTone.neutral.foreground)
    }
}
