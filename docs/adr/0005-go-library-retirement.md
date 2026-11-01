# ADR 0005: Retire the Go library from `main`

Status: accepted, 2026-11-01, by the maintainer. Executed locally in the
local completion mode recorded in `docs/rust-port/resume-checkpoint.md`; the
final push runs ordinary CI once as acceptance.

## Decision

`main` no longer contains the Go module. The root `go.mod`/`go.sum`, all Go
library packages, the Go lint configuration, Go CI jobs, the Go release gate
and the Go consumer-pin drift tooling are removed. CoreKit on `main` is the
Rust workspace plus its language-neutral contracts (`contracts/`,
`llmkit/providers.json`).

- **Frozen Go state:** `v0.18.3` (`0a446ac7c37c7c29995c261cfa89067196a4f9f4`)
  is the last Go release from `main`. Consumers that still import the Go
  module (Vault, Desktop, Brain at the time of this decision) keep their exact
  pins; the module proxy and the tag stay available.
- **Go maintenance line:** Go fixes ship only from branch `release/v0.18`
  (created at `v0.18.3`) as `v0.18.N` patch tags. That branch keeps its own Go
  CI, release workflow and consumer-pin drift tooling. No Go feature work.
- **Fixture provenance:** frozen Go observations still bind exact Go source
  bytes. Verifiers read retired Go paths from the immutable `v0.18.3` commit
  through `scripts/rust-port/retired_go.py`; a full clone with that commit is
  required and a missing anchor fails closed. The Go oracle harness under
  `scripts/rust-port/` stays byte-identical because SQLite, FS/SEC and update
  fixture provenance hashes bind those files. It is never built by any `main`
  gate.
- **Live Go recapture** (`GO_ORACLE=1`, `rust-sqlite-refreeze`,
  `rust-fs-secret-live-oracle`, the dispatch-only capture jobs) is retired on
  `main`. A genuine recapture runs on `release/v0.18`.

## Reasoning

The shared Rust closure is accepted (RUST-001..013, RUST-017; Go-free native
aggregate, #368). Every remaining Go importer pins an exact released version,
so removing Go from `main` does not break any consumer build. Keeping a second
live implementation on `main` would keep doubling CI, review and security
maintenance for code that new work no longer uses. A separate maintenance
branch keeps a supported Go path for the consumers still being ported without
blocking the Rust-only CoreKit.

## Consequences

- `go get github.com/danieljustus/symaira-corekit@latest` resolves to the
  newest tag. A later Rust-only tag contains no Go packages, so Go users must
  pin `v0.18.x`. Repository `vX.Y.Z` tags after `v0.18.3` on `main` describe the
  Rust workspace (ADR 0002 distribution by exact Git revision is unchanged).
- Required GitHub status contexts that named removed jobs (`govulncheck`,
  `apidiff`, `cross (…)`) must be replaced by `merge gate` / `audit` before the
  first push of this change.
- RUST-016 (released Rust-only consumers) is unchanged: each consumer still
  needs its own Rust-only cutover. This decision only removes CoreKit's own Go
  implementation.

## Rollback

Restore Go on `main` with `git revert` of the retirement commit; `v0.18.3` and
`release/v0.18` remain the reference implementation in the meantime.
