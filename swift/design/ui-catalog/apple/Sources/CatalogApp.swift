import SwiftUI
import SymairaTheme
#if os(macOS)
import AppKit
#endif

// Symaira UI-Katalog: every element of ../elements.json with its Apple variants side by side.
// Launch arguments: -ui-catalog-item <ID> [-variant <A|B|C|D>] [-appearance light|dark]

struct CatalogVariant: Decodable, Identifiable, Hashable {
    let id: String
    let title: String
    let kind: String
    let code: String
}

struct CatalogElement: Decodable, Identifiable, Hashable {
    let id: String
    let group: String
    let title: String
    let job: String
    let glass: Bool
    let modal: Bool
    let apple: [CatalogVariant]
}

struct CatalogFile: Decodable { let elements: [CatalogElement] }

@MainActor
enum Catalog {
    static let elements: [CatalogElement] = {
        guard let url = Bundle.main.url(forResource: "elements", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let file = try? JSONDecoder().decode(CatalogFile.self, from: data)
        else { return [] }
        return file.elements
    }()
    /// Daniel's choice per element (selection.json, decided 2026-11-25): element ID -> Apple variant.
    static let chosen: [String: String] = {
        struct Choice: Decodable { let apple: String }
        struct File: Decodable { let elements: [String: Choice] }
        guard let url = Bundle.main.url(forResource: "selection", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let file = try? JSONDecoder().decode(File.self, from: data)
        else { return [:] }
        return file.elements.mapValues(\.apple)
    }()
    static let groups: [String] = elements.reduce(into: []) { if !$0.contains($1.group) { $0.append($1.group) } }

    static let args = ProcessInfo.processInfo.arguments
    static func arg(_ name: String) -> String? {
        guard let i = args.firstIndex(of: name), i + 1 < args.count else { return nil }
        return args[i + 1]
    }
    static var requestedItem: String? { arg("-ui-catalog-item") }
    static var requestedVariant: String? { arg("-variant") }
    static var solo: Bool { args.contains("-solo") }
    static var windowFile: String? { arg("-window-file") }
    static var tourDir: String? { arg("-ui-catalog-tour") }
    static var colorScheme: ColorScheme? {
        switch arg("-appearance") { case "dark": .dark; case "light": .light; default: nil }
    }
}

@main
struct UICatalogApp: App {
    #if os(macOS)
    @NSApplicationDelegateAdaptor(TourAppDelegate.self) private var tourDelegate
    #endif
    var body: some Scene {
        WindowGroup("Symaira UI-Katalog") {
            Group {
                if Catalog.tourDir != nil {
                    TourLauncher()
                } else if let id = Catalog.requestedItem, let element = Catalog.elements.first(where: { $0.id == id }) {
                    ElementPage(element: element, autoPresent: Catalog.requestedVariant,
                                only: Catalog.solo ? Catalog.requestedVariant : nil)
                        .onAppear(perform: WindowReporter.scheduleReport)
                } else {
                    CatalogBrowser()
                }
            }
            .preferredColorScheme(Catalog.colorScheme)
            #if os(macOS)
            .frame(minWidth: 1180, minHeight: 640)
            #endif
        }
        #if os(macOS)
        .defaultSize(width: 1180, height: 780)
        #endif
    }
}

struct CatalogBrowser: View {
    @State private var selection: String? = Catalog.elements.first?.id
    @State private var query = ""

    private var filtered: [CatalogElement] {
        query.isEmpty ? Catalog.elements
            : Catalog.elements.filter { $0.title.localizedCaseInsensitiveContains(query) || $0.id.localizedCaseInsensitiveContains(query) }
    }

    var body: some View {
        NavigationSplitView {
            List(selection: $selection) {
                ForEach(Catalog.groups, id: \.self) { group in
                    Section(group) {
                        ForEach(filtered.filter { $0.group == group }) { element in
                            NavigationLink(value: element.id) {
                                LabeledContent {
                                    Text(Catalog.chosen[element.id] ?? "–").font(.caption.monospaced())
                                } label: {
                                    Label { Text(element.title) } icon: { Text(element.id).font(.caption.monospaced()) }
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("UI-Katalog")
            .searchable(text: $query, prompt: "Element suchen")
        } detail: {
            if let id = selection, let element = Catalog.elements.first(where: { $0.id == id }) {
                ElementPage(element: element, autoPresent: nil, only: nil)
            } else {
                ContentUnavailableView("Element wählen", systemImage: "square.grid.2x2")
            }
        }
    }
}

struct ElementPage: View {
    let element: CatalogElement
    let autoPresent: String?
    let only: String?

    private var columns: [GridItem] {
        #if os(macOS)
        [GridItem(.adaptive(minimum: 270, maximum: 420), spacing: 16, alignment: .top)]
        #else
        [GridItem(.adaptive(minimum: 300), spacing: 16, alignment: .top)]
        #endif
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(element.id) · \(element.group)").font(.caption.monospaced()).foregroundStyle(.secondary)
                    Text(element.title).font(.title2.bold())
                    Text(element.job).foregroundStyle(.secondary)
                }
                LazyVGrid(columns: columns, alignment: .leading, spacing: 16) {
                    ForEach(element.apple.filter { only == nil || $0.id == only }) { variant in
                        VariantCell(element: element, variant: variant,
                                    autoPresent: autoPresent == variant.id)
                    }
                }
            }
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .accessibilityIdentifier("catalog.\(element.id)")
    }
}

struct VariantCell: View {
    let element: CatalogElement
    let variant: CatalogVariant
    let autoPresent: Bool

    private var isChosen: Bool { Catalog.chosen[element.id] == variant.id }

    private var kindLabel: String {
        switch variant.kind {
        case "apple-native": "Apple nativ"
        case "native-tinted": "Nativ + Symaira-Tint"
        case "apple-glass": "Liquid Glass"
        case "symaira": "Symaira-Eigenbau"
        default: variant.kind
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(variant.id)
                    .font(.headline.monospaced())
                    .frame(width: 26, height: 26)
                    .background(Color.primary.opacity(0.08), in: .rect(cornerRadius: 6))
                VStack(alignment: .leading, spacing: 2) {
                    Text(variant.title).font(.subheadline.weight(.semibold))
                    Text(kindLabel).font(.caption).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                if isChosen {
                    Label("Gewählt", systemImage: "checkmark.circle.fill")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(SymairaTokens.selected)
                }
            }
            Text(variant.code)
                .font(.caption2.monospaced())
                .foregroundStyle(.secondary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            demoArea(backdrop: false, autoPresent: autoPresent)
            if element.glass {
                Text("Über Inhalt").font(.caption2).foregroundStyle(.secondary)
                demoArea(backdrop: true, autoPresent: false)
            }
        }
        .padding(12)
        .overlay(RoundedRectangle(cornerRadius: 14)
            .strokeBorder(isChosen ? SymairaTokens.selected : Color.primary.opacity(0.12), lineWidth: isChosen ? 2 : 1))
    }
}

extension VariantCell {
    func demoArea(backdrop: Bool, autoPresent: Bool) -> some View {
        ZStack {
            if backdrop { DemoBackdrop() }
            DemoView(elementID: element.id, variant: variant.id, autoPresent: autoPresent)
                .padding(14)
        }
        .frame(maxWidth: .infinity, minHeight: backdrop ? 110 : 130)
        .background(Color.primary.opacity(0.03))
        .clipShape(.rect(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Color.primary.opacity(0.10)))
    }
}

/// Busy, calm content behind glass demos so refraction is visible.
struct DemoBackdrop: View {
    var body: some View {
        ZStack {
            LinearGradient(colors: [Color(red: 0.86, green: 0.80, blue: 0.70), Color(red: 0.40, green: 0.45, blue: 0.52)],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
            VStack(alignment: .leading, spacing: 6) {
                ForEach(0..<7) { i in
                    Text(i.isMultiple(of: 2) ? "Inhalt unter dem Glas · 412 GB" : "Liste · Zeile \(i) · Status ok")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.85))
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(10)
        }
    }
}

/// Writes the window numbers for scripted `screencapture -l` (macOS only).
@MainActor
enum WindowReporter {
    static func scheduleReport() {
        #if os(macOS)
        guard let path = Catalog.windowFile else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
            let lines = NSApplication.shared.windows.filter(\.isVisible).map { w in
                "\(w.windowNumber) \(Int(w.frame.width)) \(Int(w.frame.height)) \(w.sheetParent != nil || w.isSheet ? "sheet" : "main")"
            }
            try? lines.joined(separator: "\n").write(toFile: path, atomically: true, encoding: .utf8)
        }
        #endif
    }
}

/// Placeholder for the SwiftUI scene during a tour; the tour window comes from TourAppDelegate.
struct TourLauncher: View {
    var body: some View { Color.clear }
    #if os(macOS)
    nonisolated(unsafe) static var window: NSWindow?
    #endif
}

#if os(macOS)
/// Reports key/main state so AppKit-drawn parts (Liquid Glass, title bar) render as active while the
/// app stays in the background. Only used for the capture tour.
final class BackgroundKeyWindow: NSWindow {
    override var isKeyWindow: Bool { true }
    override var isMainWindow: Bool { true }
    // AppKit's internal appearance queries (title bar, NSSwitch, Liquid Glass).
    @objc func _hasActiveAppearance() -> Bool { true }
    @objc func _hasActiveAppearanceIgnoringKeyFocus() -> Bool { true }
    @objc func _hasKeyAppearance() -> Bool { true }
    @objc func _hasActiveControls() -> Bool { true }
    @objc func hasKeyAppearance() -> Bool { true }

    /// Private AppKit switch used by NSSwitch and friends; called via the runtime, no-op if absent.
    func forceActiveControls() {
        let sel = NSSelectorFromString("_setForceActiveControls:")
        guard responds(to: sel), let imp = method(for: sel) else { return }
        typealias Setter = @convention(c) (AnyObject, Selector, Bool) -> Void
        unsafeBitCast(imp, to: Setter.self)(self, sel, true)
    }
}

/// Principal class: during the capture tour the app reports itself as active although it never
/// takes the focus, so AppKit draws every control in its active state. Interactive use is unaffected.
@objc(TourApplication)
final class TourApplication: NSApplication {
    private let tour = ProcessInfo.processInfo.arguments.contains("-ui-catalog-tour")
    override var isActive: Bool { tour ? true : super.isActive }
    @objc func _isActiveApp() -> Bool { tour ? true : isActive }
}

/// Creates the tour window at launch, independent of SwiftUI scenes (which stay passive under
/// `open -g`). The window is ordered back and the app is never activated.
final class TourAppDelegate: NSObject, NSApplicationDelegate {
    /// Keeps the occluded background app out of App Nap, which otherwise stalls the tour timers.
    nonisolated(unsafe) static var activity: NSObjectProtocol?

    @MainActor func applicationDidFinishLaunching(_ notification: Notification) {
        guard let dir = Catalog.tourDir else { return }
        TourAppDelegate.activity = ProcessInfo.processInfo.beginActivity(
            options: [.userInitiated, .idleSystemSleepDisabled], reason: "UI catalog capture tour")
        let window = BackgroundKeyWindow(contentRect: NSRect(x: 40, y: 40, width: 1180, height: 780),
                              styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "Symaira UI-Katalog"
        window.isReleasedWhenClosed = false
        window.isRestorable = false
        if let scheme = Catalog.colorScheme {
            window.appearance = NSAppearance(named: scheme == .dark ? .darkAqua : .aqua)
        }
        window.forceActiveControls()
        TourLauncher.window = window  // before the content: TourView.run() reads it
        window.contentView = NSHostingView(rootView: TourView(dir: dir).preferredColorScheme(Catalog.colorScheme))
        window.orderBack(nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            for other in NSApplication.shared.windows where other !== window { other.orderOut(nil) }
        }
    }
}
#endif

/// Scripted capture tour (macOS): shows every element (modal ones once per variant), writes
/// `ready.txt` with "<name> <window number> <sheet number or 0>" and waits until capture.py deletes it.
/// Runs entirely in the background (`open -g`, window ordered back, never activated).
struct TourView: View {
    let dir: String
    struct Job: Hashable { let element: CatalogElement; let variant: String? }
    private let jobs: [Job] = Catalog.elements.flatMap { el in
        el.modal ? el.apple.map { Job(element: el, variant: $0.id) } : [Job(element: el, variant: nil)]
    }
    @State private var index = 0

    var body: some View {
        Group {
            if index < jobs.count {
                let job = jobs[index]
                ElementPage(element: job.element, autoPresent: job.variant, only: nil)
                    .id(job)
            } else {
                Text("Fertig").font(.title)
            }
        }
        #if os(macOS)
        // The app stays in the background; render SwiftUI controls in the key-window state anyway.
        .environment(\.controlActiveState, .key)
        #endif
        .task { await run() }
    }

    private func run() async {
        #if os(macOS)
        let ready = URL(fileURLWithPath: dir).appendingPathComponent("ready.txt")
        while TourLauncher.window == nil { try? await Task.sleep(for: .milliseconds(100)) }
        while index < jobs.count {
            guard let window = TourLauncher.window else { return }
            // Background only: never activate, keep the window behind every other window.
            window.orderBack(nil)
            try? await Task.sleep(for: .seconds(1.6))
            let sheet = window.attachedSheet?.windowNumber ?? 0
            let job = jobs[index]
            let name = job.variant.map { "\(job.element.id)_\($0)" } ?? job.element.id
            try? "\(name) \(window.windowNumber) \(sheet)".write(to: ready, atomically: true, encoding: .utf8)
            while FileManager.default.fileExists(atPath: ready.path) {
                try? await Task.sleep(for: .milliseconds(100))
            }
            index += 1
        }
        try? "done".write(to: URL(fileURLWithPath: dir).appendingPathComponent("done.txt"), atomically: true, encoding: .utf8)
        NSApplication.shared.terminate(nil)
        #endif
    }
}
