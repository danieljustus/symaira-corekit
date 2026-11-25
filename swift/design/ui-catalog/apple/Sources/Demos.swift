import SwiftUI
import SymairaTheme

// One demo per element ID; `variant` selects A/B/C/D exactly as listed in elements.json.

struct DemoView: View {
    let elementID: String
    let variant: String
    let autoPresent: Bool

    var body: some View {
        switch elementID {
        case "E01": PrimaryButtonDemo(v: variant)
        case "E02": SecondaryButtonDemo(v: variant)
        case "E03": DestructiveButtonDemo(v: variant)
        case "E04": IconButtonDemo(v: variant)
        case "E05": ToolbarGroupDemo(v: variant)
        case "E06": MenuDemo(v: variant)
        case "E07": SegmentDemo(v: variant)
        case "E08": SwitchDemo(v: variant)
        case "E09": PickerDemo(v: variant)
        case "E10": SliderDemo(v: variant)
        case "E11": StepperDemo()
        case "E12": DateDemo(v: variant)
        case "E13": TextFieldDemo(v: variant)
        case "E14": SecureDemo(v: variant)
        case "E15": SearchDemo(v: variant)
        case "E16": TextEditorDemo(v: variant)
        case "E17": FormDemo(v: variant)
        case "E18": GroupDemo(v: variant)
        case "E19": ProgressDemo(v: variant)
        case "E20": NoticeDemo(v: variant)
        case "E21": BadgeDemo(v: variant)
        case "E22": StatusDemo(v: variant)
        case "E23": EmptyDemo(v: variant)
        case "E24": LoadingDemo(v: variant)
        case "E25": ConfirmDemo(v: variant, autoPresent: autoPresent)
        case "E26": SheetDemo(v: variant, autoPresent: autoPresent)
        case "E27": SidebarDemo(v: variant)
        case "E28": TabsDemo(v: variant)
        case "E29": AppearanceDemo(v: variant)
        case "E30": ListDemo(v: variant)
        case "E31": TableDemo(v: variant)
        case "E32": DisclosureDemo(v: variant)
        case "E33": StatDemo(v: variant)
        default: Text("Keine Demo für \(elementID)").foregroundStyle(.secondary)
        }
    }
}

// MARK: - Aktionen

struct PrimaryButtonDemo: View {
    let v: String
    var body: some View {
        VStack(spacing: 10) {
            row("Speichern", enabled: true)
            row("Deaktiviert", enabled: false)
        }
    }
    @ViewBuilder func row(_ title: String, enabled: Bool) -> some View {
        switch v {
        case "A": Button(title) {}.buttonStyle(.borderedProminent).controlSize(.large).disabled(!enabled)
        case "B": Button(title) {}.buttonStyle(.borderedProminent).tint(SymairaTokens.selected).controlSize(.large).disabled(!enabled)
        case "C": Button(title) {}.buttonStyle(.glassProminent).controlSize(.large).disabled(!enabled)
        default: Button(title) {}.symairaButtonStyle(.primary).disabled(!enabled)
        }
    }
}

struct SecondaryButtonDemo: View {
    let v: String
    var body: some View {
        VStack(spacing: 10) {
            row("Abbrechen", enabled: true)
            row("Deaktiviert", enabled: false)
        }
    }
    @ViewBuilder func row(_ title: String, enabled: Bool) -> some View {
        switch v {
        case "A": Button(title) {}.buttonStyle(.bordered).controlSize(.large).disabled(!enabled)
        case "B": Button(title) {}.buttonStyle(.glass).controlSize(.large).disabled(!enabled)
        case "C": Button(title) {}.buttonStyle(.borderless).controlSize(.large).disabled(!enabled)
        default: Button(title) {}.symairaButtonStyle(.secondary).disabled(!enabled)
        }
    }
}

