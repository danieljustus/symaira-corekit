import CoreText
import SwiftUI
import XCTest

@testable import SymairaTheme

final class TypographyTests: XCTestCase {
    func testScaleEntriesAreDistinctWhereTheyShouldBe() {
        let roles: [SymairaFontRole] = [
            SymairaTypography.display,
            SymairaTypography.title,
            SymairaTypography.heading,
            SymairaTypography.subheading,
            SymairaTypography.body,
            SymairaTypography.caption,
            SymairaTypography.micro,
            SymairaTypography.mono,
        ]
        XCTAssertEqual(Set(roles).count, roles.count, "scale entries must not collapse onto each other")
    }

    func testPlatformScaleDoublesOnlyOnTheTV() {
        #if os(tvOS)
        XCTAssertEqual(SymairaMetrics.platformScale, 2)
        #else
        XCTAssertEqual(SymairaMetrics.platformScale, 1)
        #endif
        XCTAssertEqual(SymairaSpacing.large, 16 * SymairaMetrics.platformScale)
        XCTAssertEqual(SymairaRadius.card, 14 * SymairaMetrics.platformScale)
        XCTAssertEqual(SymairaPageLayout.toolbarHeight, 44 * SymairaMetrics.platformScale)
        XCTAssertEqual(SymairaMetrics.readableContentWidth, 760 * SymairaMetrics.platformScale)
    }

    /// One radius scale: `SymairaRadius` is the token scale at the platform's size.
    func testRadiiComeFromTheTokenScale() {
        XCTAssertEqual(SymairaRadius.control, SymairaTokens.Radius.md * SymairaMetrics.platformScale)
        XCTAssertEqual(SymairaRadius.card, SymairaTokens.Radius.lg * SymairaMetrics.platformScale)
        XCTAssertEqual(SymairaRadius.panel, SymairaTokens.Radius.xl * SymairaMetrics.platformScale)
    }

    /// IOS-7: body text is 13.5 pt at the default Dynamic Type size on iOS; tvOS keeps the platform scale.
    func testTextScaleSetsTheIOSBodySize() {
        #if os(iOS)
        XCTAssertEqual(13.5 * SymairaMetrics.textScale, 13.5, accuracy: 0.0001)
        #else
        XCTAssertEqual(SymairaMetrics.textScale, SymairaMetrics.platformScale)
        #endif
    }

    /// Every bundled role matches its `typography` entry in DESIGN.md (family, size, weight,
    /// line height), so web classes and Apple roles with one name never mean two styles.
    func testRolesMatchTheTokenSpec() throws {
        let spec = try String(contentsOf: ThemeTests.tokenSpec, encoding: .utf8)
        let block = try XCTUnwrap(
            spec.components(separatedBy: "\ntypography:\n").last?
                .components(separatedBy: "\nrounded:\n").first)
        var entries: [String: [String: String]] = [:]
        var current: String?
        for line in block.split(separator: "\n") where !line.trimmingCharacters(in: .whitespaces).hasPrefix("#") {
            let parts = line.trimmingCharacters(in: .whitespaces).split(separator: ":", maxSplits: 1)
            if line.hasPrefix("    "), let current, parts.count == 2 {
                entries[current, default: [:]][String(parts[0])] =
                    parts[1].trimmingCharacters(in: CharacterSet(charactersIn: " \""))
            } else if line.hasPrefix("  ") {
                current = String(parts[0])
            }
        }
        let roles: [(String, SymairaFontRole)] = [
            ("display", SymairaTypography.display), ("title", SymairaTypography.title),
            ("heading", SymairaTypography.heading), ("subheading", SymairaTypography.subheading),
            ("body", SymairaTypography.body), ("body-medium", SymairaTypography.bodyMedium),
            ("body-emphasized", SymairaTypography.bodyEmphasized), ("label", SymairaTypography.label),
            ("callout", SymairaTypography.callout), ("caption", SymairaTypography.caption),
            ("micro", SymairaTypography.micro), ("readout", SymairaTypography.readout),
            ("stat", SymairaTypography.stat),
        ]
        for (name, role) in roles {
            let entry = try XCTUnwrap(entries[name], "DESIGN.md has no typography role \(name)")
            guard case .bundled(let family, let size, let weight, _) = role.source else {
                return XCTFail("\(name) must use a bundled font")
            }
            XCTAssertEqual(entry["fontFamily"], family == .brand ? "Google Sans Flex" : "Figtree", name)
            let fontSize = entry["fontSize"].flatMap { Double($0.replacingOccurrences(of: "px", with: "")) }
            XCTAssertEqual(fontSize, Double(size), name)
            XCTAssertEqual(Double(entry["fontWeight"] ?? ""), weight, name)
            XCTAssertEqual(Double(entry["lineHeight"] ?? ""), role.lineHeight.map { Double($0) }, name)
        }
    }

