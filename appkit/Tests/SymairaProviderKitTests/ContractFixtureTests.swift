import XCTest
@testable import SymairaProviderKit

final class ContractFixtureTests: XCTestCase {
    func testBundledCatalogMatchesCorekitProviderContractShape() throws {
        let catalog = try SymairaProviderCatalog.load()
        XCTAssertEqual(catalog.schemaVersion, 1)
        XCTAssertEqual(catalog.providers.count, 14)

        let expectedIDs = [
            "anthropic", "openai", "openrouter", "google", "groq", "deepseek", "mistral",
            "xai", "moonshot", "together", "fireworks", "azure-openai", "ollama", "custom",
        ]
        XCTAssertEqual(catalog.providers.map(\.id), expectedIDs)
        XCTAssertEqual(catalog.provider(id: "anthropic")?.auth.header, "x-api-key")
        XCTAssertEqual(catalog.provider(id: "anthropic")?.extraHeaders["anthropic-version"], "2023-06-01")
        XCTAssertEqual(catalog.provider(id: "ollama")?.models.discoveryPath, "/api/tags")
        XCTAssertEqual(catalog.provider(id: "custom")?.baseURLRequiredOverride, true)
        XCTAssertEqual(catalog.provider(id: "custom")?.dialectConfigurable, true)
        XCTAssertEqual(catalog.provider(id: "azure-openai")?.baseURL, nil)
    }

    func testBundledCatalogAndPublicLoaderAreEquivalent() throws {
        XCTAssertEqual(try SymairaProviderCatalog.load(), .bundled)
    }

    func testVendoredRootFixtureMatchesBundledResource() throws {
        let repositoryRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let fixtureURL = repositoryRoot.appendingPathComponent("contracts/llm_providers.json")
        let fixtureCatalog = try SymairaProviderCatalog(data: Data(contentsOf: fixtureURL))

        XCTAssertEqual(fixtureCatalog, .bundled)
    }

    func testVendoredErrorFixtureMatchesBundledTaxonomy() throws {
        let repositoryRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let fixtureURL = repositoryRoot.appendingPathComponent("contracts/llm_errors.json")
        let fixtureCatalog = try SymairaProviderErrorCatalog(data: Data(contentsOf: fixtureURL))

        XCTAssertEqual(fixtureCatalog, .bundled)
        XCTAssertEqual(fixtureCatalog.errors.map(\.code), [
            .authFailure, .rateLimited, .contextOverflow, .modelNotFound, .transportError, .providerError,
        ])
    }

    func testUnknownSchemaIsRejected() {
        XCTAssertThrowsError(
            try SymairaProviderCatalog(data: Data(#"{"schema_version":2,"providers":[]}"#.utf8))
        ) { error in
            XCTAssertEqual(error as? SymairaProviderCatalogError, .unsupportedSchema(2))
        }
    }

    func testDuplicateProviderIDsAreRejected() throws {
        let descriptor = try XCTUnwrap(SymairaProviderCatalog.bundled.providers.first)
        XCTAssertThrowsError(
            try SymairaProviderCatalog(schemaVersion: 1, providers: [descriptor, descriptor])
        ) { error in
            XCTAssertEqual(error as? SymairaProviderCatalogError, .duplicateProviderID(descriptor.id))
        }
    }
}
