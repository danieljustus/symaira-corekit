# Symaira AppKit

> **Accepted product direction — implementation pending:** AppKit remains a separate shared Swift foundation. Brain owns the future credential-management UI; domain-specific views stay product-owned, not in AppKit. The optional Browse/Operate and credential UI transfers do not eliminate shared native foundations or change existing dependency pins. See [PB-2026-09-09](docs/product-boundaries.md).

[![CI](https://github.com/danieljustus/symaira-appkit/actions/workflows/ci.yml/badge.svg)](https://github.com/danieljustus/symaira-appkit/actions/workflows/ci.yml) [![Release](https://img.shields.io/github/v/release/danieljustus/symaira-appkit?label=Release)](https://github.com/danieljustus/symaira-appkit/releases/latest) [![Coverage](https://img.shields.io/badge/coverage-not%20published-lightgrey)](https://github.com/danieljustus/symaira-appkit/actions/workflows/ci.yml) [![License](https://img.shields.io/github/license/danieljustus/symaira-appkit)](LICENSE) [![Swift 6](https://img.shields.io/badge/swift-6.0-orange)](https://swift.org)

![Symaira AppKit social preview](docs/assets/social-preview.png)

Shared Swift foundations for the macOS clients of the [Symaira](https://symaira.com) ecosystem — the GUI counterpart to [`symaira-corekit`](https://github.com/danieljustus/symaira-corekit).

Every Symaira app stays fully standalone: this package is consumed as a **pinned SPM dependency** (exact version), never as a required runtime service.

## Why symaira-appkit

- **Zero third-party dependencies** — Foundation, SwiftUI and Security only; nothing extra to audit per app.
- **One pinned dependency per app** — every client builds against the exact version it was released with; breaking changes are explicit, not accidental.
- **Shared foundation, standalone apps** — theme, CLI runner, tool detection, keychain, update check, daemon supervision and ingest contracts in one place, with a version handshake so apps and cores never silently disagree.

> **Status:** pre-1.0. Breaking API changes bump the minor version — review the [CHANGELOG](CHANGELOG.md) before bumping your pin.

## Install

Add the package as an exact-pinned dependency in the client app's `Package.swift`:

```swift
.package(url: "https://github.com/danieljustus/symaira-appkit.git", exact: "0.18.1")
```

## Modules

| Product | Purpose |
| :--- | :--- |
| `SymairaTheme` | Cross-platform design foundation: adaptive Symaira tokens, a Dynamic-Type-backed type scale (`SymairaTypography`, `.symairaText(_:)`), Apple materials and Liquid Glass, backgrounds, surfaces, controls, form scaffolding (`SymairaFormSection`, `SymairaFormRow`, `.symaira` text fields), feedback and status states, and accessibility-aware fallbacks. Includes legacy `Color.symaira*` aliases. |
| `SymairaCLIRunner` | Subprocess execution for Symaira CLIs: mandatory timeout, stderr capture, snake_case JSON decoding, unified `CLIRunnerError`. |
| `SymairaToolKit` | `SymairaToolRegistry` (single source of truth for all tools), `BinaryLocator` (bundle → exe dir → PATH → Homebrew prefixes → user override), `ToolDetector` with the `version --json` schema handshake. |
| `SymairaKeychain` | Keychain wrapper with data-protection storage (`kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`), iCloud-sync disabled, service-namespaced `dev.symaira.<app>`, and automatic legacy-item migration. The data-protection keychain needs the `keychain-access-groups` entitlement; unentitled macOS apps pass `storage: .loginKeychain`. |
| `SymairaUpdateCheck` | GitHub latest-release checker with disk cache, stable-semver comparison, cosign keyless signature verification, install-method detection (rejects Homebrew-managed binaries), and streaming asset downloads with progress callbacks. |
| `SymairaDaemonKit` | `DaemonSupervisor` for launching and supervising long-running Symaira core daemon processes. |
| `SymairaIngestContract` | JSON contract clients for the ingest rules/mail config and ReOCR requests (the engine ships inside `symdesk`). |
| `SymairaMCP` | Shared MCP server plumbing: `MCPServer`, stdio `MCPTransport` with message-size guard, and JSON-RPC `MCPTypes` with machine-readable `MCPError` payloads. |
| `SymairaProviderKit` | Shared LLM provider catalog, typed credential references, Keychain-backed credentials, redacted error taxonomy, model discovery, non-billable connection checks, PKCE OAuth/token storage, and reusable SwiftUI provider settings. |

### Platform availability

The package declares `.iOS(.v17)` alongside `.macOS(.v14)`, but availability is
uneven per product. Where a product is **mixed**, the macOS-only pieces are
wrapped in `#if os(macOS)`, so referencing them from an iOS target is a
compile error, not a silently empty API.

| Product | iOS | Notes |
| :--- | :--- | :--- |
| `SymairaTheme` | Mixed | Tokens, typography, controls, meters and topography support iOS; the resizable desktop workspace and native NSAppearance application API are macOS-only. |
| `SymairaKeychain` | Full | Security framework APIs behave the same on both platforms. |
| `SymairaMCP` | Full | No macOS-specific APIs; stdio transport works but is unusual for an iOS app to use. |
| `SymairaProviderKit` | Full | Provider HTTP and SwiftUI surfaces use Foundation/SwiftUI; credentials use the cross-platform Security keychain. |
| `SymairaCLIRunner` | **Unavailable** | Entire module is `#if os(macOS)` (subprocess execution does not exist on iOS). Importing it still succeeds; using any symbol from it fails to build. |
| `SymairaDaemonKit` | **Unavailable** | `DaemonSupervisor` is `#if os(macOS)` for the same reason (wraps `SymairaCLIRunner`). |
| `SymairaToolKit` | Mixed | `SymairaTool` / `SymairaToolRegistry` (plain data) build on iOS. `BinaryLocator` and `ToolDetector` are `#if os(macOS)` — using them from an iOS target fails to build. |
| `SymairaIngestContract` | Mixed | The `ReOCRClient` protocol and all contract/DTO types build on iOS. The concrete `SymingestReOCRClient` (which shells out via `SymairaToolKit`) is `#if os(macOS)`. |
| `SymairaUpdateCheck` | Mixed | Release-check, semver, and asset-verification logic build on iOS; the pieces that shell out to install/replace the running binary (`SubprocessRunner` and the install/apply paths that use it) are `#if os(macOS)`. |

A macOS-only product still **links** cleanly into an iOS target — SwiftPM does
not fail the dependency graph over this — only *using* one of its symbols
fails to build. `SymairaTheme`, `SymairaKeychain`, and `SymairaMCP` are safe to
adopt in an iOS client today.

## Usage

Review the [CHANGELOG](CHANGELOG.md) before bumping your pin — every release documents its additions, fixes, and breaking changes.

```swift
import SymairaCLIRunner
import SymairaToolKit

let detector = ToolDetector()
if let desk = await detector.detect(SymairaToolRegistry.tool(id: "symdesk")!) {
    try detector.requireSchemaVersion(1, of: desk)
    let results = try await CLIRunner().runDecoding(
        SearchResults.self,
        executable: desk.location.url,
        arguments: ["search", "query", "--json"]
    )
    print(results)
}
```

### Update flow

```swift
import SymairaUpdateCheck

let release = ReleaseInfo(
    tagName: "0.18.0",
    htmlURL: "https://github.com/danieljustus/symaira-appkit/releases/tag/0.18.0"
)
let installURL = "/Applications/Symaira.app"
let applier = UpdateApplier(
    checkInstallMethod: true,
    cosignConfig: CosignConfig(
        repo: "danieljustus/symaira-appkit",
        binaryName: "symaira-appkit",
        identityRegexp: "https://github.com/danieljustus/"
    )
)
let result = try await applier.applyBundle(release: release, targetPath: installURL)
```

### Shared UI foundation

```swift
import SwiftUI
import SymairaTheme

struct Dashboard: View {
    var body: some View {
        ZStack {
            SymairaTokens.canvas

            VStack(spacing: SymairaSpacing.xLarge) {
                SymairaNotice(
                    title: "Core connected",
                    message: "Local features are ready.",
                    tone: .positive
                )

                Text("Reading surfaces remain opaque.")
                    .padding(SymairaSpacing.xLarge)
                    .symairaCard()

                SymairaGlassEffectContainer {
                    HStack {
                        Button("Cancel") {}
                            .symairaButtonStyle(.secondary)
                        Button("Continue") {}
                            .symairaButtonStyle(.primary)
                    }
                }
            }
            .padding()
        }
    }
}
```

Use Liquid Glass for navigation chrome and toolbar controls, not behind reading
surfaces. Content buttons stay opaque and share stable primary/secondary geometry.
`symairaGlassChrome` and `SymairaGlassEffectContainer` use native macOS/iOS 26
effects with material or opaque accessibility fallbacks on earlier systems. See
[`GUIDELINES.md`](GUIDELINES.md) for the interface rules every Symaira screen
follows (structure, states, actions, copy, review contract) and
[`DESIGN.md`](DESIGN.md) for the design rules and migration guidance.
`python3 scripts/gui-review.py <swift-source-root>` checks product sources
against the mechanical part of those rules.

The approved desktop shell is `SymairaWorkspace` with `SymairaSidebarState`:
rounded inset content, continuous chrome, drag resizing and a collapsible icon
rail. `SymairaWorkspaceToolbar` opens settings directly through its shared gear
button, without an intermediate menu. Place `SymairaAppearancePicker` inside the
settings window alongside other preferences. `SymairaSidebarToggle`,
`SymairaNavigationButton` and `SymairaProgressStyle` keep interaction rules in the library. See
[workspace usage and the shared rule inventory](docs/workspace-foundation.md).
Product-specific screens and settings keys remain product-owned; release pins
must be upgraded explicitly before other installed apps acquire these changes.

Packaged apps must embed `symaira-appkit_SymairaTheme.bundle` in their Resources
directory. The shared font/shader resolver prefers that shipped bundle before
SwiftPM's development fallback. Validate the actual app without the build-cache
resource bundle; a file-presence check alone does not prove self-contained loading.

Typography uses view-resolved roles so existing mounted views respond to iOS
Dynamic Type changes while keeping each bundled font's fixed optical size
(Google Sans Flex for headings, Inter for running text).
See [typography API migration and native regression](docs/typography.md) for
the `Font`/`Text` source changes and the separate simulator check.

## Build & Test

```bash
make build
make test
make lint
```

The Makefile resolves a full Xcode toolchain and exports `DEVELOPER_DIR` for
the build itself, so these work regardless of what `xcode-select` points at.
A bare `swift build` fails when Command Line Tools are the active developer
directory, since they ship no XCTest and no SwiftUI macro plugins.
`make toolchain` shows which toolchain will be used.

`make lint` uses `swift-format` from the selected Xcode, falling back to PATH.
It fails when the formatter is missing or reports any finding. Set
`SWIFT_FORMAT=/path/to/swift-format` to use a specific executable.
`make format` applies the same `.swift-format` rules: four-space indentation,
120-column wrapping, and the formatter's default lint rules. CI runs the same
strict gate. `make test-make` checks tool discovery and error propagation in
isolation; it also runs as part of `make test`.

Requires macOS 14+ or iOS 17+, Swift 6, and a full Xcode installation. Native Liquid Glass is enabled on
macOS/iOS 26+ when built with a compatible SDK.

## License

Apache-2.0