struct DestructiveButtonDemo: View {
    let v: String
    var body: some View {
        switch v {
        case "A": Button("Projekt löschen", role: .destructive) {}.buttonStyle(.bordered).controlSize(.large)
        case "B": Button("Projekt löschen", role: .destructive) {}.buttonStyle(.borderedProminent).tint(.red).controlSize(.large)
        default: Button("Projekt löschen", role: .destructive) {}.buttonStyle(.bordered).tint(SymairaTokens.critical).controlSize(.large)
        }
    }
}

struct IconButtonDemo: View {
    let v: String
    private let items: [(String, String, SymairaIcon)] = [
        ("Aktualisieren", "arrow.clockwise", .refresh), ("Teilen", "square.and.arrow.up", .share),
        ("Löschen", "trash", .delete),
    ]
    var body: some View {
        HStack(spacing: 12) {
            ForEach(items, id: \.0) { item in
                switch v {
                case "A":
                    Button { } label: { Label(item.0, systemImage: item.1).labelStyle(.iconOnly) }
                        .buttonStyle(.bordered).buttonBorderShape(.circle).controlSize(.large).help(item.0)
                case "B":
                    Button { } label: { Label(item.0, systemImage: item.1).labelStyle(.iconOnly) }
                        .buttonStyle(.glass).buttonBorderShape(.circle).controlSize(.large).help(item.0)
                default:
                    SymairaIconButton(item.0, icon: item.2) {}
                }
            }
        }
    }
}

struct ToolbarGroupDemo: View {
    let v: String
    var body: some View {
        switch v {
        case "A":
            GlassEffectContainer(spacing: 8) {
                HStack(spacing: 8) {
                    Button { } label: { Image(systemName: "sidebar.left") }.buttonStyle(.glass)
                    Button { } label: { Image(systemName: "arrow.clockwise") }.buttonStyle(.glass)
                    Button { } label: { Image(systemName: "gearshape") }.buttonStyle(.glass)
                }
                .controlSize(.large)
            }
        case "B":
            ControlGroup {
                Button { } label: { Label("Seitenleiste", systemImage: "sidebar.left") }
                Button { } label: { Label("Aktualisieren", systemImage: "arrow.clockwise") }
                Button { } label: { Label("Einstellungen", systemImage: "gearshape") }
            }
            .labelStyle(.iconOnly)
            .controlSize(.large)
            .fixedSize()
        default:
            SymairaGlassEffectContainer {
                HStack(spacing: 4) {
                    SymairaIconButton("Seitenleiste", icon: .sidebar) {}
                    SymairaIconButton("Aktualisieren", icon: .refresh) {}
                    SymairaIconButton("Einstellungen", icon: .settings) {}
                }
                .padding(6)
                .symairaGlassChrome()
            }
        }
    }
}

struct MenuDemo: View {
    let v: String
    @State private var status = "alle"
    private let options: [(value: String, label: String)] = [("alle", "Alle Status"), ("ok", "Läuft"), ("warn", "Warnung"), ("err", "Fehler")]
    var body: some View {
        switch v {
        case "A":
            Menu {
                ForEach(options, id: \.value) { o in Button(o.label) { status = o.value } }
            } label: { Label("Filter", systemImage: "line.3.horizontal.decrease.circle") }
            .fixedSize()
        case "B":
            Picker("Status", selection: $status) {
                ForEach(options, id: \.value) { o in Text(o.label).tag(o.value) }
            }
            .pickerStyle(.menu).fixedSize()
        default:
            SymairaFilterMenu("Status", selection: $status, options: options)
        }
    }
}

// MARK: - Auswahl

