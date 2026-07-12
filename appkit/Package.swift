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
    ],
    targets: [
        .target(name: "SymairaTheme"),
        .target(name: "SymairaCLIRunner"),
        .target(name: "SymairaToolKit", dependencies: ["SymairaCLIRunner"]),
        .target(name: "SymairaKeychain"),
        .target(name: "SymairaUpdateCheck"),
        .target(name: "SymairaDaemonKit"),
        .target(name: "SymairaIngestContract", dependencies: ["SymairaToolKit", "SymairaCLIRunner"]),
        .testTarget(name: "SymairaThemeTests", dependencies: ["SymairaTheme"]),
        .testTarget(name: "SymairaCLIRunnerTests", dependencies: ["SymairaCLIRunner"]),
        .testTarget(name: "SymairaToolKitTests", dependencies: ["SymairaToolKit"]),
        .testTarget(name: "SymairaUpdateCheckTests", dependencies: ["SymairaUpdateCheck"]),
        .testTarget(name: "SymairaDaemonKitTests", dependencies: ["SymairaDaemonKit"]),
        .testTarget(name: "SymairaIngestContractTests", dependencies: ["SymairaIngestContract"]),
    ]
)
