# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.8.1] - 2026-08-06

### Added
- `MCPJSONSchemaProperty` now carries JSON Schema `minimum`/`maximum` numeric bounds, so consumers can advertise safe ranges (e.g. brightness 0.0–1.0, charge limit 50–100) in their `tools/list` schemas (consumer follow-up of #55).

## [0.8.0] - 2026-08-06

### Added
- `SymairaMCP` module: shared typed JSON-RPC/MCP stdio server
  (`MCPServer.withMethodHandler(_:)`, `MCPStdioTransport`, and the MCP wire
  types `MCPTool`, `MCPCallToolResult`, `MCPInitializeResult`, …), zero
  third-party dependencies — so client apps can stop hand-rolling their own
  MCP servers (follow-up of #55).

### Fixed
- `UpdateApplier`: cosign subprocess errors now bound stderr in the
  user-facing error message instead of dumping unbounded output.
- Restored the iOS platform declaration for package consumers.

### Changed
- `UpdateApplier` subprocess calls now run with explicit timeouts
  (loose-coupling rule).

## [0.7.0] - 2026-08-01

### Added
- `SymairaTypography`: canonical type scale (`display`, `title`, `heading`,
  `subheading`, `body`, `bodyEmphasized`, `bodyMedium`, `callout`, `caption`,
  `label`, `micro`, `mono`, `monoSmall`). Every entry is built from a Dynamic
  Type text style, so client text scales with the system setting.
- `SymairaTextRole` and `View.symairaText(_:respectsForeground:)`: apply font,
  tracking, and foreground colour together, so type and contrast cannot drift
  apart per app.
- `SymairaTextFieldStyle` plus `.symaira` / `.symaira(isFocused:)` shorthands —
  warm surface, glass border, gold focus ring, Increase Contrast aware.
- `SymairaFormSection`, `SymairaFormRow`, `SymairaFormDivider`: the settings and
  detail scaffold the client apps have been rebuilding individually.
- `SymairaStatusDot` and `SymairaStatusLabel`: tone-coloured status that always
  carries a text or accessibility label, never colour alone.
- `SymairaMetrics.emptyStateSymbolSize` token for the empty-state illustration.
- `SymairaOnboardingStep`, `SymairaOnboardingFlow`, and `SymairaOnboardingScaffold`:
  a product-independent multi-step onboarding scaffold. Step identity is
  protocol-based (`Hashable`/`Identifiable` plus an explicit `order`) so an
  enum, an `Int` index, or a bespoke struct can all conform; the flow is a
  pure, testable state machine (advance/retreat/skip/finish) and the SwiftUI
  scaffold owns chrome, keyboard navigation, and VoiceOver
  announcements/focus, leaving step content to the client.

### Changed
- Feedback and control components now draw their fonts from `SymairaTypography`
  instead of inline `Font` literals.
- `SymairaNotice` message and `SymairaLoadingState` text move from `.subheadline`
  to the scale's `callout` role — a small size increase, applied deliberately so
  secondary text is one size across the library.

## [0.6.1] - 2026-07-30

### Fixed
- iOS compatibility: guard macOS-only types with `#if os(macOS)` in `CLIRunner`,
  `UpdateApplier`, `CosignCLIVerifier`, `CosignConfig`, `SymingestReOCRClient`,
  `SymingestRulesClient` — enables iOS cross-compilation of the package
- `UpdateChecker`: use `cachesDirectory` on iOS for disk cache path
- `detectInstallMethod`: check original path patterns before symlink resolution
  to correctly classify `/usr/local/bin/` as direct download
- PEM redaction regex: use `\s` instead of `\\s` in character class for correct
  multi-line PEM block matching

### Changed
- Remove `.iOS(.v17)` from package platforms — repository uses macOS-only APIs
  in most targets
- Remove `ios-build` CI job (no longer applicable)
- Tag convention documented: no `v` prefix since 0.3.0. Earlier tags
  (`v0.1.0`–`v0.2.3`) use the `v` prefix and are retained for
  historical reference.

### Security
- Add `permissions: read-all` to CI workflow (least privilege)
- Enable private vulnerability reporting
- Configure CodeQL default setup (Swift analysis)

### Added
- `CONTRIBUTING.md` with PR/code guidelines and tag convention
- Issue templates: bug report, feature request, config.yml
- Pull request template with checklist
- `SECURITY.md` for supported versions and reporting policy
- `dependabot.yml` for GitHub Actions dependency updates
- `CHANGELOG.md`: Unreleased section documenting tag convention

## [0.6.0] - 2026-07-29

### Added

- `UpdateApplier`: download, SHA256-verify, and bundle-install pipeline (Swift port from `corekit/updateapply`)
- `AppUpdateStatus.installing` and `readyToRelaunch` states for GUI update flows
- Cosign keyless signature verification and Homebrew installation detection in `UpdateApplier`
- `AutoUpdatePreferenceStore` with `checkOnLaunchIfEnabled()` launch hook
- CI: iOS build job and Swift 6.2+ toolchain job
- `CHANGELOG.md` with entries for all published tags
- `CLIRunner.augmentedEnvironment(_:)` — shared PATH augmentation helper

### Changed

- CI now runs the XCTest suite on pull requests (was build-only)
- `SymairaDaemonKit` depends on `SymairaCLIRunner` for shared PATH logic
- Tool detection runs handshakes concurrently (bounded to 4) with per-binary caching

### Fixed

- DaemonSupervisor restart race: stale termination handlers no longer tear down new sessions
- Keychain items now use data-protection keychain and device-bound accessibility
- CLI binary provenance verified via code-signature check before execution
- Raw subprocess stderr no longer interpolated into user-facing error messages
- Subprocess output buffering capped at 16 MiB with truncation flag
- Duplicated Ingest contract decode paths consolidated; force-unwrap removed

### Security

- Reject binaries in non-root-owned or group/world-writable directories
- Secret shapes (PEM blocks, long tokens, key-prefixed values) redacted from error messages

### Breaking

- Keychain storage migrated to data-protection keychain — existing items are migrated on first access but consumers should verify access patterns after updating

## [0.2.3] - 2026-07-27

### Fixed

- Switch `DaemonSupervisor` lock to `NSRecursiveLock` to prevent deadlock in `start()`

## [0.2.2] - 2026-07-23

### Added

- `SymairaUpdateCheck`: GitHub latest-release checker with disk cache and stable-semver comparison, lifted from `symaira-desktop`

## [0.5.0] - 2026-07-21

### Added

- `SymairaTheme`: adaptive Apple UI foundation with Liquid Glass, materials, and accessibility fallbacks
- `symmeet` tool entry in `SymairaToolRegistry` with schema-1 handshake test

### Fixed

- Harden daemon and ingest contracts

## [0.4.0] - 2026-07-12

### Added

- ReOCR JSON contract client in `SymairaIngestContract`

## [0.3.0] - 2026-07-12

### Added

- `SymairaIngestContract` module: JSON contract clients for `symingest` rules and mail configuration

## [0.2.1] - 2026-07-10

### Fixed

- Reject bundle's own executable in `BinaryLocator` to prevent false-positive tool detection

## [0.2.0] - 2026-07-06

### Added

- `SymairaDaemonKit` module with `DaemonSupervisor` for launching and supervising long-running Symaira core daemon processes
- iOS platform support

### Breaking

- `SymairaDaemonKit` introduces new public API surface; downstream consumers must add the module to their target dependencies if they use daemon supervision

## [0.1.2] - 2026-07-06

### Added

- `symdesk` tool entry in `SymairaToolRegistry`

### Fixed

- `symingest` MCP server detection (exposes an MCP server since v0.6.0)

## [0.1.1] - 2026-07-06

### Added

- `CLIRunner` now accepts an `environment` parameter that is merged over the inherited environment

## [0.1.0] - 2026-07-03

### Added

- Initial release of SymairaAppKit — shared Swift foundations for Symaira macOS clients
- `SymairaTheme`: Cross-platform design foundation with adaptive Symaira tokens, Apple materials and Liquid Glass, backgrounds, surfaces, controls, feedback states, and accessibility-aware fallbacks
- `SymairaCLIRunner`: Subprocess execution for Symaira CLIs with mandatory timeout, stderr capture, snake_case JSON decoding, and unified `CLIRunnerError`
- `SymairaToolKit`: `SymairaToolRegistry` (single source of truth for all tools), `BinaryLocator`, `ToolDetector` with `version --json` schema handshake
- `SymairaKeychain`: Keychain wrapper, service-namespaced `dev.symaira.<app>`

[0.7.0]: https://github.com/danieljustus/symaira-appkit/compare/0.6.1...0.7.0
[0.6.1]: https://github.com/danieljustus/symaira-appkit/compare/0.6.0...0.6.1
[0.6.0]: https://github.com/danieljustus/symaira-appkit/compare/0.5.0...0.6.0
[0.2.3]: https://github.com/danieljustus/symaira-appkit/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/danieljustus/symaira-appkit/compare/v0.2.1...v0.2.2
[0.5.0]: https://github.com/danieljustus/symaira-appkit/compare/0.4.0...0.5.0
[0.4.0]: https://github.com/danieljustus/symaira-appkit/compare/0.3.0...0.4.0
[0.3.0]: https://github.com/danieljustus/symaira-appkit/compare/v0.2.1...0.3.0
[0.2.1]: https://github.com/danieljustus/symaira-appkit/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/danieljustus/symaira-appkit/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/danieljustus/symaira-appkit/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/danieljustus/symaira-appkit/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/danieljustus/symaira-appkit/releases/tag/v0.1.0
