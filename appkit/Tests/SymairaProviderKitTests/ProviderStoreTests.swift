import XCTest
@testable import SymairaProviderKit

@MainActor
final class ProviderStoreTests: XCTestCase {
    func testStoreUsesSharedCatalogAndPersistsOnlyCredentialReferences() throws {
        let catalog = try SymairaProviderCatalog.load()
        let store = SymairaProviderStore(
            providerID: "openai",
            catalog: catalog,
            credentialStore: SymairaProviderCredentialStore(keychain: .init(app: "provider-store-tests"))
        )

        XCTAssertEqual(store.descriptor.id, "openai")
        XCTAssertEqual(store.model, "gpt-5")
        let workspace = store.workspaceConfig()
        XCTAssertEqual(workspace.providerID, "openai")
        XCTAssertNil(workspace.baseURLOverride)
        XCTAssertNil(workspace.credentialReference)
    }

    func testCredentialStoreUsesBoundedKeychainTimeout() {
        let store = SymairaProviderCredentialStore(keychainTimeout: 0.25)

        XCTAssertEqual(store.keychainTimeout, 0.25)
        XCTAssertEqual(
            SymairaProviderCredentialStore.defaultKeychainTimeout,
            5
        )
    }

    func testStoreResetsEndpointAndModelWhenProviderChanges() throws {
        let catalog = try SymairaProviderCatalog.load()
        let store = SymairaProviderStore(providerID: "openai", catalog: catalog)
        store.baseURLText = "https://example.invalid"
        store.model = "custom-model"

        store.selectProvider(id: "anthropic")

        XCTAssertEqual(store.descriptor.id, "anthropic")
        XCTAssertEqual(store.baseURLText, "https://api.anthropic.com")
        XCTAssertEqual(store.model, "claude-sonnet-5-20250915")
        XCTAssertEqual(store.connectionState, .idle)
    }

    func testWorkspaceConfigResolvesAgainstSharedCatalog() throws {
        let catalog = try SymairaProviderCatalog.load()
        let workspace = SymairaWorkspaceConfig(
            providerID: "openrouter",
            baseURLOverride: URL(string: "https://router.example/v1"),
            model: "example/model",
            credentialReference: "env://OPENROUTER_API_KEY"
        )

        let configuration = try workspace.providerConfiguration(in: catalog)

        XCTAssertEqual(configuration.descriptor.id, "openrouter")
        XCTAssertEqual(configuration.baseURLOverride?.absoluteString, "https://router.example/v1")
        XCTAssertEqual(configuration.model, "example/model")
        XCTAssertEqual(configuration.credentialReference, "env://OPENROUTER_API_KEY")
    }

    func testUnknownWorkspaceProviderFailsClosed() throws {
        let workspace = SymairaWorkspaceConfig(providerID: "not-in-catalog")

        XCTAssertThrowsError(try workspace.providerConfiguration()) { error in
            let providerError = error as? SymairaProviderError
            XCTAssertEqual(providerError?.code, .providerError)
        }
    }
}
