import SwiftUI
import SymairaCLIRunner
import SymairaTheme

@MainActor
protocol ProviderSettingsCredentialStore {
    func credential(for providerID: String) throws -> String?
    func save(_ value: String, for providerID: String) throws -> Bool
    func delete(for providerID: String) -> Bool
    func reference(for providerID: String) -> String
}

extension SymairaProviderCredentialStore: ProviderSettingsCredentialStore {}

/// Two-step removal of a saved key: the first activation only asks, and
/// only an explicit confirmation deletes the stored credential (NN-8).
@MainActor
struct ProviderKeyRemoval {
    private(set) var isConfirming = false

    mutating func request() { isConfirming = true }

    mutating func cancel() { isConfirming = false }

    mutating func confirm(providerID: String, store: any ProviderSettingsCredentialStore) -> Bool {
        isConfirming = false
        return store.delete(for: providerID)
    }
}

/// Reusable provider picker backed by the shared descriptor registry.
public struct SymairaProviderPicker: View {
    @Binding private var selection: String
    private let catalog: SymairaProviderCatalog
    private let title: String

    public init(
        selection: Binding<String>,
        catalog: SymairaProviderCatalog = .bundled,
        title: String = ProviderStrings.provider
    ) {
        self._selection = selection
        self.catalog = catalog
        self.title = title
    }

    public var body: some View {
        Picker(title, selection: $selection) {
            ForEach(catalog.providers) { provider in
                Text(provider.displayName).tag(provider.id)
            }
        }
        .pickerStyle(.menu)
    }
}

/// A secure provider key field that writes only on an explicit user action.
public struct SymairaProviderCredentialField: View {
    private let providerID: String
    private let store: any ProviderSettingsCredentialStore
    private let title: String
    private let onCredentialChange: (() -> Void)?
    @State private var value: String
    @State private var hasStoredKey: Bool
    @State private var removal = ProviderKeyRemoval()
    @State private var saved = false
    @State private var errorMessage: String?

    public init(
        providerID: String,
        store: SymairaProviderCredentialStore = SymairaProviderCredentialStore(),
        title: String = ProviderStrings.apiKey,
        onCredentialChange: (() -> Void)? = nil
    ) {
        self.init(providerID: providerID, credentialStore: store, title: title, onCredentialChange: onCredentialChange)
    }

    init(
        providerID: String,
        credentialStore: any ProviderSettingsCredentialStore,
        title: String = ProviderStrings.apiKey,
        onCredentialChange: (() -> Void)? = nil
    ) {
        self.providerID = providerID
        self.store = credentialStore
        self.title = title
        self.onCredentialChange = onCredentialChange
        let stored = try? credentialStore.credential(for: providerID)
        self._value = State(initialValue: stored ?? "")
        self._hasStoredKey = State(initialValue: stored?.isEmpty == false)
    }

    public var body: some View {
        // A Group yields one native row per child inside a grouped Form (FORM-1).
        Group {
            SecureField(title, text: draft, prompt: Text(ProviderStrings.enterKey))
                .onSubmit(save)
            HStack(spacing: SymairaSpacing.small) { credentialActions }
            if let errorMessage {
                SymairaNotice(message: errorMessage, tone: .critical)
            } else if saved {
                SymairaNotice(message: ProviderStrings.saved, tone: .positive)
            }
        }
        .alert(ProviderStrings.removeKey, isPresented: isConfirmingRemoval) {
            Button(ProviderStrings.removeKey, role: .destructive, action: delete)
            Button(ProviderStrings.cancel, role: .cancel) { removal.cancel() }
        } message: {
            Text(ProviderStrings.removeConsequence)
        }
    }