struct SegmentDemo: View {
    let v: String
    @State private var mode = "auto"
    private let options: [(value: String, label: String)] = [("leise", "Leise"), ("auto", "Auto"), ("max", "Maximal")]
    var body: some View {
        switch v {
        case "A":
            Picker("Lüfterprofil", selection: $mode) { ForEach(options, id: \.value) { Text($0.label).tag($0.value) } }
                .pickerStyle(.segmented).labelsHidden()
        case "B":
            Picker("Lüfterprofil", selection: $mode) { ForEach(options, id: \.value) { Text($0.label).tag($0.value) } }
                .pickerStyle(.segmented).labelsHidden().tint(SymairaTokens.selected)
        default:
            SymairaSegmentedControl("Lüfterprofil", selection: $mode, options: options)
        }
    }
}

struct SwitchDemo: View {
    let v: String
    @State private var on = true
    @State private var off = false
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            toggle("Automatisch sichern", $on)
            toggle("Beim Anmelden starten", $off)
        }
        .frame(maxWidth: 260)
    }
    @ViewBuilder func toggle(_ title: String, _ binding: Binding<Bool>) -> some View {
        switch v {
        case "A": Toggle(title, isOn: binding).toggleStyle(.switch)
        case "B": Toggle(title, isOn: binding).toggleStyle(.switch).tint(SymairaTokens.selected)
        case "C":
            #if os(macOS)
            Toggle(title, isOn: binding).toggleStyle(.checkbox)
            #else
            Text("Checkbox gibt es nur auf macOS").font(.caption).foregroundStyle(.secondary)
            #endif
        default: Toggle(title, isOn: binding).toggleStyle(.symairaSwitch)
        }
    }
}

struct PickerDemo: View {
    let v: String
    @State private var model = "lokal"
    var body: some View {
        switch v {
        case "A":
            Picker("Modell", selection: $model) { options }.pickerStyle(.menu).frame(maxWidth: 260)
        case "B":
            #if os(macOS)
            Picker("Modell", selection: $model) { options }.pickerStyle(.radioGroup)
            #else
            Picker("Modell", selection: $model) { options }.pickerStyle(.inline)
            #endif
        default:
            SymairaFormSection {
                SymairaFormRow("Modell", description: "Wird für neue Chats genutzt") {
                    Picker("Modell", selection: $model) { options }.pickerStyle(.menu).labelsHidden().fixedSize()
                }
            }
        }
    }
    @ViewBuilder var options: some View {
        Text("Lokal").tag("lokal"); Text("Schnell").tag("schnell"); Text("Gründlich").tag("gruendlich")
    }
}

struct SliderDemo: View {
    let v: String
    @State private var value = 0.62
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Lautstärke \(Int(value * 100)) %").font(.callout)
            if v == "A" { Slider(value: $value) } else { Slider(value: $value).tint(SymairaTokens.ink) }
        }
        .frame(maxWidth: 260)
    }
}

struct StepperDemo: View {
    @State private var count = 3
    var body: some View {
        Stepper("Parallele Läufe: \(count)", value: $count, in: 1...8).frame(maxWidth: 260)
    }
}

struct DateDemo: View {
    let v: String
    @State private var date = Date(timeIntervalSince1970: 1_795_000_000)
    var body: some View {
        switch v {
        case "A": DatePicker("Termin", selection: $date)
        case "B":
            #if os(macOS)
            DatePicker("Termin", selection: $date).datePickerStyle(.field)
            #else
            DatePicker("Termin", selection: $date).datePickerStyle(.wheel).labelsHidden().frame(maxHeight: 160)
            #endif
        default: DatePicker("Termin", selection: $date, displayedComponents: .date).datePickerStyle(.graphical).labelsHidden().frame(maxWidth: 300)
        }
    }
}

// MARK: - Eingabe

