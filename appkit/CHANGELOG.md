# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