    @ViewBuilder private var credentialActions: some View {
        Button(ProviderStrings.save, action: save)
            .symairaButtonStyle(.secondary)
            .disabled(value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        if hasStoredKey {
            Button(ProviderStrings.removeKey, role: .destructive) { removal.request() }
                .symairaButtonStyle(.secondary)
        }
    }

    private var isConfirmingRemoval: Binding<Bool> {
        Binding(get: { removal.isConfirming }, set: { if !$0 { removal.cancel() } })
    }

    private var draft: Binding<String> {
        Binding(
            get: { value },
            set: {
                value = $0
                saved = false
                errorMessage = nil
            })
    }

    private func save() {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        do {
            guard try store.save(trimmed, for: providerID) else {
                errorMessage = ProviderStrings.saveFailed
                saved = false
                return
            }
            value = trimmed
            hasStoredKey = true
            errorMessage = nil
            saved = true
            onCredentialChange?()
        } catch {
            errorMessage = SymairaSecretRedactor.redact(error.localizedDescription)
            saved = false
        }
    }

    private func delete() {
        guard removal.confirm(providerID: providerID, store: store) else {
            errorMessage = ProviderStrings.removeFailed
            return
        }
        value = ""
        hasStoredKey = false
        errorMessage = nil
        saved = false
        onCredentialChange?()
    }
}

/// Model picker for static and discovered provider models.
public struct SymairaModelPicker: View {
    @Binding private var selection: String
    private let models: [SymairaProviderModel]
    private let title: String

    public init(
        selection: Binding<String>,
        models: [SymairaProviderModel],
        title: String = ProviderStrings.model
    ) {
        self._selection = selection
        self.models = models
        self.title = title
    }

    public var body: some View {
        if models.isEmpty {
            LabeledContent(title) {
                Text(ProviderStrings.noModels)
                    .symairaText(.caption)
            }
        } else {
            Picker(title, selection: $selection) {
                ForEach(models) { model in
                    Text(model.displayName).tag(model.id)
                }
            }
            .pickerStyle(.menu)
        }
    }
}

/// Complete provider setup surface for host apps.
///
/// It deliberately owns only provider selection, credentials, endpoint/model
/// configuration and connectivity. Agent behavior and usage accounting remain
/// in the consuming app.
public struct SymairaProviderSettingsView: View {
    @Binding private var providerID: String
    private let catalog: SymairaProviderCatalog
    private let credentialStore: any ProviderSettingsCredentialStore
    private let credentialResolver: SymairaCredentialResolver
    private let httpClient: any SymairaProviderHTTPClient

    @State private var baseURLText = ""
    @State private var modelText = ""
    @State private var discoveredModels: [SymairaProviderModel]?
    @State private var isLoadingModels = false
    @State private var isTesting = false
    @State private var statusMessage: String?
    @State private var statusTone: SymairaTone = .neutral

    public init(
        providerID: Binding<String>,
        catalog: SymairaProviderCatalog = .bundled,
        credentialStore: SymairaProviderCredentialStore = SymairaProviderCredentialStore(),
        credentialResolver: SymairaCredentialResolver = SymairaCredentialResolver(),
        httpClient: any SymairaProviderHTTPClient = SymairaURLSessionHTTPClient()
    ) {
        self.init(
            providerID: providerID, catalog: catalog, store: credentialStore,
            credentialResolver: credentialResolver, httpClient: httpClient)
    }

    init(
        providerID: Binding<String>,
        catalog: SymairaProviderCatalog = .bundled,
        store: any ProviderSettingsCredentialStore,
        credentialResolver: SymairaCredentialResolver = SymairaCredentialResolver(),
        httpClient: any SymairaProviderHTTPClient = SymairaURLSessionHTTPClient()
    ) {
        self._providerID = providerID
        self.catalog = catalog
        self.credentialStore = store
        self.credentialResolver = credentialResolver
        self.httpClient = httpClient
    }

    public var body: some View {
        Form {
            Section {
                SymairaProviderPicker(selection: $providerID, catalog: catalog)

                if let descriptor {
                    SymairaProviderCredentialField(
                        providerID: descriptor.id,
                        credentialStore: credentialStore,
                        onCredentialChange: { statusMessage = nil }
                    )
                    .id(descriptor.id)

                    if descriptor.baseURLOverridable || descriptor.baseURLRequiredOverride {
                        TextField(ProviderStrings.baseURL, text: $baseURLText)
                            .textContentType(.URL)
                            .autocorrectionDisabled()
                    }

                    modelRow(descriptor)
                }
            }

            if let descriptor {
                Section { connectionActions(descriptor) }
            }
        }
        .formStyle(.grouped)
        .onAppear(perform: synchronizeState)
        .onChange(of: providerID) { _, _ in synchronizeState() }
    }

