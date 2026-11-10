// swift-tools-version: 6.0
import PackageDescription

// Swift package of Symaira CoreKit (formerly the separate symaira-appkit
// repository, ADR 0006). Sources live under appkit/; the manifest sits at the
// repository root because SwiftPM resolves remote packages only from the root.

let package = Package(
    name: "symaira-corekit",
    defaultLocalization: "en",
    platforms: [
        .macOS(.v14),
        .iOS(.v17)
    ],
    products: [
        .library(name: "SymairaTheme", targets: ["SymairaTheme"]),
        .library(name: "SymairaCLIRunner", targets: ["SymairaCLIRunner"]),
        .library(name: "SymairaToolKit", targets: ["SymairaToolKit"]),
        .library(name: "SymairaKeychain", targets: ["SymairaKeychain"]),
        .library(name: "SymairaUpdateCheck", targets: ["SymairaUpdateCheck"]),
        .library(name: "SymairaDaemonKit", targets: ["SymairaDaemonKit"]),
        .library(name: "SymairaIngestContract", targets: ["SymairaIngestContract"]),
        .library(name: "SymairaMCP", targets: ["SymairaMCP"]),
        .library(name: "SymairaProviderKit", targets: ["SymairaProviderKit"]),
    ],
    targets: [
        .target(name: "SymairaTheme", path: "appkit/Sources/SymairaTheme", resources: [.process("Resources")]),
        .target(name: "SymairaCLIRunner", path: "appkit/Sources/SymairaCLIRunner"),
        .target(name: "SymairaToolKit", dependencies: ["SymairaCLIRunner"], path: "appkit/Sources/SymairaToolKit"),
        .target(name: "SymairaKeychain", path: "appkit/Sources/SymairaKeychain"),
        .target(name: "SymairaUpdateCheck", path: "appkit/Sources/SymairaUpdateCheck"),
        .target(name: "SymairaDaemonKit", dependencies: ["SymairaCLIRunner"], path: "appkit/Sources/SymairaDaemonKit"),
        .target(
            name: "SymairaIngestContract",
            dependencies: ["SymairaToolKit", "SymairaCLIRunner"],
            path: "appkit/Sources/SymairaIngestContract"
        ),
        .target(name: "SymairaMCP", path: "appkit/Sources/SymairaMCP"),
        .target(
            name: "SymairaProviderKit",
            dependencies: ["SymairaKeychain", "SymairaTheme", "SymairaCLIRunner"],
            path: "appkit/Sources/SymairaProviderKit",
            resources: [.process("Resources")]
        ),
        .testTarget(name: "SymairaThemeTests", dependencies: ["SymairaTheme"], path: "appkit/Tests/SymairaThemeTests"),
        .testTarget(
            name: "SymairaKeychainTests", dependencies: ["SymairaKeychain"], path: "appkit/Tests/SymairaKeychainTests"),
        .testTarget(
            name: "SymairaCLIRunnerTests", dependencies: ["SymairaCLIRunner"], path: "appkit/Tests/SymairaCLIRunnerTests"),
        .testTarget(
            name: "SymairaToolKitTests", dependencies: ["SymairaToolKit"], path: "appkit/Tests/SymairaToolKitTests"),
        .testTarget(
            name: "SymairaUpdateCheckTests", dependencies: ["SymairaUpdateCheck"],
            path: "appkit/Tests/SymairaUpdateCheckTests"),
        .testTarget(
            name: "SymairaDaemonKitTests", dependencies: ["SymairaDaemonKit"], path: "appkit/Tests/SymairaDaemonKitTests"),
        .testTarget(
            name: "SymairaIngestContractTests", dependencies: ["SymairaIngestContract"],
            path: "appkit/Tests/SymairaIngestContractTests"),
        .testTarget(name: "SymairaMCPTests", dependencies: ["SymairaMCP"], path: "appkit/Tests/SymairaMCPTests"),
        .testTarget(
            name: "SymairaProviderKitTests", dependencies: ["SymairaProviderKit"],
            path: "appkit/Tests/SymairaProviderKitTests"),
    ]
)
