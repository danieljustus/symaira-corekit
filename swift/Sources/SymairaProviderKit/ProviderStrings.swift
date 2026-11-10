import Foundation

/// User-facing strings of the provider settings views, resolved from this
/// module's `Localizable.strings` (English and German, English fallback).
@usableFromInline
enum ProviderStrings {
    @usableFromInline static var provider: String { string("provider.title", "Provider") }
    @usableFromInline static var apiKey: String { string("provider.apiKey", "API key") }
    @usableFromInline static var model: String { string("provider.model", "Model") }
    static var saved: String { string("provider.saved", "Saved") }
    static var save: String { string("provider.save", "Save") }
    static var removeKey: String { string("provider.removeKey", "Remove saved key") }
    static var removeFailed: String {
        string("provider.removeFailed", "The saved credential could not be removed.")
    }
    static var noModels: String {
        string("provider.noModels", "No model list available — enter a model in the host app.")
    }
    static var baseURL: String { string("provider.baseURL", "Base URL") }
    static var modelOrDeployment: String { string("provider.modelOrDeployment", "Model or deployment") }
    static var loading: String { string("provider.loading", "Loading…") }
    static var refreshModels: String { string("provider.refreshModels", "Refresh models") }
    static var testing: String { string("provider.testing", "Testing…") }
    static var testConnection: String { string("provider.testConnection", "Test connection") }
    static func loadedModels(_ count: Int) -> String {
        String(format: string("provider.loadedModels", "Loaded %lld model(s)."), count)
    }
    static func connected(milliseconds: Int) -> String {
        String(format: string("provider.connected", "Connected in %lld ms."), milliseconds)
    }

    static let bundle = Bundle.module

    static func string(_ key: String, _ english: String, bundle: Bundle = ProviderStrings.bundle) -> String {
        bundle.localizedString(forKey: key, value: english, table: nil)
    }
}
