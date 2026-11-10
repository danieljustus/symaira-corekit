# Agent Instructions — symaira-corekit

## Current product contract

Read [PB-2026-09-09](docs/product-boundaries.md) before changing ownership or integration boundaries. It is the accepted target, not a completed migration. CoreKit is the single shared-library repository; the former `symaira-appkit` Swift package lives under `swift/` ([ADR 0006](docs/adr/0006-appkit-merged-into-corekit.md)). Require two real consumers per shared module. No credential crypto, browser engine, native automation or product-domain policy belongs here merely to enable consolidation.

This repository is the public Apache-2.0 licensed shared library for Symaira public-core tools (Rust crates) and native clients (Swift package).

## Ecosystem Guidance

- Before changing cross-tool integrations, shared conventions, or product
  boundaries, read [PB-2026-09-09](docs/product-boundaries.md); it is available in standalone checkouts.
- Keep the standalone-first contract: this library must not make any consumer
  require another Symaira tool at build time or startup.

## Repository Role

- `main` is a Rust workspace plus the Swift package under `swift/`. The Go library was retired after v0.18.3 ([ADR 0005](docs/adr/0005-go-library-retirement.md)): no Go library code, `go.mod` or Go CI on `main`. Go fixes for consumers that still import the Go module (`symvault`, `symdesk`, `symbrain` until their Rust-only cutovers) land only on branch `release/v0.18` as `v0.18.N` tags.
- Crates under `rust/`: `symaira-core-exit`, `-version`, `-env`, `-log`, `-config`, `-fs`, `-secretref`, `-mcp`, `-mcpcfg`, `-llm`, `-sqlite`, `-update`. Language-neutral contracts live in `contracts/`; `llmkit/providers.json` is generated from `contracts/llm_providers.json` by `scripts/rust-port/llm_providers_gen.py`.
- Swift package (AppKit): sources, tests, scripts and GUI rules under `swift/`; `Package.swift` at the repository root (SwiftPM resolves remote packages only there). Read [`swift/AGENTS.md`](swift/AGENTS.md) before Swift or GUI work.
- Every crate and Swift module must be independently usable and testable.
- Preserve standalone-first behavior for every consumer. Corekit may provide reusable helpers and conventions, but it must never make any public tool require another Symaira tool at build time or startup.

## Build & Test

```bash
make build              # cargo build --workspace --all-targets --locked
make test               # cargo test --workspace --all-features --locked
make lint               # cargo fmt --check + clippy -D warnings
make rust-contracts     # Go-free native contract aggregate
make swift-test         # Swift package build + tests (full Xcode required)
make swift-lint         # swift-format --strict
```

No gate may require a Go toolchain. Frozen Go fixture provenance reads retired Go sources from the immutable `v0.18.3` commit (`scripts/rust-port/retired_go.py`); keep the hash-bound oracle harness under `scripts/rust-port/` byte-identical.

## Architecture & Constraints

- **No system library dependency**: builds use the pinned toolchain in `rust-toolchain.toml` and `--locked`; SQLite is bundled.
- **Zero Stdio Pollution**: MCP server transport runs over stdio. Never print to stdout except structured JSON-RPC 2.0 messages.
- **No Cloud/SaaS concepts**: No Firebase, Stripe, GCP SDK, or billing code. This is a public Apache-2.0 library.
- **No tool-specific business logic**: No vault crypto, no memory PII rules, no seek ranking, no fetch fingerprinting, no scope port scanning.
- **No cross-tool coupling**: Do not depend on `symaira-vault`, `symaira-memory`, `symaira-seek`, `symaira-fetch`, `symaira-scope`, or any of their internal modules. Optional integrations must remain runtime contracts implemented by consumers.
- **Cross-language conventions**: CoreKit's Rust crates share conventions (exit codes, XDG paths, env var naming, MCP stdio framing, zero stdout pollution) that also guide the Swift and Python free tools. See `docs/cross-language-conventions.md`.
- **Exact pins**: Rust consumers pin a full 40-character Git revision plus `Cargo.lock` ([ADR 0002](docs/adr/0002-rust-distribution-git-pins.md)); crates stay `publish = false`. Swift consumers pin an exact tag (`.package(url: "https://github.com/danieljustus/symaira-corekit.git", exact: "X.Y.Z")`, products from `package: "symaira-corekit"`).
- **GUI handshake contract (`symaira-core-version`)**: every core's `version --json` subcommand must emit the `Info` payload (`{tool, version, schema_version}`). the Swift package's `SymairaToolKit` (`swift/`) performs its schema handshake against exactly these field names — never rename them. Bump the tool's `schema_version` whenever its machine-readable JSON output changes incompatibly. The plain `version` output should stay "tool vX.Y.Z" so appkit's fallback parser keeps working.

## Consumer Bump Ownership

Each consumer pins an exact CoreKit revision (Rust: Git revision in
`Cargo.toml`/`Cargo.lock`; Go: `v0.18.x` in `go.mod` until its Rust-only
cutover). Raising those pins after a CoreKit change is owned explicitly;
`danieljustus/symaira-corekit#157` found four consumers three-plus releases
behind when nobody owned it.

- **Who bumps:** the corekit maintainer (@danieljustus) bumps every listed
  consumer's pin, one change per consumer, verified by that consumer's own
  test suite.
- **Trigger:** within two weeks of a corekit release (or a `release/v0.18`
  Go patch), or immediately before cutting a consumer's own release —
  whichever comes first.
- **Follow-up mechanism:** `make consumer-drift` runs
  `port/consumer/verify.py` against every record in `docs/consumers.json` and
  lists each sibling checkout's Go pin.
- Add new consumers to `docs/consumers.json` when they start depending on
  corekit; remove or update entries when a consumer is archived, renamed, or
  cuts over (`go_status: retired`).

## Key Dependencies

- `toml` — TOML config parsing
- `serde` / `serde_json` — JSON contracts
- `rusqlite` (bundled) — SQLite
- `ureq` / `reqwest` with rustls — HTTPS for update checks and LLM transport