struct TextFieldDemo: View {
    let v: String
    @State private var name = "Symaira Vault"
    @State private var empty = ""
    var body: some View {
        switch v {
        case "A":
            VStack(spacing: 8) {
                TextField("Name", text: $name).textFieldStyle(.roundedBorder)
                TextField("Beschreibung (optional)", text: $empty).textFieldStyle(.roundedBorder)
            }.frame(maxWidth: 280)
        case "B":
            Form {
                TextField("Name", text: $name)
                TextField("Beschreibung", text: $empty, prompt: Text("optional"))
            }
            .formStyle(.grouped).scrollDisabled(true).frame(maxWidth: 320, maxHeight: 130)
        default:
            VStack(spacing: 8) {
                TextField("Name", text: $name).textFieldStyle(.symaira)
                TextField("Beschreibung (optional)", text: $empty).textFieldStyle(.symaira)
            }.frame(maxWidth: 280)
        }
    }
}

struct SecureDemo: View {
    let v: String
    @State private var secret = "geheim123"
    var body: some View {
        Group {
            if v == "A" { SecureField("Passwort", text: $secret).textFieldStyle(.roundedBorder) }
            else { SecureField("Passwort", text: $secret).textFieldStyle(.symaira) }
        }
        .frame(maxWidth: 280)
    }
}

struct SearchDemo: View {
    let v: String
    @State private var query = ""
    var body: some View {
        switch v {
        case "A":
            NavigationStack {
                List(["Vault", "Brain", "Cockpit"], id: \.self) { Text($0) }
                    .searchable(text: $query, prompt: "Suchen")
                    .navigationTitle("Werkzeuge")
                    #if os(iOS)
                    .navigationBarTitleDisplayMode(.inline)
                    #endif
            }
            .frame(height: 220)
            .overlay(alignment: .bottom) {
                #if os(macOS)
                Text("macOS: Suchfeld sitzt in der Fenster-Toolbar (siehe Katalogfenster)").font(.caption2).foregroundStyle(.secondary).padding(4)
                #endif
            }
        case "B":
            HStack {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField("Suchen", text: $query).textFieldStyle(.plain)
            }
            .padding(.horizontal, 10).padding(.vertical, 7)
            .background(.quaternary, in: .capsule)
            .frame(maxWidth: 280)
        default:
            HStack(spacing: 8) {
                SymairaIconView(.search, size: 18)
                TextField("Suchen", text: $query).textFieldStyle(.symaira)
            }
            .frame(maxWidth: 300)
        }
    }
}

