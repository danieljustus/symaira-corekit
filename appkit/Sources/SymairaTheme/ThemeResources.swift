import Foundation

/// Native SwiftPM's generated accessor searches beside the executable or in its
/// build tree. Packaged macOS apps keep resources in Contents/Resources instead.
/// Font and shader lookup must select the same shipped bundle before that fallback.
enum SymairaThemeResources {
    static let bundle = packagedBundle(in: Bundle.main.resourceURL) ?? Bundle.module

    static func packagedBundle(in directory: URL?) -> Bundle? {
        directory.flatMap { Bundle(url: $0.appendingPathComponent("symaira-appkit_SymairaTheme.bundle")) }
    }
}
