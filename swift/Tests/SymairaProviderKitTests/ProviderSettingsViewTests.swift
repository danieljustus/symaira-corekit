#if os(macOS)
import AppKit
import SwiftUI
import XCTest

@testable import SymairaProviderKit

@MainActor
final class ProviderSettingsViewTests: XCTestCase {
    func testSettingsRendersInBothAppearances() throws {
        let provider = "ollama"
        let store = InMemoryCredentialStore(provider: provider)
        _ = NSApplication.shared
        for scheme in [ColorScheme.light, .dark] {
            let host = NSHostingView(
                rootView: SymairaProviderSettingsView(providerID: .constant(provider), store: store)
                    .padding(16)
                    .frame(width: 560, height: 400, alignment: .top)
                    .background(scheme == .dark ? Color.black : Color.white)
                    .environment(\.colorScheme, scheme))
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 560, height: 400),
                styleMask: [.borderless], backing: .buffered, defer: false)
            window.contentView = host
            host.layoutSubtreeIfNeeded()
            let image = try XCTUnwrap(host.bitmapImageRepForCachingDisplay(in: host.bounds))
            host.cacheDisplay(in: host.bounds, to: image)
            if let directory = ProcessInfo.processInfo.environment["SYMAIRA_FORM_CAPTURE_DIR"] {
                let png = try XCTUnwrap(image.representation(using: .png, properties: [:]))
                try png.write(to: URL(fileURLWithPath: directory).appendingPathComponent("provider-\(scheme).png"))
            }
        }
        XCTAssertEqual(store.deleteCount, 0)
    }

    func testRemovalAsksFirstAndCancelKeepsStoredKey() {
        let provider = "ollama"
        let store = InMemoryCredentialStore(provider: provider)
        var removal = ProviderKeyRemoval()

        removal.request()
        XCTAssertTrue(removal.isConfirming, "The first activation must only ask")
        XCTAssertEqual(store.deleteCount, 0)

        removal.cancel()
        XCTAssertFalse(removal.isConfirming)
        XCTAssertEqual(store.values[provider], "fixture-value")
        XCTAssertEqual(store.deleteCount, 0)

        removal.request()
        XCTAssertTrue(removal.confirm(providerID: provider, store: store))
        XCTAssertFalse(removal.isConfirming)
        XCTAssertNil(store.values[provider])
        XCTAssertEqual(store.deleteCount, 1)
    }
}

@MainActor
private final class InMemoryCredentialStore: ProviderSettingsCredentialStore {
    var values: [String: String]
    private(set) var deleteCount = 0

    init(provider: String) { values = [provider: "fixture-value"] }

    func credential(for providerID: String) throws -> String? { values[providerID] }

    func save(_ value: String, for providerID: String) throws -> Bool {
        values[providerID] = value
        return true
    }

    func delete(for providerID: String) -> Bool {
        deleteCount += 1
        return values.removeValue(forKey: providerID) != nil
    }

    func reference(for providerID: String) -> String { "env://TEST_PROVIDER_KEY" }
}
#endif