struct TextEditorDemo: View {
    let v: String
    @State private var text = "Notiz zum Lauf vom Dienstag.\nAlles grün bis auf den Sync."
    var body: some View {
        switch v {
        case "A":
            TextEditor(text: $text)
                .scrollContentBackground(.hidden)
                .padding(6)
                .background(.background, in: .rect(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(.separator))
                .frame(maxWidth: 300, minHeight: 90, maxHeight: 90)
        case "B":
            TextField("Nachricht", text: $text, axis: .vertical).lineLimit(2...4).textFieldStyle(.roundedBorder).frame(maxWidth: 300)
        default:
            TextEditor(text: $text).scrollContentBackground(.hidden).frame(minHeight: 70, maxHeight: 70)
                .symairaCard(padding: SymairaSpacing.medium).frame(maxWidth: 300)
        }
    }
}

// MARK: - Formulare & Flächen

struct FormDemo: View {
    let v: String
    @State private var sync = true
    @State private var interval = "15"
    @State private var name = "MacBook"
    var body: some View {
        switch v {
        case "A", "B":
            let form = Form {
                Section("Synchronisation") {
                    Toggle("Automatisch synchronisieren", isOn: $sync)
                    Picker("Intervall", selection: $interval) { Text("5 Min.").tag("5"); Text("15 Min.").tag("15"); Text("1 Std.").tag("60") }
                    LabeledContent("Letzter Lauf", value: "vor 3 Min.")
                }
                Section("Gerät") { TextField("Name", text: $name) }
            }
            Group {
                if v == "A" { form.formStyle(.grouped) } else { form.formStyle(.columns) }
            }
            .scrollDisabled(true)
            .frame(maxWidth: 380, minHeight: 250)
        default:
            VStack(spacing: 12) {
                SymairaFormSection("Synchronisation") {
                    SymairaFormRow("Automatisch synchronisieren") { Toggle("", isOn: $sync).labelsHidden().toggleStyle(.symairaSwitch) }
                    SymairaFormDivider()
                    SymairaFormRow("Intervall") {
                        Picker("Intervall", selection: $interval) { Text("5 Min.").tag("5"); Text("15 Min.").tag("15"); Text("1 Std.").tag("60") }
                            .labelsHidden().fixedSize()
                    }
                    SymairaFormDivider()
                    SymairaFormRow("Letzter Lauf") { Text("vor 3 Min.").symairaText(.secondary) }
                }
            }
            .frame(maxWidth: 380)
        }
    }
}

struct GroupDemo: View {
    let v: String
    var body: some View {
        switch v {
        case "A":
            GroupBox("Speicher") { content }.frame(maxWidth: 300)
        case "B":
            List { Section("Speicher") { LabeledContent("Belegt", value: "412 GB"); LabeledContent("Frei", value: "88 GB") } }
                #if os(macOS)
                .listStyle(.inset)
                #else
                .listStyle(.insetGrouped)
                #endif
                .scrollDisabled(true).frame(maxWidth: 320, minHeight: 130)
        default:
            VStack(alignment: .leading, spacing: 8) {
                Text("SPEICHER").symairaText(.sectionLabel)
                content
            }
            .frame(maxWidth: 300, alignment: .leading)
            .symairaCard()
        }
    }
    var content: some View {
        VStack(alignment: .leading, spacing: 6) {
            LabeledContent("Belegt", value: "412 GB")
            LabeledContent("Frei", value: "88 GB")
        }
    }
}

// MARK: - Rückmeldung

struct ProgressDemo: View {
    let v: String
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach([0.0, 0.42, 1.0], id: \.self) { value in
                switch v {
                case "A": ProgressView(value: value) { Text("Import \(Int(value * 100)) %").font(.caption) }
                case "B": Gauge(value: value) { Text("Import") }.gaugeStyle(.accessoryLinearCapacity)
                case "C":
                    HStack { Gauge(value: value) { Text("") } currentValueLabel: { Text("\(Int(value * 100))") }.gaugeStyle(.accessoryCircularCapacity); Spacer() }
                default:
                    ProgressView(value: value) { Text("Import \(Int(value * 100)) %").font(.caption) }.progressViewStyle(SymairaProgressStyle())
                }
            }
        }
        .frame(maxWidth: 280)
    }
}

struct NoticeDemo: View {
    let v: String
    var body: some View {
        VStack(spacing: 8) {
            notice("Update verfügbar", "Version 0.27 kann installiert werden.", "info.circle.fill", .secondary, .neutral)
            notice("Sync verzögert", "Der Server antwortet langsam.", "exclamationmark.triangle.fill", .orange, .warning)
        }
        .frame(maxWidth: 340)
    }
    @ViewBuilder func notice(_ t: String, _ m: String, _ symbol: String, _ color: Color, _ tone: SymairaTone) -> some View {
        switch v {
        case "A":
            GroupBox {
                Label { VStack(alignment: .leading) { Text(t).bold(); Text(m).font(.callout).foregroundStyle(.secondary) } }
                icon: { Image(systemName: symbol).foregroundStyle(color) }
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        case "B":
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: symbol).foregroundStyle(color)
                VStack(alignment: .leading) { Text(t).bold(); Text(m).font(.callout).foregroundStyle(.secondary) }
                Spacer(minLength: 0)
            }
            .padding(12).background(.regularMaterial, in: .rect(cornerRadius: 12))
        default:
            SymairaNotice(title: t, message: m, tone: tone)
        }
    }
}

