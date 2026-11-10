# Agent Instructions — CoreKit Swift package (AppKit)

## Current product contract

Read [PB-2026-09-09](../docs/product-boundaries.md) and [ADR 0006](../docs/adr/0006-appkit-merged-into-corekit.md). AppKit is the shared Swift foundation inside `symaira-corekit` (formerly the separate `symaira-appkit` repository), not a new application or a home for credential-management views. Brain owns the future credential management UI; the separate credential service owns authorization and keys. Reuse only modules with two genuine consumers. Keep immutable pins and cross-language fixture checks. The UI transfer and removal of the old management app remain gated implementation work.

Shared public Swift library (Apache-2.0) for Symaira macOS and iOS clients, maintained in the CoreKit repository next to the Rust crates. Sources, tests, scripts and GUI rules live in this `appkit/` directory; `Package.swift` sits at the repository root because SwiftPM resolves remote packages only from there. Consumed by the client apps as an exact-pinned SPM dependency on `symaira-corekit`.

## GUI work

Before building, changing or reviewing any SwiftUI surface (here or in a consumer), read in this order: [`GUIDELINES.md`](GUIDELINES.md) (structure, states, actions, copy, keyboard, accessibility, review contract), [`DESIGN.md`](DESIGN.md) (material hierarchy, platform behavior) and [`docs/workspace-foundation.md`](docs/workspace-foundation.md) (shell API, approved rule inventory). Tokens come from [`design/liquid-topography/DESIGN.md`](design/liquid-topography/DESIGN.md). Write the six-line screen card from GUIDELINES.md section 2 before writing code. Review product sources with `python3 scripts/gui-review.py <swift-source-root>` plus the manual checklist in section 13; `python3 scripts/gui-review.py --self-test` runs in CI. A reusable rule accepted in a product pilot lands here first, with implementation and regression check, then consumers adopt it through their exact pin.

## Build & Test

```bash
make build              # run inside appkit/; from the repository root: make swift-build
make test               # root: make swift-test
make lint               # root: make swift-lint
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
- **Cross-language contract fixtures:** the Swift contract tests (`Tests/*/ContractFixtureTests.swift`) read the authoritative repository-root `contracts/*.json` directly; there are no vendored copies any more. A contract change and both language implementations land in one commit. `SymairaProviderKit` keeps a bundled `llm_providers.json` resource; its test asserts equality with the canonical fixture.

## Architecture & Boundaries

- **No tool-specific code.** A module belongs here only if ≥2 apps need it. App-specific views, models, and IPC stay in the app's repo. Record each "should this move here?" assessment — including the ones answered "no" — in the project's internal architecture notes, so the question is not re-litigated from scratch.
- **No Cloud/SaaS code** (no Stripe, Firebase, Pro concepts) — same boundary as corekit.
- **No third-party dependencies.** Foundation, SwiftUI, Security only.
- Consumers pin exact versions (`.package(url: "https://github.com/danieljustus/symaira-corekit.git", exact: "x.y.z")`, products from `package: "symaira-corekit"`). Local development may use `path:` dependencies to the CoreKit checkout root, but merged app code must reference a tag.
- `SymairaToolRegistry` is the single source of truth for tool metadata (binary names, Homebrew formulae, MCP args). Update it here, never fork it into an app.
- The version handshake expects cores to answer `version --json` with `{"version": "...", "schema_version": N}`. Cores without it are detected with `schemaVersion == 0` (usable, no contract guarantees).
- Subprocess execution must always have a timeout (loose-coupling rule: runtime detection with timeout and graceful fallback).

## Release

The Swift package ships with the CoreKit release process (one tag series, `vX.Y.Z`; SwiftPM accepts the `v` prefix).

1. Add Swift changes to `appkit/CHANGELOG.md` (Keep-a-Changelog) under the CoreKit version being released, and to the root `CHANGELOG.md` / `docs/migrations.md` entry for that version. Keep the single exact pin in `appkit/README.md` equal to the newest `appkit/CHANGELOG.md` release (`scripts/check-readme.py` enforces it).
2. Tag `vX.Y.Z` on CoreKit `main` per the root release workflow. Strict SemVer — breaking Swift API changes bump the minor pre-1.0; per-app migration stays explicit (each app updates its pin deliberately).
