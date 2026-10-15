// iOS-Demo für Liquid Topography. Build: apple/Demo/build-ios.sh
import SwiftUI

@main
struct LiquidTopographyiOSDemo: App {
    var body: some Scene { WindowGroup { IOSDemoView() } }
}

struct IOSDemoView: View {
    @State private var topo = SymairaTopoModel()
    @State private var expanded = false

    var body: some View {
        NavigationStack {
            ZStack {
                SymairaTopoView(model: topo).ignoresSafeArea()
                VStack(spacing: 16) {
                    Spacer()
                    VStack(alignment: .leading, spacing: 10) {
                        Button { withAnimation(.snappy) { expanded.toggle() } } label: {
                            Label("4 Dateien gelesen", systemImage: expanded ? "chevron.down" : "chevron.right")
                                .font(.system(size: 13, weight: .semibold))
                        }.foregroundStyle(SymairaTokens.ink2)
                        if expanded { Text("profiles.go\ngroups.go").font(.system(size: 12, design: .monospaced)) }
                        Text("Ein Leck gefunden, Fix liegt bereit").font(.system(size: 17, weight: .bold))
                        Text("agent-default erbt vault.manage über human-ui.").foregroundStyle(SymairaTokens.ink2)
                    }
                    .padding(16).frame(maxWidth: .infinity, alignment: .leading)
                    .background(SymairaTokens.surface, in: .rect(cornerRadius: SymairaTokens.Radius.lg))
                    .topoProtected(in: topo, hill: true)
                }
                .padding(20)
            }
            .coordinateSpace(name: SymairaTopo.space)
            .navigationTitle("Liquid Topography")
            .toolbar {
                ToolbarItem(placement: .bottomBar) {
                    Picker("Zustand", selection: $topo.state) {
                        Text("Bereit").tag(SymairaTopoState.idle)
                        Text("Denkt").tag(SymairaTopoState.thinking)
                        Text("Problem").tag(SymairaTopoState.problem)
                        Text("Wartet").tag(SymairaTopoState.input)
                    }.pickerStyle(.segmented)
                }
            }
        }
        .fontWeight(.medium)
    }
}
