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
        for role in [SymairaTextRole.body, .callout, .caption, .mono] {
            XCTAssertEqual(role.tracking, 0, "\(role) must not add tracking")
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

    func testPackagedResourcesResolveWithoutTheBuildCache() throws {
        let resources = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: resources, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: resources) }
        let shipped = resources.appendingPathComponent("symaira-appkit_SymairaTheme.bundle")
        try FileManager.default.copyItem(at: Bundle.module.bundleURL, to: shipped)
        let resolved = try XCTUnwrap(SymairaThemeResources.packagedBundle(in: resources))
        XCTAssertEqual(resolved.bundleURL.standardizedFileURL, shipped.standardizedFileURL)
        let font = try XCTUnwrap(resolved.url(forResource: "GoogleSansFlex", withExtension: "ttf"))
        XCTAssertTrue(font.path.hasPrefix(shipped.path + "/"))
        XCTAssertNotNil(resolved.url(forResource: "GoogleSansFlex-OFL", withExtension: "txt"))
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
        XCTAssertEqual(SymairaMetrics.emptyStateSymbolSize, 36)
    }

    #if os(macOS)
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
            case .brand(let size, let weight, _):
                let font = Font(SymairaFont.ctFont(size: size, weight: weight))
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
