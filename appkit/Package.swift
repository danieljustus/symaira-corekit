// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "symaira-appkit",
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
        .target(name: "SymairaTheme"),
        .target(name: "SymairaCLIRunner"),
        .target(name: "SymairaToolKit", dependencies: ["SymairaCLIRunner"]),
        .target(name: "SymairaKeychain"),
        .target(name: "SymairaUpdateCheck"),
        .target(name: "SymairaDaemonKit", dependencies: ["SymairaCLIRunner"]),
        .target(name: "SymairaIngestContract", dependencies: ["SymairaToolKit", "SymairaCLIRunner"]),
        .target(name: "SymairaMCP"),
        .target(
            name: "SymairaProviderKit",
            dependencies: ["SymairaKeychain", "SymairaTheme", "SymairaCLIRunner"],
            resources: [.process("Resources")]
        ),
        .testTarget(name: "SymairaThemeTests", dependencies: ["SymairaTheme"]),
        .testTarget(name: "SymairaKeychainTests", dependencies: ["SymairaKeychain"]),
        .testTarget(name: "SymairaCLIRunnerTests", dependencies: ["SymairaCLIRunner"]),
        .testTarget(name: "SymairaToolKitTests", dependencies: ["SymairaToolKit"]),
        .testTarget(name: "SymairaUpdateCheckTests", dependencies: ["SymairaUpdateCheck"]),
        .testTarget(name: "SymairaDaemonKitTests", dependencies: ["SymairaDaemonKit"]),
        .testTarget(name: "SymairaIngestContractTests", dependencies: ["SymairaIngestContract"]),
        .testTarget(name: "SymairaMCPTests", dependencies: ["SymairaMCP"]),
        .testTarget(name: "SymairaProviderKitTests", dependencies: ["SymairaProviderKit"]),
    ]
)
