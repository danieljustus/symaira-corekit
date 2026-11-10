// swift-tools-version: 6.0
import PackageDescription

// Swift package of Symaira CoreKit (formerly the separate symaira-appkit
// repository, ADR 0006). Sources live under swift/; the manifest sits at the
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
        .target(name: "SymairaTheme", path: "swift/Sources/SymairaTheme", resources: [.process("Resources")]),
        .target(name: "SymairaCLIRunner", path: "swift/Sources/SymairaCLIRunner"),
        .target(name: "SymairaToolKit", dependencies: ["SymairaCLIRunner"], path: "swift/Sources/SymairaToolKit"),
        .target(name: "SymairaKeychain", path: "swift/Sources/SymairaKeychain"),
        .target(name: "SymairaUpdateCheck", path: "swift/Sources/SymairaUpdateCheck"),
        .target(name: "SymairaDaemonKit", dependencies: ["SymairaCLIRunner"], path: "swift/Sources/SymairaDaemonKit"),
        .target(
            name: "SymairaIngestContract",
            dependencies: ["SymairaToolKit", "SymairaCLIRunner"],
            path: "swift/Sources/SymairaIngestContract"
        ),
        .target(name: "SymairaMCP", path: "swift/Sources/SymairaMCP"),
        .target(
            name: "SymairaProviderKit",
            dependencies: ["SymairaKeychain", "SymairaTheme", "SymairaCLIRunner"],
            path: "swift/Sources/SymairaProviderKit",
            resources: [.process("Resources")]
        ),
        .testTarget(name: "SymairaThemeTests", dependencies: ["SymairaTheme"], path: "swift/Tests/SymairaThemeTests"),
        .testTarget(
            name: "SymairaKeychainTests", dependencies: ["SymairaKeychain"], path: "swift/Tests/SymairaKeychainTests"),
        .testTarget(
            name: "SymairaCLIRunnerTests", dependencies: ["SymairaCLIRunner"], path: "swift/Tests/SymairaCLIRunnerTests"),
        .testTarget(
            name: "SymairaToolKitTests", dependencies: ["SymairaToolKit"], path: "swift/Tests/SymairaToolKitTests"),
        .testTarget(
            name: "SymairaUpdateCheckTests", dependencies: ["SymairaUpdateCheck"],
            path: "swift/Tests/SymairaUpdateCheckTests"),
        .testTarget(
            name: "SymairaDaemonKitTests", dependencies: ["SymairaDaemonKit"], path: "swift/Tests/SymairaDaemonKitTests"),
        .testTarget(
            name: "SymairaIngestContractTests", dependencies: ["SymairaIngestContract"],
            path: "swift/Tests/SymairaIngestContractTests"),
        .testTarget(name: "SymairaMCPTests", dependencies: ["SymairaMCP"], path: "swift/Tests/SymairaMCPTests"),
        .testTarget(
            name: "SymairaProviderKitTests", dependencies: ["SymairaProviderKit"],
            path: "swift/Tests/SymairaProviderKitTests"),
    ]
)
