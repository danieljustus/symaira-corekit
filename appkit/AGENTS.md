# Agent Instructions — symaira-appkit

## Current product contract

Read [PB-2026-09-09](docs/product-boundaries.md). AppKit remains a separate shared Swift foundation, not a new application or a home for credential-management views. Brain owns the future credential management UI; the separate credential service owns authorization and keys. Reuse only modules with two genuine consumers. Keep immutable pins and cross-language fixture checks. The UI transfer and removal of the old management app remain gated implementation work.

Shared public Swift library (Apache-2.0) for Symaira macOS clients. GUI counterpart to `symaira-corekit`. Consumed by the per-tool client apps as a pinned SPM dependency.

## GUI work

Before building, changing or reviewing any SwiftUI surface (here or in a consumer), read in this order: [`GUIDELINES.md`](GUIDELINES.md) (structure, states, actions, copy, keyboard, accessibility, review contract), [`DESIGN.md`](DESIGN.md) (material hierarchy, platform behavior) and [`docs/workspace-foundation.md`](docs/workspace-foundation.md) (shell API, approved rule inventory). Tokens come from [`design/liquid-topography/DESIGN.md`](design/liquid-topography/DESIGN.md). Write the six-line screen card from GUIDELINES.md section 2 before writing code. Review product sources with `python3 scripts/gui-review.py <swift-source-root>` plus the manual checklist in section 13; `python3 scripts/gui-review.py --self-test` runs in CI. A reusable rule accepted in a product pilot lands here first, with implementation and regression check, then consumers adopt it through their exact pin.

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
