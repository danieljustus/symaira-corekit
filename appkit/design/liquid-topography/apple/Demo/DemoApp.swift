// Native Demo für Liquid Topography (macOS). Build: apple/Demo/build.sh
import SwiftUI
import AppKit

@main
struct LiquidTopographyDemo: App {
    init() { NSApplication.shared.setActivationPolicy(.regular); NSApplication.shared.activate() }
    var body: some Scene {
        WindowGroup("Symaira Liquid Topography") { DemoView().frame(minWidth: 1000, minHeight: 680) }
    }
}

struct DemoView: View {
    @State private var topo = SymairaTopoModel()
    @State private var expanded = false
    @State private var text = ""
    // Explicit, passive benchmark inputs; never coupled to a real agent or credentials.
    private let benchmark = ProcessInfo.processInfo.environment["SYMAIRA_TOPO_BENCHMARK"]

    var body: some View {
        NavigationSplitView {
            List {
                Section("Heute") {
                    Label("Vault-Policy für Brain prüfen", systemImage: "checkmark.shield")
                    Label("symaira.com Hero überarbeiten", systemImage: "globe")
                    Label("Cockpit Lüfterkurve M4", systemImage: "fan")
                }
            }
            .navigationSplitViewColumnWidth(272)
        } detail: {
            ZStack {
                SymairaTokens.canvas.ignoresSafeArea()
                if benchmark != "off" {
                    SymairaTopoView(model: topo, animationEnabled: benchmark != "static").ignoresSafeArea()
                }
                VStack(spacing: 20) {
                    Spacer()
                    VStack(alignment: .leading, spacing: 12) {
                        Button { withAnimation(.snappy) { expanded.toggle() }; ripple(at: .zero) } label: {
                            Label("4 Dateien gelesen · 2 Tests ausgeführt", systemImage: expanded ? "chevron.down" : "chevron.right")
                                .font(.system(size: 12.5, weight: .semibold))
                        }.buttonStyle(.plain).foregroundStyle(SymairaTokens.ink2)
                        if expanded {
                            Text("brain/internal/policy/profiles.go\nbrain/internal/policy/groups.go")
                                .font(.system(size: 12, design: .monospaced)).foregroundStyle(SymairaTokens.ink2)
                        }
                        Text("Ein Leck gefunden, Fix liegt bereit").font(.system(size: 16, weight: .bold))
                        Text("Das Profil agent-default erbt vault.manage über die Gruppe human-ui.")
                            .foregroundStyle(SymairaTokens.ink2)
                    }
                    .padding(.horizontal, 18).padding(.vertical, 16)
                    .frame(maxWidth: 640, alignment: .leading)
                    .background(SymairaTokens.surface, in: .rect(cornerRadius: SymairaTokens.Radius.lg))
                    .topoProtected(in: topo, hill: true)

                    HStack {
                        TextField("Frag Symaira oder beschreib eine Aufgabe …", text: $text)
                            .textFieldStyle(.plain).font(.system(size: 14.5, weight: .medium))
                            .onSubmit { topo.state = .thinking }
                        Button { topo.state = .thinking } label: { Image(systemName: "arrow.up").fontWeight(.bold).frame(width: 22, height: 22) }
                            .buttonStyle(.glassProminent).buttonBorderShape(.circle).tint(SymairaTokens.primary)
                    }
                    .padding(.horizontal, 18).padding(.vertical, 14)
                    .frame(maxWidth: 640)
                    .background(SymairaTokens.surface, in: .rect(cornerRadius: SymairaTokens.Radius.xl))
                    .topoProtected(in: topo, hill: true)
                    .padding(.bottom, 24)
                }
                .padding(.horizontal, 28)
            }
            .coordinateSpace(name: SymairaTopo.space)
            .toolbar {
                Picker("Zustand", selection: $topo.state) {
                    Text("Bereit").tag(SymairaTopoState.idle)
                    Text("Denkt nach").tag(SymairaTopoState.thinking)
                    Text("Problem").tag(SymairaTopoState.problem)
                    Text("Wartet").tag(SymairaTopoState.input)
                }.pickerStyle(.segmented)
            }
        }
        .fontWeight(.medium)
        // Glas-Regel: Seitenleiste + Toolbar = natives Liquid Glass (NavigationSplitView/Toolbar),
        // Inhaltsflächen bleiben deckend. Die Topografie liegt dahinter und scheint durch die Sidebar.
        .containerBackground(for: .window) { SymairaTokens.canvas }
        .preferredColorScheme(benchmark == nil ? nil : .dark)
        .task {
            guard let benchmark else { return }
            if benchmark == "hidden" {
                try? await Task.sleep(for: .seconds(1))
                if let window = NSApp.windows.first(where: { $0.title == "Symaira Liquid Topography" }) {
                    window.orderOut(nil)
                    try? await Task.sleep(for: .seconds(1))
                    NSLog("TOPO_BENCH hidden=%d visible=%d", window.isVisible ? 0 : 1, window.occlusionState.contains(.visible) ? 1 : 0)
                } else {
                    NSLog("TOPO_BENCH missing-window")
                }
            }
            guard benchmark == "interaction" else { return }
            topo.state = .thinking
            var step = 0.0
            while !Task.isCancelled {
                // Deterministic model inputs, NOT evidence of real pointer event delivery.
                topo.pointer = CGPoint(x: 350 + 120 * sin(step), y: 240 + 80 * cos(step))
                topo.pointerVelocity = 0.6
                topo.pressed = true
                step += 0.05
                do { try await Task.sleep(for: .milliseconds(50)) } catch { break }
            }
        }
    }

    private func ripple(at p: CGPoint) { topo.ripple(at: CGPoint(x: 400, y: 300), strength: 0.7) }
}
