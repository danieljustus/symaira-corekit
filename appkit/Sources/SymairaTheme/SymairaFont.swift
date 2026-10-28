import CoreText
import Foundation
import SwiftUI

#if canImport(AppKit) && !targetEnvironment(macCatalyst)
import AppKit
#else
import UIKit
#endif

/// The two bundled Symaira typefaces.
///
/// Google Sans Flex carries the brand: display, titles, headings and metrics.
/// Inter carries running text, labels and captions, where it stays more legible
/// at 11 to 14 pt. Both variable fonts ship unmodified in this module's bundle
/// (SIL Open Font License 1.1, see `Resources/Fonts`), so they may be used
/// commercially and on every platform. They are registered for the current
/// process on first use, so apps need no `Info.plist` entry.
///
/// Every font is built with a fixed optical size per family. Core Text would
/// otherwise derive the optical size from the point size, which makes Google
/// Sans Flex below 14 pt about 5 to 8 % wider and look letter-spaced.
public enum SymairaFont {
    /// Which bundled typeface a role uses.
    public enum Family: Hashable, Sendable {
        /// Google Sans Flex: display, titles, headings, metrics.
        case brand
        /// Inter: running text, labels, captions.
        case text

        /// Family name as registered with Core Text.
        public var name: String {
            switch self {
            case .brand: SymairaFont.familyName
            case .text: SymairaFont.textFamilyName
            }
        }

        /// Fixed optical size used for every role of this family.
        public var opticalSize: Double {
            switch self {
            case .brand: SymairaFont.opticalSize
            case .text: SymairaFont.textOpticalSize
            }
        }

        var resource: String {
            switch self {
            case .brand: "GoogleSansFlex"
            case .text: "Inter"
            }
        }
    }

    public static let familyName = "Google Sans Flex"
    /// Optical size of Google Sans Flex. Approved in the Cockpit design pilot.
    public static let opticalSize: Double = 18
    public static let textFamilyName = "Inter"
    /// Optical size of Inter: its text cut, the small end of the axis (14 to 32).
    public static let textOpticalSize: Double = 14

    /// Registers both bundled fonts once per process. Returns `false` when
    /// either is neither bundled nor already available (that family then falls
    /// back to the system font, see ``isAvailable(_:)``).
    @discardableResult
    public static func register() -> Bool { brandRegistration && textRegistration }

    /// Whether Google Sans Flex can be used in this process.
    public static var isAvailable: Bool { brandRegistration }

    /// Whether the given family can be used in this process.
    public static func isAvailable(_ family: Family) -> Bool {
        switch family {
        case .brand: brandRegistration
        case .text: textRegistration
        }
    }

    private static let brandRegistration = registerBundled(.brand)
    private static let textRegistration = registerBundled(.text)

    private static func registerBundled(_ family: Family) -> Bool {
        if let url = SymairaThemeResources.bundle.url(forResource: family.resource, withExtension: "ttf") {
            // Fails harmlessly when the file is already registered in this process.
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
        }
        // Decide by the actual result, not by error codes: the family must resolve.
        let descriptor = CTFontDescriptorCreateWithAttributes([kCTFontFamilyNameAttribute: family.name] as CFDictionary)
        let probe = CTFontCreateWithFontDescriptor(descriptor, 12, nil)
        return CTFontCopyFamilyName(probe) as String == family.name
    }

    /// A Core Text font with the family's fixed optical size and the given weight axis.
    public static func ctFont(size: CGFloat, weight: Double, family: Family = .brand) -> CTFont {
        let variation: [NSNumber: Double] = [axis("wght"): weight, axis("opsz"): family.opticalSize]
        let attributes: [CFString: Any] = [
            kCTFontFamilyNameAttribute: family.name,
            kCTFontVariationAttribute: variation,
        ]
        return CTFontCreateWithFontDescriptor(
            CTFontDescriptorCreateWithAttributes(attributes as CFDictionary), size, nil)
    }

    /// A view-resolved role, scaling live with Dynamic Type relative to `textStyle`.
    /// Apply with `View.font(_:)`; concrete `Font`/`Text` consumers must migrate to views.
    public static func font(
        size: CGFloat, weight: Double, relativeTo textStyle: Font.TextStyle, family: Family = .brand
    ) -> SymairaFontRole {
        SymairaFontRole(source: .bundled(family: family, size: size, weight: weight, relativeTo: textStyle))
    }

    /// The caller has already resolved the point size in its current view environment.
    static func resolvedFont(size: CGFloat, weight: Double, family: Family = .brand) -> Font {
        guard isAvailable(family) else {
            return Font.system(size: size, weight: systemWeight(weight))
        }
        #if canImport(AppKit) && !targetEnvironment(macCatalyst)
        return Font(ctFont(size: size, weight: weight, family: family) as NSFont)
        #else
        return Font(ctFont(size: size, weight: weight, family: family) as UIFont)
        #endif
    }

    static func axis(_ tag: String) -> NSNumber {
        NSNumber(value: tag.unicodeScalars.reduce(0) { ($0 << 8) | Int($1.value) })
    }

    static func systemWeight(_ weight: Double) -> Font.Weight {
        switch weight {
        case ..<450: .regular
        case ..<550: .medium
        case ..<675: .semibold
        default: .bold
        }
    }

}
