import Foundation

/// User-facing strings of the provider settings views, resolved from this
/// module's `Localizable.strings` (English and German, English fallback).
@usableFromInline
enum ProviderStrings {
    @usableFromInline static var provider: String { string("provider.title", "Provider") }
    @usableFromInline static var apiKey: String { string("provider.apiKey", "API Key") }
    @usableFromInline static var model: String { string("provider.model", "Model") }
    static var saved: String { string("provider.saved", "Your API key was saved.") }
    static var save: String { string("provider.save", "Save API Key") }
    static var enterKey: String { string("provider.enterKey", "Enter an API key to save it.") }
    static var saveFailed: String { string("provider.saveFailed", "Could not save your API key. Try again.") }
    static var removeKey: String { string("provider.removeKey", "Remove API Key") }
    static var cancel: String { string("provider.cancel", "Cancel") }
    static var removeConsequence: String {
        string("provider.removeConsequence", "This removes the saved API key for this provider from this device.")
    }
    static var removeFailed: String {
        string("provider.removeFailed", "Could not remove your API key. Try again.")
    }
    static var noModels: String {
        string("provider.noModels", "No model list available — enter a model in the host app.")
    }
    static var baseURL: String { string("provider.baseURL", "Base URL") }
    static var modelOrDeployment: String { string("provider.modelOrDeployment", "Model or Deployment") }
    static var loading: String { string("provider.loading", "Loading models…") }
    static var refreshModels: String { string("provider.refreshModels", "Refresh Models") }
    static var testing: String { string("provider.testing", "Testing connection…") }
    static var testConnection: String { string("provider.testConnection", "Test Connection") }
    static func loadedModels(_ count: Int, bundle: Bundle = ProviderStrings.bundle) -> String {
        let fallback = count == 1 ? "Loaded %lld model." : "Loaded %lld models."
        return String.localizedStringWithFormat(string("provider.loadedModels", fallback, bundle: bundle), count)
    }
    static func connected(milliseconds: Int) -> String {
        String(format: string("provider.connected", "Connected in %lld ms."), milliseconds)
    }

    static let bundle = Bundle.module

    static func string(_ key: String, _ english: String, bundle: Bundle = ProviderStrings.bundle) -> String {
        bundle.localizedString(forKey: key, value: english, table: nil)
    }
}