    /// LAYOUT-2: running text at the prose measure holds 45 to 75 characters of body text, in
    /// English and German, at this platform's body size.
    func testProseMeasureKeepsBodyTextReadable() {
        SymairaFont.register()
        let font = SymairaFont.ctFont(size: 13.5 * SymairaMetrics.textScale, weight: 450, family: .text)
        let samples = [
            "Symaira keeps your requests in one place. Each request shows its current status, the broker it was sent to and the date of the last reply.",
            "Symaira hält deine Anfragen an einem Ort zusammen. Jede Anfrage zeigt ihren aktuellen Status, den Datenhändler und das Datum der letzten Antwort.",
        ]
        for sample in samples {
            let line = CTLineCreateWithAttributedString(
                NSAttributedString(
                    string: sample, attributes: [NSAttributedString.Key(kCTFontAttributeName as String): font]))
            let perCharacter = CTLineGetTypographicBounds(line, nil, nil, nil) / Double(sample.count)
            let characters = Double(SymairaMetrics.proseMeasure) / perCharacter
            XCTAssertGreaterThanOrEqual(characters, 45, sample)
            XCTAssertLessThanOrEqual(characters, 75, sample)
        }
        // The page column itself is no measure for running text (#512).
        XCTAssertLessThan(SymairaMetrics.proseMeasure, SymairaMetrics.readableContentWidth)
    }

    func testWeightVariantsOfBodyAreDistinct() {
        XCTAssertNotEqual(SymairaTypography.body, SymairaTypography.bodyEmphasized)
        XCTAssertNotEqual(SymairaTypography.body, SymairaTypography.bodyMedium)
        XCTAssertNotEqual(SymairaTypography.bodyMedium, SymairaTypography.bodyEmphasized)
    }

    func testMonospacedRolesDifferFromTheirProportionalCounterparts() {
        XCTAssertNotEqual(SymairaTypography.mono, SymairaTypography.body)
        XCTAssertNotEqual(SymairaTypography.monoSmall, SymairaTypography.caption)
    }

    func testTextRolesMapOntoTheScale() {
        XCTAssertEqual(SymairaTextRole.display.font, SymairaTypography.display)
        XCTAssertEqual(SymairaTextRole.body.font, SymairaTypography.body)
        XCTAssertEqual(SymairaTextRole.bodyEmphasized.font, SymairaTypography.bodyEmphasized)
        XCTAssertEqual(SymairaTextRole.sectionLabel.font, SymairaTypography.micro)
        XCTAssertEqual(SymairaTextRole.mono.font, SymairaTypography.mono)
    }

    func testCalloutAndSecondaryShareASizeButNotAColour() {
        XCTAssertEqual(SymairaTextRole.callout.font, SymairaTextRole.secondary.font)
        XCTAssertNotEqual(
            SymairaTextRole.callout.foreground(for: .dark),
            SymairaTextRole.secondary.foreground(for: .dark)
        )
    }

    func testForegroundsFollowTheAdaptivePalette() {
        XCTAssertEqual(SymairaTextRole.title.foreground(for: .dark), SymairaTheme.foregroundPrimary(for: .dark))
        XCTAssertEqual(
            SymairaTextRole.secondary.foreground(for: .dark),
            SymairaTheme.foregroundSecondary(for: .dark)
        )
        XCTAssertEqual(
            SymairaTextRole.caption.foreground(for: .light),
            SymairaTheme.foregroundMuted(for: .light)
        )
    }

    func testTrackingTightensLargeRolesAndOpensOnlyTheSectionLabel() {
        XCTAssertEqual(SymairaTextRole.sectionLabel.tracking, 0.6)
        XCTAssertLessThan(SymairaTextRole.display.tracking, 0)
        XCTAssertLessThan(SymairaTextRole.title.tracking, 0)
        for role in [SymairaTextRole.body, .callout, .secondary, .caption, .mono] {
            XCTAssertEqual(role.tracking, 0, "\(role) must not add tracking")
            XCTAssertEqual(role.tracking(for: .light), 0, "\(role) must not add tracking in light appearance")
        }
    }