struct BadgeDemo: View {
    let v: String
    var body: some View {
        switch v {
        case "A":
            List {
                Text("Posteingang").badge(3)
                Text("Fehler").badge(Text("neu"))
            }
            .scrollDisabled(true).frame(maxWidth: 280, minHeight: 100)
        case "B":
            HStack(spacing: 8) {
                capsule("Aktiv", .green); capsule("Warnung", .orange); capsule("Fehler", .red); capsule("Neutral", .secondary)
            }
        default:
            HStack(spacing: 8) {
                SymairaBadge("Aktiv", tone: .positive); SymairaBadge("Warnung", tone: .warning)
                SymairaBadge("Fehler", tone: .critical); SymairaBadge("Neutral")
            }
        }
    }
    func capsule(_ t: String, _ c: Color) -> some View {
        Text(t).font(.caption.weight(.semibold)).foregroundStyle(c)
            .padding(.horizontal, 8).padding(.vertical, 3).background(c.opacity(0.15), in: .capsule)
    }
}

struct StatusDemo: View {
    let v: String
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            switch v {
            case "A":
                Label("Läuft", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                Label("Verzögert", systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                Label("Gestoppt", systemImage: "xmark.octagon.fill").foregroundStyle(.red)
            case "B":
                dot("Läuft", .green); dot("Verzögert", .orange); dot("Gestoppt", .red)
            default:
                SymairaStatusLabel("Läuft", tone: .positive)
                SymairaStatusLabel("Verzögert", tone: .warning)
                SymairaStatusLabel("Gestoppt", tone: .critical)
            }
        }
    }
    func dot(_ t: String, _ c: Color) -> some View {
        HStack(spacing: 6) { Image(systemName: "circle.fill").font(.system(size: 8)).foregroundStyle(c); Text(t) }
    }
}

struct EmptyDemo: View {
    let v: String
    var body: some View {
        if v == "A" {
            ContentUnavailableView {
                Label("Noch keine Einträge", systemImage: "tray")
            } description: { Text("Lege deinen ersten Eintrag an.") } actions: {
                Button("Eintrag anlegen") {}.buttonStyle(.borderedProminent)
            }
        } else {
            SymairaEmptyState(icon: .inbox, title: "Noch keine Einträge", message: "Lege deinen ersten Eintrag an.") {
                Button("Eintrag anlegen") {}.symairaButtonStyle(.primary)
            }
        }
    }
}

struct LoadingDemo: View {
    let v: String
    var body: some View {
        if v == "A" { ProgressView("Lädt Einträge …") } else { SymairaLoadingState("Lädt Einträge …") }
    }
}

struct ConfirmDemo: View {
    let v: String
    let autoPresent: Bool
    @State private var shown = false
    var body: some View {
        switch v {
        case "A":
            Button("Projekt löschen …", role: .destructive) { shown = true }
                .alert("Projekt wirklich löschen?", isPresented: $shown) {
                    Button("Löschen", role: .destructive) {}
                    Button("Abbrechen", role: .cancel) {}
                } message: { Text("Das lässt sich nicht rückgängig machen.") }
                .onAppear { if autoPresent { shown = true } }
        case "B":
            Button("Projekt löschen …", role: .destructive) { shown = true }
                .confirmationDialog("Projekt wirklich löschen?", isPresented: $shown, titleVisibility: .visible) {
                    Button("Löschen", role: .destructive) {}
                    Button("Abbrechen", role: .cancel) {}
                } message: { Text("Das lässt sich nicht rückgängig machen.") }
                .onAppear { if autoPresent { shown = true } }
        default:
            VStack(alignment: .leading, spacing: 10) {
                Text("Projekt wirklich löschen?").symairaText(.heading)
                Text("Das lässt sich nicht rückgängig machen.").symairaText(.secondary)
                HStack {
                    Spacer()
                    Button("Abbrechen") {}.symairaButtonStyle(.secondary)
                    Button("Löschen") {}.symairaButtonStyle(.primary)
                }
            }
            .frame(maxWidth: 340)
            .symairaCard()
        }
    }
}

