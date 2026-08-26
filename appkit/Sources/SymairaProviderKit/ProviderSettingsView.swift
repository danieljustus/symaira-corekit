import SwiftUI

/// Reusable provider picker backed by the shared descriptor registry.
public struct SymairaProviderPicker: View {
    @Binding private var selection: String
    private let catalog: SymairaProviderCatalog
    private let title: String

    public init(
        selection: Binding<String>,
        catalog: SymairaProviderCatalog = .bundled,
        title: String = "Provider"
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
    }
}

/// A secure provider key field that writes only on an explicit user action.
public struct SymairaProviderCredentialField: View {
    private let providerID: String
    private let store: SymairaProviderCredentialStore
    private let title: String
    private let onCredentialChange: (() -> Void)?
    @State private var value: String
    @State private var saved = false
    @State private var errorMessage: String?

    public init(
        providerID: String,
        store: SymairaProviderCredentialStore = SymairaProviderCredentialStore(),
        title: String = "API key",
        onCredentialChange: (() -> Void)? = nil
    ) {
        self.providerID = providerID
        self.store = store
        self.title = title
        self.onCredentialChange = onCredentialChange
        self._value = State(initialValue: (try? store.credential(for: providerID)) ?? "")
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                SecureField(title, text: $value)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit(save)
                if saved {
                    Text("Saved")
                        .foregroundStyle(.green)
                        .font(.caption)
                } else {
                    Button("Save", action: save)
                        .disabled(value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            if !value.isEmpty {
                Button("Remove saved key", role: .destructive, action: delete)
                    .font(.caption)
            }
            if let errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .contain)
    }

    private func save() {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        do {
            _ = try store.save(trimmed, for: providerID)
            value = trimmed
            errorMessage = nil
            saved = true
            onCredentialChange?()
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(2))
                saved = false
            }
        } catch {
            errorMessage = SymairaSecretRedactor.redact(error.localizedDescription)
            saved = false
        }
    }

    private func delete() {
        guard store.delete(for: providerID) else {
            errorMessage = "The saved credential could not be removed."
            return
        }
        value = ""
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
        title: String = "Model"
    ) {
        self._selection = selection
        self.models = models
        self.title = title
    }

    public var body: some View {
        if models.isEmpty {
            Text("No model list available — enter a model in the host app.")
                .font(.caption)
                .foregroundStyle(.secondary)
        } else {
            Picker(title, selection: $selection) {
                ForEach(models) { model in
                    Text(model.displayName).tag(model.id)
                }
            }
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
    private let credentialStore: SymairaProviderCredentialStore
    private let credentialResolver: SymairaCredentialResolver
    private let httpClient: any SymairaProviderHTTPClient

    @State private var baseURLText = ""
    @State private var modelText = ""
    @State private var discoveredModels: [SymairaProviderModel] = []
    @State private var isLoadingModels = false
    @State private var isTesting = false
    @State private var statusMessage: String?

    public init(
        providerID: Binding<String>,
        catalog: SymairaProviderCatalog = .bundled,
        credentialStore: SymairaProviderCredentialStore = SymairaProviderCredentialStore(),
        credentialResolver: SymairaCredentialResolver = SymairaCredentialResolver(),
        httpClient: any SymairaProviderHTTPClient = SymairaURLSessionHTTPClient()
    ) {
        self._providerID = providerID
        self.catalog = catalog
        self.credentialStore = credentialStore
        self.credentialResolver = credentialResolver
        self.httpClient = httpClient
    }

    public var body: some View {
        Form {
            SymairaProviderPicker(selection: $providerID, catalog: catalog)

            if let descriptor {
                SymairaProviderCredentialField(
                    providerID: descriptor.id,
                    store: credentialStore,
                    onCredentialChange: { statusMessage = nil }
                )
                .id(descriptor.id)

                if descriptor.baseURLOverridable || descriptor.baseURLRequiredOverride {
                    TextField("Base URL", text: $baseURLText)
                        .textContentType(.URL)
                        .autocorrectionDisabled()
                }

                if descriptor.models.mode == .configured || descriptor.models.mode == .deployment {
                    TextField("Model or deployment", text: $modelText)
                        .autocorrectionDisabled()
                } else {
                    SymairaModelPicker(selection: $modelText, models: modelsForDisplay(descriptor))
                    if descriptor.models.mode == .discovered {
                        Button(isLoadingModels ? "Loading…" : "Refresh models", action: loadModels)
                            .disabled(isLoadingModels)
                    }
                }

                HStack {
                    Button(isTesting ? "Testing…" : "Test connection", action: testConnection)
                        .disabled(isTesting)
                    if let statusMessage {
                        Text(statusMessage)
                            .font(.caption)
                            .foregroundStyle(statusMessage.hasPrefix("Connected") ? .green : .red)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
        .onAppear(perform: synchronizeState)
        .onChange(of: providerID) { _, _ in synchronizeState() }
    }

    private var descriptor: SymairaProviderDescriptor? {
        catalog.provider(id: providerID) ?? catalog.providers.first
    }

    private func modelsForDisplay(_ descriptor: SymairaProviderDescriptor) -> [SymairaProviderModel] {
        if !discoveredModels.isEmpty { return discoveredModels }
        guard let defaultModel = descriptor.models.defaultModel else { return [] }
        return [SymairaProviderModel(id: defaultModel)]
    }

    private func synchronizeState() {
        guard let descriptor else { return }
        baseURLText = descriptor.baseURL?.absoluteString ?? ""
        modelText = descriptor.models.defaultModel ?? ""
        discoveredModels = []
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
                discoveredModels = models
                if modelText.isEmpty { modelText = models.first?.id ?? "" }
                statusMessage = "Loaded \(models.count) model(s)."
            } catch {
                statusMessage = SymairaSecretRedactor.redact(error.localizedDescription)
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
                let latency = Int((result.latency * 1_000).rounded())
                statusMessage = "Connected in \(latency) ms."
            } catch {
                statusMessage = SymairaSecretRedactor.redact(error.localizedDescription)
            }
        }
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
