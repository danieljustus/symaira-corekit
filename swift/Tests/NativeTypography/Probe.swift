import CoreText
import SwiftUI
import SymairaTheme
import UIKit

struct Sizes: PreferenceKey {
    static let defaultValue: [String: CGSize] = [:]
    static func reduce(value: inout [String: CGSize], nextValue: () -> [String: CGSize]) {
        value.merge(nextValue(), uniquingKeysWith: { _, new in new })
    }
}

/// Observes the font inherited below the production modifier, never a reconstructed recipe.
struct FontReceipt: View {
    @Environment(\.font) private var font
    @Environment(\.self) private var environment
    let name: String
    let report: (String, [String: Any]) -> Void

    var body: some View {
        Color.clear.onAppear(perform: record)
            .onChange(of: font) { _, _ in record() }
            .onChange(of: environment.dynamicTypeSize) { _, _ in record() }
    }

    private func record() {
        if #available(iOS 26, *), let font {
            let resolved = font.resolve(in: environment.fontResolutionContext)
            var axes: [String: Double] = [:]
            // Core Text omits axes at their default; opsz 18 is the bundled font's default.
            for axis in CTFontCopyVariationAxes(resolved.ctFont) as? [[CFString: Any]] ?? [] {
                if let id = axis[kCTFontVariationAxisIdentifierKey] as? NSNumber,
                    let value = axis[kCTFontVariationAxisDefaultValueKey] as? Double
                {
                    axes[id.stringValue] = value
                }
            }
            for (id, value) in CTFontCopyVariation(resolved.ctFont) as? [NSNumber: Double] ?? [:] {
                axes[id.stringValue] = value
            }
            report(
                name, ["size": resolved.pointSize, "family": CTFontCopyFamilyName(resolved.ctFont), "variation": axes])
        }
    }
}

@main
struct ProbeApp: App {
    var body: some Scene { WindowGroup { Probe() } }
}

struct Probe: View {
    @State private var size: DynamicTypeSize = .large
    @State private var sizes: [String: CGSize] = [:]
    @State private var fonts: [String: [String: Any]] = [:]
    @State private var phase = "large"
    private let sample = "Energie 0123456789"
    private let roles: [(String, SymairaFontRole)] = [
        ("display", SymairaTypography.display), ("title", SymairaTypography.title),
        ("heading", SymairaTypography.heading), ("subheading", SymairaTypography.subheading),
        ("body", SymairaTypography.body), ("bodyEmphasized", SymairaTypography.bodyEmphasized),
        ("bodyMedium", SymairaTypography.bodyMedium), ("label", SymairaTypography.label),
        ("callout", SymairaTypography.callout), ("caption", SymairaTypography.caption),
        ("micro", SymairaTypography.micro), ("readout", SymairaTypography.readout),
        ("stat", SymairaTypography.stat), ("mono", SymairaTypography.mono),
        ("monoSmall", SymairaTypography.monoSmall),
    ]

    private func measured(_ name: String, text: String? = nil) -> some View {
        Text(text ?? sample).fixedSize()
            .background {
                GeometryReader { proxy in
                    Color.clear.preference(key: Sizes.self, value: [name: proxy.size])
                }
            }
            .background { FontReceipt(name: name) { key, value in fonts[key] = value } }
    }

    var body: some View {
        ScrollView([.horizontal, .vertical]) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Passive live typography: \(phase)").font(.system(size: 12))
                ForEach(roles, id: \.0) { name, role in measured(name).font(role) }
                measured("modifier-body").symairaText(.body)
                measured("modifier-title").symairaText(.title)
                measured("tabular-1", text: "111111").font(SymairaTypography.stat)
                measured("tabular-8", text: "888888").font(SymairaTypography.stat)
            }.padding(20)
        }
        .dynamicTypeSize(size)
        .onPreferenceChange(Sizes.self) { sizes = $0 }
        .task {
            var results: [String: Any] = [
                "fontAvailable": SymairaFont.isAvailable,
                "processID": ProcessInfo.processInfo.processIdentifier,
                "mountedViewRun": UUID().uuidString,
                "osVersion": ProcessInfo.processInfo.operatingSystemVersionString,
            ]
            // The same mounted hierarchy changes environment, never rootView or process.
            for (name, value) in [
                ("large", DynamicTypeSize.large), ("accessibility5", .accessibility5), ("large-restored", .large),
            ] {
                phase = name
                size = value
                try? await Task.sleep(for: .seconds(2))
                results[name] = sizes.mapValues { ["width": $0.width, "height": $0.height] }
                results[name + "-resolved"] = fonts
                let window = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
                    .flatMap(\.windows).first!
                let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
                    window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
                }
                try! image.pngData()!.write(to: URL.documentsDirectory.appendingPathComponent(name + ".png"))
            }
            try! JSONSerialization.data(withJSONObject: results, options: [.prettyPrinted, .sortedKeys])
                .write(to: URL.documentsDirectory.appendingPathComponent("results.json"))
        }
    }
}