struct SheetDemo: View {
    let v: String
    let autoPresent: Bool
    @State private var shown = false
    @State private var name = "Neues Projekt"
    var body: some View {
        if v == "A" {
            Button("Projekt anlegen …") { shown = true }
                .sheet(isPresented: $shown) {
                    NavigationStack {
                        Form { TextField("Name", text: $name); Toggle("Als Favorit", isOn: .constant(true)) }
                            .formStyle(.grouped)
                            .navigationTitle("Neues Projekt")
                            .toolbar {
                                ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { shown = false } }
                                ToolbarItem(placement: .confirmationAction) { Button("Anlegen") { shown = false } }
                            }
                    }
                    .frame(minWidth: 380, minHeight: 220)
                }
                .onAppear { if autoPresent { shown = true } }
        } else {
            SymairaSheetScaffold(title: "Neues Projekt", dismiss: {}, primaryTitle: "Anlegen") {
                SymairaFormSection {
                    SymairaFormRow("Name") { TextField("Name", text: $name).textFieldStyle(.symaira).frame(maxWidth: 180) }
                }
            }
            .frame(maxWidth: 380, minHeight: 240)
        }
    }
}

// MARK: - Navigation & Daten

struct SidebarDemo: View {
    let v: String
    @State private var selection: String? = "Übersicht"
    private let items = [("Übersicht", "square.grid.2x2", SymairaIcon.dashboard), ("Dokumente", "doc", .document), ("Einstellungen", "gearshape", .settings)]
    var body: some View {
        if v == "A" {
            NavigationSplitView {
                List(selection: $selection) {
                    ForEach(items, id: \.0) { Label($0.0, systemImage: $0.1).tag(Optional($0.0)) }
                }
                .listStyle(.sidebar)
                .navigationSplitViewColumnWidth(160)
            } detail: {
                Text(selection ?? "").font(.title3).frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .frame(height: 220)
        } else {
            HStack(spacing: 0) {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(items, id: \.0) { item in
                        SymairaNavigationButton(item.0, icon: item.2, isSelected: selection == item.0) { selection = item.0 }
                    }
                    Spacer()
                }
                .padding(8)
                .frame(width: 170)
                .background(SymairaTokens.sidebar)
                Text(selection ?? "").symairaText(.heading).frame(maxWidth: .infinity, maxHeight: .infinity).background(SymairaTokens.canvas)
            }
            .frame(height: 220)
            .clipShape(.rect(cornerRadius: 10))
        }
    }
}

struct TabsDemo: View {
    let v: String
    @State private var tab = "start"
    private let options: [(value: String, label: String)] = [("start", "Start"), ("verlauf", "Verlauf"), ("profil", "Profil")]
    var body: some View {
        switch v {
        case "A":
            TabView(selection: $tab) {
                Tab("Start", systemImage: "house", value: "start") { Text("Start").frame(maxWidth: .infinity, maxHeight: .infinity) }
                Tab("Verlauf", systemImage: "clock", value: "verlauf") { Text("Verlauf").frame(maxWidth: .infinity, maxHeight: .infinity) }
                Tab("Profil", systemImage: "person", value: "profil") { Text("Profil").frame(maxWidth: .infinity, maxHeight: .infinity) }
            }
            .frame(height: 220)
        case "B":
            VStack {
                Picker("Bereich", selection: $tab) { ForEach(options, id: \.value) { Text($0.label).tag($0.value) } }
                    .pickerStyle(.segmented).labelsHidden()
                Text(tab.capitalized).frame(maxWidth: .infinity, minHeight: 80)
            }
        default:
            VStack {
                SymairaSegmentedControl("Bereich", selection: $tab, options: options)
                Text(tab.capitalized).frame(maxWidth: .infinity, minHeight: 80)
            }
        }
    }
}

