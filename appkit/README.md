# symaira-appkit

Shared Swift foundations for the macOS clients of the [Symaira](https://symaira.com) ecosystem — the GUI counterpart to [`symaira-corekit`](https://github.com/danieljustus/symaira-corekit).

Every Symaira app stays fully standalone: this package is consumed as a **pinned SPM dependency** (exact version), never as a required runtime service.

## Modules

| Product | Purpose |
| :--- | :--- |
| `SymairaTheme` | Design tokens (gold/glassmorphism brand), `Color(hex:)`, glass panel/card modifiers, button styles. Includes the legacy `Color.symaira*` aliases for painless migration. |
| `SymairaCLIRunner` | Subprocess execution for Symaira CLIs: mandatory timeout, stderr capture, snake_case JSON decoding, unified `CLIRunnerError`. |
| `SymairaToolKit` | `SymairaToolRegistry` (single source of truth for all tools), `BinaryLocator` (bundle → exe dir → PATH → Homebrew prefixes → user override), `ToolDetector` with the `version --json` schema handshake. |
| `SymairaKeychain` | Keychain wrapper, service-namespaced `dev.symaira.<app>`. |
| `SymairaUpdateCheck` | GitHub latest-release checker with disk cache and stable-semver comparison (port of `corekit/updatecheck`). |

## Usage

```swift
// Package.swift of a client app — always pin exactly:
.package(url: "https://github.com/danieljustus/symaira-appkit.git", exact: "0.1.0")
```

```swift
import SymairaToolKit

let detector = ToolDetector()
if let seek = await detector.detect(SymairaToolRegistry.tool(id: "symseek")!) {
    try detector.requireSchemaVersion(1, of: seek)
    let results = try await CLIRunner().runDecoding(
        SearchResults.self,
        executable: seek.location.url,
        arguments: ["search", "query", "--json"]
    )
}
```

## Build & Test

```bash
swift build
swift test
```

Requires macOS 14+, Swift 6.

## License

Apache-2.0
