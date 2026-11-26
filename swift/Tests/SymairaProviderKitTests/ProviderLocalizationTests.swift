import Foundation
import XCTest

@testable import SymairaProviderKit

/// Provider settings copy resolves from the module's compiled strings (#197).
final class ProviderLocalizationTests: XCTestCase {
    private func table(_ language: String) throws -> Bundle {
        let path = try XCTUnwrap(ProviderStrings.bundle.path(forResource: language, ofType: "lproj"))
        return try XCTUnwrap(Bundle(path: path))
    }

    private func keys(_ language: String) throws -> Set<String> {
        let url = try XCTUnwrap(try table(language).url(forResource: "Localizable", withExtension: "strings"))
        return Set(try XCTUnwrap(NSDictionary(contentsOf: url) as? [String: String]).keys)
    }

    func testEnglishAndGermanCarryTheSameKeys() throws {
        XCTAssertFalse(try keys("en").isEmpty)
        XCTAssertEqual(try keys("de"), try keys("en"))
    }

    func testGermanCopyAndFormats() throws {
        let german = try table("de")
        XCTAssertEqual(ProviderStrings.string("provider.testConnection", "", bundle: german), "Verbindung testen")
        let connected = ProviderStrings.string("provider.connected", "", bundle: german)
        XCTAssertEqual(String(format: connected, 42), "Verbunden in 42 ms.")
        let english = try table("en")
        XCTAssertEqual(ProviderStrings.string("provider.testConnection", "", bundle: english), "Test Connection")
        XCTAssertEqual(ProviderStrings.string("provider.removeKey", "", bundle: english), "Remove API Key")
        XCTAssertEqual(ProviderStrings.string("provider.removeKey", "", bundle: german), "API-Schlüssel entfernen")
    }

    func testModelCountUsesSingularAndPluralInBothLanguages() throws {
        let english = try table("en")
        let german = try table("de")
        XCTAssertEqual(ProviderStrings.loadedModels(0, bundle: english), "Loaded 0 models.")
        XCTAssertEqual(ProviderStrings.loadedModels(1, bundle: english), "Loaded 1 model.")
        XCTAssertEqual(ProviderStrings.loadedModels(3, bundle: english), "Loaded 3 models.")
        XCTAssertEqual(ProviderStrings.loadedModels(0, bundle: german), "0 Modelle geladen.")
        XCTAssertEqual(ProviderStrings.loadedModels(1, bundle: german), "1 Modell geladen.")
        XCTAssertEqual(ProviderStrings.loadedModels(3, bundle: german), "3 Modelle geladen.")
    }
}