struct AppearanceDemo: View {
    let v: String
    @State private var native = "system"
    @State private var appearance: SymairaAppearance = .system
    var body: some View {
        if v == "A" {
            Picker("Darstellung", selection: $native) { Text("System").tag("system"); Text("Hell").tag("light"); Text("Dunkel").tag("dark") }
                .pickerStyle(.segmented).frame(maxWidth: 320)
        } else {
            SymairaAppearancePicker(selection: $appearance).frame(maxWidth: 320)
        }
    }
}

struct ListDemo: View {
    let v: String
    private let rows = [("Vault", "Läuft"), ("Brain", "Läuft"), ("Desk", "Pausiert")]
    var body: some View {
        switch v {
        case "A":
            List(rows, id: \.0) { LabeledContent($0.0, value: $0.1) }
                .listStyle(.inset).scrollDisabled(true).frame(maxWidth: 320, minHeight: 130)
        case "B":
            List { Section("Werkzeuge") { ForEach(rows, id: \.0) { LabeledContent($0.0, value: $0.1) } } }
                #if os(macOS)
                .listStyle(.plain)
                #else
                .listStyle(.insetGrouped)
                #endif
                .scrollDisabled(true).frame(maxWidth: 320, minHeight: 150)
        default:
            VStack(spacing: 0) {
                ForEach(Array(rows.enumerated()), id: \.offset) { index, row in
                    if index > 0 { SymairaFormDivider() }
                    SymairaFormRow(row.0) { Text(row.1).symairaText(.secondary) }
                }
            }
            .frame(maxWidth: 320).symairaCard()
        }
    }
}

struct TableRowItem: Identifiable { let id: String; let size: String; let changed: String }

struct TableDemo: View {
    let v: String
    private let rows = [TableRowItem(id: "rechnung.pdf", size: "1,2 MB", changed: "Heute"),
                        TableRowItem(id: "vertrag.pdf", size: "640 KB", changed: "Gestern"),
                        TableRowItem(id: "notizen.md", size: "4 KB", changed: "Mo.")]
    var body: some View {
        if v == "A" {
            Table(rows) {
                TableColumn("Name", value: \.id)
                TableColumn("Größe", value: \.size)
                TableColumn("Geändert", value: \.changed)
            }
            .frame(minWidth: 320, minHeight: 150)
        } else {
            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 8) {
                GridRow { Text("NAME"); Text("GRÖSSE"); Text("GEÄNDERT") }.symairaText(.sectionLabel)
                Divider()
                ForEach(rows) { r in GridRow { Text(r.id); Text(r.size).symairaText(.secondary); Text(r.changed).symairaText(.secondary) } }
            }
            .symairaCard()
        }
    }
}

struct DisclosureDemo: View {
    let v: String
    @State private var open = true
    var body: some View {
        let group = DisclosureGroup("Technische Details", isExpanded: $open) {
            VStack(alignment: .leading, spacing: 4) {
                LabeledContent("Version", value: "0.27.0"); LabeledContent("Schema", value: "3")
            }.padding(.top, 6)
        }
        if v == "A" { group.frame(maxWidth: 300) } else { group.frame(maxWidth: 300).symairaCard() }
    }
}

struct StatDemo: View {
    let v: String
    var body: some View {
        switch v {
        case "A":
            VStack(alignment: .leading, spacing: 6) {
                LabeledContent("Speicher belegt", value: "412 GB")
                LabeledContent("Dokumente", value: "1.284")
            }.frame(maxWidth: 260)
        case "B":
            Gauge(value: 0.82) { Text("Speicher") } currentValueLabel: { Text("412 GB") }
                minimumValueLabel: { Text("0") } maximumValueLabel: { Text("500") }
                .frame(maxWidth: 260)
        default:
            HStack(spacing: 12) {
                SymairaStatTile(value: "412 GB", label: "Speicher belegt", detail: "von 500 GB")
                SymairaStatTile(value: "1.284", label: "Dokumente")
            }
        }
    }
}
