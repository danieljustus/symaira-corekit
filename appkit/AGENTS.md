# Agent Instructions — symaira-appkit

Shared public Swift library (Apache-2.0) for Symaira macOS clients. GUI counterpart to `symaira-corekit`. Consumed by the per-tool client apps as a pinned SPM dependency.

## Build & Test

```bash
make build
make test
make toolchain          # show which Swift toolchain will be used
```

- macOS 14+, Swift 6 (strict concurrency). No Xcode project — pure SPM.
- **Use the Makefile, not bare `swift build`/`swift test`.** Command Line Tools ship
  no XCTest and no SwiftUI macro plugins, so a bare `swift build` fails outright
  whenever `xcode-select -p` points at `/Library/Developer/CommandLineTools`. The
  Makefile resolves a full Xcode itself and exports `DEVELOPER_DIR` for the child
  process only — no machine-wide `sudo xcode-select -s` needed. Precedence: an
  explicit `DEVELOPER_DIR`, then the active `xcode-select` path if it is a real
  Xcode, then `Xcode.app`, then `Xcode-beta.app`. `make toolchain` prints the
  result and fails with a clear message when no Xcode is installed.
- `SymairaKeychainTests` exercises the data-protection keychain paths, but skips (via `XCTSkip`) on `errSecMissingEntitlement` — an unsigned `swift test` binary has no `keychain-access-groups` entitlement, so CI runs them as skips, not passes. Only a signed app/test target (a real Symaira client) exercises them for real.
- **Cross-language contract fixtures:** `contracts/*.json` are vendored copies of `symaira-corekit`'s `contracts/*.json` (see `contracts/README.md` for provenance and the update procedure). `Tests/SymairaUpdateCheckTests/ContractFixtureTests.swift` and `Tests/SymairaMCPTests/ContractFixtureTests.swift` assert this repo's Swift code against them as part of the normal `swift test` run — no separate CI job.

## Architecture & Boundaries

- **No tool-specific code.** A module belongs here only if ≥2 apps need it. App-specific views, models, and IPC stay in the app's repo. Record each "should this move here?" assessment — including the ones answered "no" — in the project's internal architecture notes, so the question is not re-litigated from scratch.
- **No Cloud/SaaS code** (no Stripe, Firebase, Pro concepts) — same boundary as corekit.
- **No third-party dependencies.** Foundation, SwiftUI, Security only.
- Consumers pin exact versions (`.package(url:…, exact: "x.y.z")`). Local development may use `path:` dependencies, but merged app code must reference a tag.
- `SymairaToolRegistry` is the single source of truth for tool metadata (binary names, Homebrew formulae, MCP args). Update it here, never fork it into an app.
- The version handshake expects cores to answer `version --json` with `{"version": "...", "schema_version": N}`. Cores without it are detected with `schemaVersion == 0` (usable, no contract guarantees).
- Subprocess execution must always have a timeout (loose-coupling rule: runtime detection with timeout and graceful fallback).

## Release

1. Update `CHANGELOG.md` with the new version entry following Keep-a-Changelog format. Gather changes from `git log` since the last tag and categorize them as Added, Changed, Deprecated, Removed, Fixed, Security, or Breaking.
2. Tag `X.Y.Z` on main (unprefixed). Strict SemVer — breaking API changes bump the minor pre-1.0, per-app migration is explicit (each app updates its pin deliberately).
