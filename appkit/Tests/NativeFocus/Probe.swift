import AppKit
import SwiftUI
import SymairaTheme

final class ProbeApplication: NSApplication {
    var receivedKeyCodes: [UInt16] = []

    override func sendEvent(_ event: NSEvent) {
        if event.type == .keyDown {
            receivedKeyCodes.append(event.keyCode)
        }
        super.sendEvent(event)
    }
}

@MainActor
final class Model: ObservableObject {
    @Published var selection = 0
    @Published var isOn = false
    @Published var disabledSelection = 0
    @Published var disabledIsOn = false
}

struct Probe: View {
    @ObservedObject var model: Model
    let colorScheme: ColorScheme

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Text("Passive keyboard probe").symairaText(.heading)
            TextField("Native text input", text: .constant(""))
            SymairaSegmentedControl(
                "Profile", selection: $model.selection,
                options: [(0, "First"), (1, "Second")]
            )
            Toggle("Enabled switch", isOn: $model.isOn)
                .toggleStyle(.symairaSwitch)
            SymairaSegmentedControl(
                "Disabled profile", selection: $model.disabledSelection,
                options: [(0, "Locked first"), (1, "Locked second")]
            )
            .disabled(true)
            Toggle("Disabled switch", isOn: $model.disabledIsOn)
                .toggleStyle(.symairaSwitch)
                .disabled(true)
        }
        .padding(32)
        .frame(width: 560, height: 430)
        .background(SymairaTheme.backgroundPrimary(for: colorScheme))
        .environment(\.colorScheme, colorScheme)
    }
}

@main
@MainActor
enum Main {
    static func main() {
        let app = ProbeApplication.shared
        app.setActivationPolicy(.regular)
        app.finishLaunching()

        let arguments = CommandLine.arguments
        guard arguments.count == 3 else { fatalError("usage: NativeFocusProbe OUTPUT_DIR light|dark") }
        let output = URL(fileURLWithPath: arguments[1], isDirectory: true)
        try! FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let colorScheme: ColorScheme = arguments[2] == "dark" ? .dark : .light
        let model = Model()
        let host = NSHostingView(rootView: Probe(model: model, colorScheme: colorScheme))
        let window = NSWindow(
            contentRect: NSRect(x: 100, y: 100, width: 560, height: 430),
            styleMask: [.titled, .closable], backing: .buffered, defer: false
        )
        window.title = "Symaira native keyboard focus verification"
        window.contentView = host
        window.makeKeyAndOrderFront(nil)
        app.activate(ignoringOtherApps: true)

        Task { @MainActor in
            try? await Task.sleep(for: .seconds(1))
            window.makeKeyAndOrderFront(nil)
            window.makeFirstResponder(host)
            var rows: [[String: Any]] = []

            @MainActor func snapshot(_ step: String) {
                host.layoutSubtreeIfNeeded()
                host.displayIfNeeded()
                if let representation = host.bitmapImageRepForCachingDisplay(in: host.bounds) {
                    host.cacheDisplay(in: host.bounds, to: representation)
                    try! representation.representation(using: .png, properties: [:])!
                        .write(to: output.appendingPathComponent(step + ".png"))
                }
                rows.append([
                    "step": step,
                    "selection": model.selection,
                    "isOn": model.isOn,
                    "disabledSelection": model.disabledSelection,
                    "disabledIsOn": model.disabledIsOn,
                    "firstResponder": String(describing: window.firstResponder),
                    "keyWindow": window.isKeyWindow,
                ])
            }

            snapshot("00-initial")
            let keys: [(String, UInt16, CGEventFlags)] = [
                ("01-tab", 48, []), ("02-space", 49, []),
                ("03-tab", 48, []), ("04-space", 49, []),
                ("05-shift-tab", 48, .maskShift), ("06-space", 49, []),
                ("07-tab", 48, []), ("08-tab", 48, []),
                ("09-space", 49, []), ("10-space", 49, []),
                ("11-tab", 48, []), ("12-space", 49, []),
                ("13-tab", 48, []), ("14-space", 49, []),
                ("15-tab", 48, []),
            ]
            for (step, keyCode, flags) in keys {
                for isKeyDown in [true, false] {
                    let event = CGEvent(keyboardEventSource: nil, virtualKey: keyCode, keyDown: isKeyDown)!
                    event.flags = flags
                    event.postToPid(ProcessInfo.processInfo.processIdentifier)
                }
                try? await Task.sleep(for: .milliseconds(300))
                snapshot(step)
            }

            let result: [String: Any] = [
                "fullKeyboardAccess": app.isFullKeyboardAccessEnabled,
                "keyboardPreference": String(
                    describing: CFPreferencesCopyValue(
                        "AppleKeyboardUIMode" as CFString,
                        kCFPreferencesAnyApplication,
                        kCFPreferencesCurrentUser,
                        kCFPreferencesAnyHost
                    )
                ),
                "received": (app as! ProbeApplication).receivedKeyCodes,
                "input": "CGEvent keyDown/keyUp through NSApplication.sendEvent; no AXPress or programmatic focus",
                "scheme": arguments[2],
                "rows": rows,
            ]
            try! JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys])
                .write(to: output.appendingPathComponent("results.json"))
            app.terminate(nil)
        }
        app.run()
    }
}