    @ViewBuilder private func modelRow(_ descriptor: SymairaProviderDescriptor) -> some View {
        if descriptor.models.mode == .configured || descriptor.models.mode == .deployment {
            TextField(ProviderStrings.modelOrDeployment, text: $modelText)
                .autocorrectionDisabled()
        } else {
            SymairaModelPicker(selection: $modelText, models: modelsForDisplay(descriptor))
        }
    }

    private func connectionActions(_ descriptor: SymairaProviderDescriptor) -> some View {
        Group {
            HStack(spacing: SymairaSpacing.small) {
                Button(ProviderStrings.testConnection, action: testConnection)
                    .symairaButtonStyle(.primary)
                    .disabled(isTesting || isLoadingModels)
                if descriptor.models.mode == .discovered {
                    Button(ProviderStrings.refreshModels, action: loadModels)
                        .symairaButtonStyle(.secondary)
                        .disabled(isTesting || isLoadingModels)
                }
            }
            if isTesting {
                ProgressView(ProviderStrings.testing)
            } else if isLoadingModels {
                ProgressView(ProviderStrings.loading)
            } else if let statusMessage {
                SymairaNotice(message: statusMessage, tone: statusTone)
            }
        }
    }

    private var descriptor: SymairaProviderDescriptor? {
        catalog.provider(id: providerID) ?? catalog.providers.first
    }

    private func modelsForDisplay(_ descriptor: SymairaProviderDescriptor) -> [SymairaProviderModel] {
        if let discoveredModels { return discoveredModels }
        guard let defaultModel = descriptor.models.defaultModel else { return [] }
        return [SymairaProviderModel(id: defaultModel)]
    }

    private func synchronizeState() {
        guard let descriptor else { return }
        baseURLText = descriptor.baseURL?.absoluteString ?? ""
        modelText = descriptor.models.defaultModel ?? ""
        discoveredModels = nil
        statusMessage = nil
    }

    private func makeClient(_ descriptor: SymairaProviderDescriptor) -> SymairaProviderClient {
        let override = URL(string: baseURLText.trimmingCharacters(in: .whitespacesAndNewlines))
        let hasStoredCredential = (try? credentialStore.credential(for: descriptor.id)) != nil
        let credentialReference = hasStoredCredential ? credentialStore.reference(for: descriptor.id) : nil
        let configuration = SymairaProviderConfiguration(
            descriptor: descriptor,
            baseURLOverride: override != descriptor.baseURL ? override : nil,
            credentialReference: credentialReference,
            model: modelText.nilIfEmpty
        )
        return SymairaProviderClient(
            configuration: configuration,
            credentialResolver: credentialResolver,
            httpClient: httpClient
        )
    }

    private func loadModels() {
        guard let descriptor, descriptor.models.mode == .discovered else { return }
        isLoadingModels = true
        statusMessage = nil
        Task { @MainActor in
            defer { isLoadingModels = false }
            do {
                let models = try await makeClient(descriptor).discoverModels()
                guard self.descriptor?.id == descriptor.id else { return }
                discoveredModels = models
                if let first = models.first, !models.contains(where: { $0.id == modelText }) {
                    modelText = first.id
                }
                statusMessage = ProviderStrings.loadedModels(models.count)
                statusTone = .positive
            } catch {
                guard self.descriptor?.id == descriptor.id else { return }
                statusMessage = SymairaSecretRedactor.redact(error.localizedDescription)
                statusTone = .critical
            }
        }
    }

    private func testConnection() {
        guard let descriptor else { return }
        isTesting = true
        statusMessage = nil
        Task { @MainActor in
            defer { isTesting = false }
            do {
                let result = try await makeClient(descriptor).testConnection()
                guard self.descriptor?.id == descriptor.id else { return }
                let latency = Int((result.latency * 1_000).rounded())
                statusMessage = ProviderStrings.connected(milliseconds: latency)
                statusTone = .positive
            } catch {
                guard self.descriptor?.id == descriptor.id else { return }
                statusMessage = SymairaSecretRedactor.redact(error.localizedDescription)
                statusTone = .critical
            }
        }
    }
}

extension String {
    fileprivate var nilIfEmpty: String? { isEmpty ? nil : self }
}