    /// Small gray text opens by +0.01em in dark appearance only; everything else keeps its tracking.
    func testDarkAppearanceOpensOnlySmallGrayText() {
        XCTAssertEqual(SymairaTextRole.secondary.tracking(for: .dark), 12.5 * 0.01, accuracy: 0.0001)
        XCTAssertEqual(SymairaTextRole.caption.tracking(for: .dark), 11.5 * 0.01, accuracy: 0.0001)
        let unchanged: [SymairaTextRole] = [
            .display, .title, .heading, .subheading, .body, .bodyEmphasized, .callout, .sectionLabel, .mono, .monoSmall,
        ]
        for role in unchanged {
            XCTAssertEqual(role.tracking(for: .dark), role.tracking, "\(role) must not change tracking in dark")
        }
    }

    func testBundledGoogleSansFlexRegistersWithFixedOpticalSize() throws {
        XCTAssertTrue(SymairaFont.register(), "GoogleSansFlex.ttf must ship in the SymairaTheme bundle")
        let license = try XCTUnwrap(
            Bundle.module.url(forResource: "GoogleSansFlex-OFL", withExtension: "txt"),
            "OFL must ship next to the font")
        XCTAssertTrue(try String(contentsOf: license, encoding: .utf8).contains("SIL OPEN FONT LICENSE"))
        XCTAssertNotNil(Bundle.module.url(forResource: "GoogleSansFlex-TRADEMARKS", withExtension: "md"))
        for size in [11.5, 13.5, 26] as [CGFloat] {
            let font = SymairaFont.ctFont(size: size, weight: 600)
            XCTAssertEqual(CTFontCopyFamilyName(font) as String, "Google Sans Flex")
            let variation = CTFontCopyVariation(font) as? [NSNumber: Double] ?? [:]
            XCTAssertEqual(variation[SymairaFont.axis("wght")], 600)
            // opsz is either reported as the fixed value or omitted; it must never follow the point size.
            if let opsz = variation[SymairaFont.axis("opsz")] { XCTAssertEqual(opsz, 18) }
        }
    }

    func testBundledFigtreeRegistersWithoutOpticalSize() throws {
        XCTAssertTrue(SymairaFont.register(), "Figtree.ttf must ship in the SymairaTheme bundle")
        XCTAssertTrue(SymairaFont.isAvailable(.text))
        XCTAssertNil(SymairaFont.Family.text.opticalSize)
        let license = try XCTUnwrap(
            Bundle.module.url(forResource: "Figtree-OFL", withExtension: "txt"), "OFL must ship next to the font")
        XCTAssertTrue(try String(contentsOf: license, encoding: .utf8).contains("SIL OPEN FONT LICENSE"))
        for size in [11.5, 13.5, 27] as [CGFloat] {
            let font = SymairaFont.ctFont(size: size, weight: 550, family: .text)
            XCTAssertEqual(CTFontCopyFamilyName(font) as String, "Figtree")
            let variation = CTFontCopyVariation(font) as? [NSNumber: Double] ?? [:]
            XCTAssertEqual(variation[SymairaFont.axis("wght")], 550)
            XCTAssertNil(variation[SymairaFont.axis("opsz")], "Figtree has no optical size axis")
        }
    }

    /// Only the largest headings (display, screen title) carry the brand; every other role uses Figtree.
    func testRolesSplitBetweenBrandAndTextFamilies() {
        func family(_ role: SymairaFontRole) -> SymairaFont.Family? {
            if case .bundled(let family, _, _, _) = role.source { return family }
            return nil
        }
        let brand = [SymairaTypography.display, SymairaTypography.title]
        let text = [
            SymairaTypography.heading, SymairaTypography.subheading, SymairaTypography.readout, SymairaTypography.stat,
            SymairaTypography.body, SymairaTypography.bodyEmphasized, SymairaTypography.bodyMedium,
            SymairaTypography.label, SymairaTypography.callout, SymairaTypography.caption, SymairaTypography.micro,
        ]
        for role in brand { XCTAssertEqual(family(role), .brand) }
        for role in text { XCTAssertEqual(family(role), .text) }
        XCTAssertNil(family(SymairaTypography.mono))
    }

