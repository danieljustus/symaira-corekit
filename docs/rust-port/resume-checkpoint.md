# Resume checkpoint — SQLite slice complete, RUST-014/015 open

Owner: migration coordinator. No active CoreKit writer worktree. `RUST-006` is
`complete` and SQL-001 through SQL-006 are `parity` since the promotion decision
recorded in `sqlite-demand.md`; the scoped candidate-source change is integrated
as `541683a` (PR #291). Main baseline for the SQLite candidate remains
`82968b4fc9537daf62c2008331f5e5ce5d32b6c6`.

## Current state

`RUST-014` stays `in_progress`: its non-registry acceptance (`cargo
semver-checks check-release`, the release/consumer governance verifier tests and
`port/release/verify.py --dry-run`) runs green in the `Rust release manifest` CI
job, but registry evidence does not exist and the Rust crates are still
`publish = false`. `RUST-015` stays `blocked` on released-consumer evidence, and
`RUST-007` through `RUST-012` stay demand-driven `deferred`.

One evidence limitation is recorded in `sqlite-demand.md`: the measured
`SQL-006-80-BUILD` cost report lives on the secure-runtime volume
(`/Volumes/SymairaSecureRuntime`), which is currently detached, so its numbers
were not re-read during the promotion. Re-read that report when the volume is
mounted again; the promoted crate bytes are unchanged since the consumers
adopted `0f441fb`.

## Candidate-source scope (integrated)

The frozen candidate manifest previously enforced its complete forensic source
set, so a workflow-only or unrelated-crate edit failed 10 of 74 acceptance tests
(`frozen source manifest is not bound to the current candidate source`) and
forced a full Go/Rust recapture for routine dependency maintenance
(`danieljustus/symaira-corekit#290`). Verification now binds only the enforced
port inputs — workspace build inputs, `rust/symaira-core-sqlite/**`, its
workspace path dependency `rust/symaira-core-fs/**`, and
`scripts/rust-port/sqlite/**` — while the manifest keeps recording the full set
as forensic context. Decision and per-file-class table:
`docs/rust-port/adr-rust-003-candidate-source-scope.md`.

Artifacts on `main`:

- `testdata/rust-port/sqlite/candidate-source.json`, SHA-256
  `33af092cff62dd6e7012ef9d2c94c1c42bb10e81baf4eea15fa292fb56116e1f`
  (70 recorded files, 39 enforced).
- `testdata/rust-port/sqlite/differential-macos-bound-candidate-scope-20260920.json`,
  SHA-256 `943aa645577fe3040a50687f7764865f0c98525959d7bff847898003a640775f`,
  typed verdict `passed` at revision `896eac1…`, native darwin/arm64, six cases,
  42 checked fields, nine explicitly accepted differences, zero unresolved.
- The earlier capture
  `differential-macos-bound-rust006-upload-artifact-v7-20260920.json` is retained
  unchanged as historical evidence.

Verification of that change: 78 SQLite acceptance tests and 1 provenance test
passed; the scope negative control (workflow, `.gitattributes` and
unrelated-crate edits) stayed green while the binding control (edit to
`rust/symaira-core-sqlite/src/lib.rs`) still failed; `cargo fmt --all --check`,
the `symaira-core-sqlite` package tests (including the consuming-close
compile-fail doctest) and Clippy with `-D warnings` passed; an independent
adversarial review reproduced the capture at the integrated revision and found
verdict, case IDs, checked fields, accepted differences, native identity and the
39-file enforced subset identical; the native SQLite lanes passed on
ubuntu-latest, macos-latest and windows-latest in the PR #291 run and on `main`.

## Resume without restarting

From a fresh worktree of `main`:

```sh
python3 docs/rust-port/validate.py
python3 -m unittest discover -s scripts/rust-port/sqlite -p 'test_*.py'
python3 -m unittest discover -s scripts/rust-port -p 'test_rust_sqlite_provenance.py'
make rust-sqlite-contract
```

`make rust-sqlite-refreeze` is the documented recapture path for a genuine
port-input change. It regenerates the manifest and writes a new capture; it
never runs automatically, and it does not repoint the acceptance tests.

Next: `RUST-014` needs an explicit decision to publish the adopted Rust crates
(version/order/provenance and a registry account) before registry evidence can
exist; `RUST-015` needs released-consumer evidence and stays blocked until then.
No release, publication, Go removal or product cutover is authorized here.
