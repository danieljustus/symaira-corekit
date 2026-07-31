import XCTest
import SwiftUI
@testable import SymairaTheme

final class TypographyTests: XCTestCase {
    func testScaleEntriesAreDistinctWhereTheyShouldBe() {
        let roles: [Font] = [
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
        XCTAssertEqual(SymairaTextRole.title.foreground(for: .dark), SymairaTheme.textPrimary)
        XCTAssertEqual(
            SymairaTextRole.secondary.foreground(for: .dark),
            SymairaTheme.foregroundSecondary(for: .dark)
        )
        XCTAssertEqual(
            SymairaTextRole.caption.foreground(for: .light),
            SymairaTheme.foregroundMuted(for: .light)
        )
    }

    func testOnlyTheSectionLabelCarriesTracking() {
        XCTAssertEqual(SymairaTextRole.sectionLabel.tracking, 0.6)
        for role in [SymairaTextRole.display, .title, .body, .caption, .mono] {
            XCTAssertEqual(role.tracking, 0, "\(role) must not add tracking")
        }
    }

    func testEmptyStateSymbolSizeIsAToken() {
        XCTAssertEqual(SymairaMetrics.emptyStateSymbolSize, 36)
    }
}