    func testPackagedResourcesResolveWithoutTheBuildCache() throws {
        let resources = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: resources, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: resources) }
        let shipped = resources.appendingPathComponent("symaira-corekit_SymairaTheme.bundle")
        try FileManager.default.copyItem(at: Bundle.module.bundleURL, to: shipped)
        let resolved = try XCTUnwrap(SymairaThemeResources.packagedBundle(in: resources))
        XCTAssertEqual(resolved.bundleURL.standardizedFileURL, shipped.standardizedFileURL)
        let font = try XCTUnwrap(resolved.url(forResource: "GoogleSansFlex", withExtension: "ttf"))
        XCTAssertTrue(font.path.hasPrefix(shipped.path + "/"))
        XCTAssertNotNil(resolved.url(forResource: "GoogleSansFlex-OFL", withExtension: "txt"))
        XCTAssertNotNil(resolved.url(forResource: "Figtree", withExtension: "ttf"))
        XCTAssertNotNil(resolved.url(forResource: "Figtree-OFL", withExtension: "txt"))
        XCTAssertNil(SymairaThemeResources.packagedBundle(in: nil))
    }

    /// Automatic optical sizing widened 13.5 pt text by about 6 %; the fixed size must not.
    func testFixedOpticalSizeKeepsSmallTextNarrow() {
        SymairaFont.register()
        func width(_ font: CTFont) -> Double {
            let text = NSAttributedString(
                string: "Energie & Kühlung · Lüfterprofil Standard",
                attributes: [NSAttributedString.Key(kCTFontAttributeName as String): font])
            return CTLineGetTypographicBounds(CTLineCreateWithAttributedString(text), nil, nil, nil)
        }
        func explicit(opsz: Double) -> CTFont {
            let variation: [NSNumber: Double] = [SymairaFont.axis("wght"): 400, SymairaFont.axis("opsz"): opsz]
            let attributes: [CFString: Any] = [
                kCTFontFamilyNameAttribute: SymairaFont.familyName,
                kCTFontVariationAttribute: variation,
            ]
            return CTFontCreateWithFontDescriptor(
                CTFontDescriptorCreateWithAttributes(attributes as CFDictionary), 13.5, nil)
        }
        let fixed = SymairaFont.ctFont(size: 13.5, weight: 400)
        // Optical size following the point size is what made small UI text look letter-spaced.
        XCTAssertLessThan(width(explicit(opsz: 18)), width(explicit(opsz: 13.5)) * 0.97, "opsz must affect width")
        XCTAssertEqual(width(fixed), width(explicit(opsz: 18)), accuracy: 0.01)
    }

    func testEmptyStateSymbolSizeIsAToken() {
        XCTAssertEqual(SymairaMetrics.emptyStateSymbolSize, 36 * SymairaMetrics.platformScale)
    }

    #if os(macOS)
    /// #512: wrapped body text sits 1.5 × the point size apart; the typeface alone gives 1.2.
    @MainActor
    func testWrappedTextKeepsTheTokenLineHeight() throws {
        SymairaFont.register()
        let sample = "Erste Zeile des Hinweises\nZweite Zeile des Hinweises"
        for (role, size, lineHeight) in [
            (SymairaTypography.body, 13.5, 1.5), (SymairaTypography.caption, 11.5, 1.4),
        ] as [(SymairaFontRole, CGFloat, CGFloat)] {
            guard case .bundled(let family, _, let weight, _) = role.source else { return XCTFail("bundled role") }
            let plain = Font(SymairaFont.ctFont(size: size, weight: weight, family: family))
            let styled = try XCTUnwrap(ImageRenderer(content: Text(sample).font(role)).cgImage)
            let natural = try XCTUnwrap(ImageRenderer(content: Text(sample).font(plain)).cgImage)
            let expected = size * (lineHeight - family.naturalLineHeight)
            XCTAssertEqual(CGFloat(styled.height - natural.height), expected, accuracy: 1, "\(size) pt")
        }
    }

    @MainActor
    func testRolesPreserveMacOSRendering() throws {
        SymairaFont.register()
        let roles = [
            SymairaTypography.display, SymairaTypography.title, SymairaTypography.heading,
            SymairaTypography.subheading, SymairaTypography.body, SymairaTypography.bodyEmphasized,
            SymairaTypography.bodyMedium, SymairaTypography.label, SymairaTypography.callout,
            SymairaTypography.caption, SymairaTypography.micro, SymairaTypography.readout,
            SymairaTypography.stat, SymairaTypography.mono, SymairaTypography.monoSmall,
        ]
        for role in roles {
            let baseline: Font
            switch role.source {
            case .bundled(let family, let size, let weight, _):
                let font = Font(SymairaFont.ctFont(size: size, weight: weight, family: family))
                baseline = role.tabularDigits ? font.monospacedDigit() : font
            case .system(let font): baseline = font
            }
            let sample = "Energie & Kühlung 0123456789"
            let current = try XCTUnwrap(ImageRenderer(content: Text(sample).font(role)).cgImage)
            let previous = try XCTUnwrap(ImageRenderer(content: Text(sample).font(baseline)).cgImage)
            XCTAssertEqual(current.width, previous.width)
            XCTAssertEqual(current.height, previous.height)
            let currentPixels = try XCTUnwrap(current.dataProvider?.data) as Data
            let previousPixels = try XCTUnwrap(previous.dataProvider?.data) as Data
            XCTAssertEqual(currentPixels, previousPixels)
        }
    }
    #endif
}
