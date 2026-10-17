import CoreText
import Foundation
import SwiftUI

#if canImport(AppKit) && !targetEnvironment(macCatalyst)
import AppKit
#else
import UIKit
#endif

/// Google Sans Flex, the Symaira brand and UI typeface.
///
/// The variable font ships unmodified in this module's bundle (SIL Open Font
/// License 1.1, see `Resources/Fonts`). It is registered for the current
/// process on first use, so apps need no `Info.plist` entry.
///
/// Every font is built with a fixed optical size (`opsz` 18). Core Text would
/// otherwise derive the optical size from the point size, which makes text
/// below 14 pt about 5 to 8 % wider and look letter-spaced.
public enum SymairaFont {
    public static let familyName = "Google Sans Flex"
    /// Optical size used for every role. Approved in the Cockpit design pilot.
    public static let opticalSize: Double = 18

    /// Registers the bundled font once per process. Returns `false` only when
    /// the font is neither bundled nor already available (callers then fall
    /// back to the system font, see ``isAvailable``).
    @discardableResult
    public static func register() -> Bool { registration }

    /// Whether Google Sans Flex can be used in this process.
    public static var isAvailable: Bool { registration }

    private static let registration: Bool = {
        if let url = SymairaThemeResources.bundle.url(forResource: "GoogleSansFlex", withExtension: "ttf") {
            // Fails harmlessly when the file is already registered in this process.
            CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
        }
        // Decide by the actual result, not by error codes: the family must resolve.
        let probe = CTFontCreateWithName("GoogleSansFlex-Regular" as CFString, 12, nil)
        return CTFontCopyFamilyName(probe) as String == familyName
    }()

    /// A Core Text font with a fixed optical size and the given weight axis.
    public static func ctFont(size: CGFloat, weight: Double) -> CTFont {
        let variation: [NSNumber: Double] = [axis("wght"): weight, axis("opsz"): opticalSize]
        let attributes: [CFString: Any] = [
            kCTFontFamilyNameAttribute: familyName,
            kCTFontVariationAttribute: variation,
        ]
        return CTFontCreateWithFontDescriptor(
            CTFontDescriptorCreateWithAttributes(attributes as CFDictionary), size, nil)
    }

    /// A view-resolved role, scaling live with Dynamic Type relative to `textStyle`.
    /// Apply with `View.font(_:)`; concrete `Font`/`Text` consumers must migrate to views.
    public static func font(size: CGFloat, weight: Double, relativeTo textStyle: Font.TextStyle) -> SymairaFontRole {
        SymairaFontRole(source: .brand(size: size, weight: weight, relativeTo: textStyle))
    }

    /// The caller has already resolved the point size in its current view environment.
    static func resolvedFont(size: CGFloat, weight: Double) -> Font {
        guard isAvailable else {
            return Font.system(size: size, weight: systemWeight(weight))
        }
        #if canImport(AppKit) && !targetEnvironment(macCatalyst)
        return Font(ctFont(size: size, weight: weight) as NSFont)
        #else
        return Font(ctFont(size: size, weight: weight) as UIFont)
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
