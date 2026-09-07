# Rust target architecture

## Repository shape

Keep Go and Rust in this repository. Add one internal Cargo workspace only after the neutral oracle harness is green. Do not mirror the Go directory tree and do not create a cross-repository workspace.

```text
contracts/                         language-neutral SSOT (unchanged)
Go packages                       supported oracle + released Go API
rust/
  test-support/symaira-contract-fixtures  publish=false fixture loader/generator
  test-support/symaira-core-foundation    publish=false cross-crate parity tests
  symaira-core-exit                 exit codes and typed CLI errors
  symaira-core-version              version handshake and exact writers
  symaira-core-env                  ordered environment aliases
  symaira-core-log                  stderr logging construction
  symaira-core-config               XDG/TOML/env precedence
  symaira-core-fs                   atomic/path-safe filesystem operations
  symaira-core-secret               secret-reference parsing and process adapters
  symaira-core-mcp                  MCP models, raw framing and server adapter
  symaira-core-sqlite               SQLite open/migration policy
  symaira-core-update               check/extract/install/apply/cosign adapters
  symaira-core-llm                  descriptor registry and provider transports
  symaira-core-evidence             alignment and grounded JSONL contracts
  symaira-core-audit                hash-chain sink and checkpoints
  symaira-core-dom                  HTML selection/render boundary
  symaira-core-vector               TurboQuant codec and sidecar compatibility
  symaira-core-mcpcfg               JSON/JSONC/YAML MCP-config discovery
```

There is deliberately no umbrella or published contracts crate. Consumers depend
only on the independently usable crates they need. A version/exit consumer must
not pull TOML, tracing, Tokio, HTTP, SQLite, DOM or archive stacks.

## Dependency direction

```text
core-env ──→ core-config
   └────────→ core-log

core-exit ─→ core-mcp
core-fs ───→ core-audit
   ├───────→ core-sqlite
   └───────→ core-update
core-secret → core-llm

Independent leaves: core-version, core-evidence, core-dom, core-vector and
core-mcpcfg. The private fixture helper may depend on
Serde/test tooling; the private foundation test package composes the small
crates only for differential tests. Neither is a consumer dependency or
published package.
```

Allowed details:

- Contract JSON remains the cross-language source; generated Rust types carry provenance and drift tests rather than becoming a second SSOT.
- Small exit/version/env crates use only the minimum Serde/stdlib surface they actually need.
- `core-fs` owns its errors unless a concrete shared error dependency is justified; never depend on consumers.
- `core-secret` owns process-runner ports but not a hard dependency on `symvault`.
- `core-mcp` may provide an official-SDK adapter, but the owned wire model and raw-frame fixtures outrank SDK defaults.
- `core-sqlite` depends only on filesystem policy plus SQLite; migration SQL stays consumer-provided.
- `core-update` isolates HTTP, archives, checksums, Cosign process execution and replacement policy behind ports.
- `core-llm` reuses secret references; provider HTTP and streaming remain behind adapters.
- domain/algorithm leaves do not expose third-party parser or transport types publicly.

Every owned crate starts with `#![deny(unsafe_code)]`. Any exception needs a separate ADR, a safety invariant, focused tests, Miri where applicable and explicit review.

## API strategy

Rust is not required to reproduce Go type shapes. It must reproduce observable behavior and persisted/wire formats. Prefer:

- explicit enums and `thiserror` library errors;
- builders only where optional configuration is genuinely large;
- synchronous deterministic logic, with Tokio only at MCP/HTTP/process concurrency boundaries;
- `serde` names and omission rules copied from the contracts, never inferred from Rust identifiers;
- injected clock, filesystem, HTTP and process traits at side-effect boundaries;
- no public `reqwest`, `rmcp`, `rusqlite`, parser or platform types.

## Crate extraction rule

A crate is created only when one of these is true:

1. two active Rust consumers have the same proven need; or
2. the crate implements a language-neutral SSOT used by at least two languages; or
3. a security-critical format needs one canonical Rust implementation before two consumers reach it.

A consumer-local implementation is compared first. Extraction must delete/avoid duplicate code and retain consumer-specific policy outside CoreKit. Single-consumer leaves remain blocked until demand appears.

## Dual-language versioning and publishing

- Repository tags remain `vMAJOR.MINOR.PATCH` and continue to version the Go module.
- During migration, Rust workspace package versions remain `0.x` and are exact across internal edges.
- First adopters pin `git = "https://github.com/danieljustus/symaira-corekit", rev = "<40-hex>"` and commit `Cargo.lock`; tags are not treated as proof that every crate changed.
- crates.io publication starts only after API review, `cargo semver-checks`, provenance/SBOM setup and at least two real adopters.
- If crates are published, one release manifest maps the repository tag to each crate/version and verifies publish order. Independent crate versions are allowed; fake lockstep releases are not required.
- Released Symaira binaries pin each published CoreKit crate exactly (`=x.y.z`) and commit `Cargo.lock`; compatible ranges are not used to smuggle unreviewed shared-library updates into a product release.
- Go `apidiff` and Rust `cargo semver-checks` run independently. A breaking Go or Rust API change follows its own major-version policy and migration note.

## Oracle and differential design

RUST-001 creates a neutral fixture generator/harness that does not import Rust internals. Go helper binaries may expose otherwise in-process library behavior only to generate deterministic fixtures. Each case records:

- exact oracle commit and production-input digest;
- operation, typed input and environment allowlist;
- stdout/stderr/exit or returned JSON/error classification;
- recursive file manifest including type, mode and SHA-256;
- SQLite schema, pragmas and ordered query snapshots where applicable;
- HTTP request/response transcript, process argv and timeout outcome;
- comparison mode and explicitly justified ignored fields.

The harness first proves Go↔Go self-equality, source-digest rejection and a negative-control mismatch. It runs with isolated HOME/XDG/temp roots and fake credential/network/process adapters. A temporary HOME alone is not a sandbox.

## CI gates

Go gates stay mandatory throughout the transition. Rust gates are added without paths-filtering them away on pull requests that touch contracts or Rust code:

- pinned stable `rust-toolchain.toml`, `rust-version`, `Cargo.lock` and MSRV check;
- `cargo fmt --all --check`;
- `cargo check --workspace --all-targets --all-features`;
- Clippy with warnings denied;
- nextest plus separate doctests;
- feature-matrix checks that prove small crates do not activate unrelated stacks;
- coverage, `cargo audit`, `cargo deny`, SemVer checks for published crates;
- Miri for suitable core crates and fuzz/property tests at untrusted parsers;
- native macOS, Linux and Windows runtime tests; cross-compilation is not runtime proof;
- Go↔Rust fixture drift and differential jobs.

## Cutover semantics

CoreKit has no single binary cutover. Each consumer migrates one dependency at a time and retains its own Go rollback until that product's Rust cutover. Go packages remain released while any released Go consumer imports them. Removing Go is a separate repository-major decision, not the last Rust PR.