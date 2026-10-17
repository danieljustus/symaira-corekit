import SwiftUI
import XCTest

@testable import SymairaTheme

#if os(macOS)
import AppKit

@MainActor
final class SharedUIAdoptionTests: XCTestCase {
    func testFormAndNoticeSurfacesAreOpaqueInBothAppearances() throws {
        for scheme in [ColorScheme.light, .dark] {
            let section = SymairaFormSection {
                Color.clear.frame(height: 80)
            }.frame(width: 320)
            let notice = SymairaNotice(message: "Example status", tone: .critical)
                .frame(width: 320)
            for view in [AnyView(section), AnyView(notice)] {
                var pixels: [[UInt8]] = []
                for background in [Color(nsColor: .magenta), .cyan] {
                    let renderer = ImageRenderer(
                        content: view.background(background).environment(\.colorScheme, scheme))
                    renderer.scale = 1
                    let image = try XCTUnwrap(renderer.cgImage)
                    pixels.append(try pixel(image, x: 30, y: image.height - 10))
                }
                XCTAssertEqual(pixels[0], pixels[1], "Text surfaces must not reveal the backing: \(scheme)")
                XCTAssertEqual(pixels[0][3], 255)
            }
        }
    }

    func testNavigationGeometryInExpandedAndIconRailModes() throws {
        for showsLabel in [true, false] {
            for selected in [true, false] {
                let width = showsLabel ? SymairaSidebarState.minimumWidth : SymairaSidebarState.compactWidth
                let renderer = ImageRenderer(
                    content:
                        SymairaNavigationButton(
                            "Manual Tasks", systemImage: "checklist", isSelected: selected,
                            showsLabel: showsLabel, action: {}
                        )
                        .frame(width: width))
                renderer.scale = 1
                let image = try XCTUnwrap(renderer.cgImage)
                XCTAssertEqual(image.width, Int(width))
                XCTAssertEqual(image.height, 44)
            }
        }
    }

    func testFeedbackProtectionDoesNotCoverExpandedWhitespace() async throws {
        _ = NSApplication.shared
        let model = SymairaTopoModel()
        let view = SymairaEmptyState(systemImage: "tray", title: "Empty", message: "No entries") {
            Button("Retry") {}.symairaButtonStyle(.secondary)
        }
        .environment(\.symairaTopography, model)
        .coordinateSpace(name: SymairaTopo.space)
        let window = NSWindow(contentViewController: NSHostingController(rootView: view))
        window.isReleasedWhenClosed = false
        window.setContentSize(NSSize(width: 800, height: 600))
        defer { window.close() }
        window.contentView?.layoutSubtreeIfNeeded()
        try await Task.sleep(for: .milliseconds(150))
        XCTAssertEqual(model.rects.count, 4, "Icon, title, message and action each own a protection region")
        for (rect, _) in model.rects.values {
            XCTAssertLessThan(rect.width, 440, "Do not protect the whole stretched placeholder")
            XCTAssertLessThan(rect.height, 100)
        }
    }

    private func pixel(_ image: CGImage, x: Int, y: Int) throws -> [UInt8] {
        var bytes = [UInt8](repeating: 0, count: image.width * image.height * 4)
        let context = try XCTUnwrap(
            CGContext(
                data: &bytes, width: image.width, height: image.height, bitsPerComponent: 8,
                bytesPerRow: image.width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        let offset = (y * image.width + x) * 4
        return Array(bytes[offset..<(offset + 4)])
    }
}
#endif
