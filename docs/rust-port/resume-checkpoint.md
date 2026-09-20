# Resume checkpoint — SQLite candidate-source scope

Owner: migration coordinator. No active CoreKit writer worktree; the scoped
change is integrated on `main` as squash commit
`541683a0fc86caee5e2ef3334f1948fda52296a1` (PR #291, based on
`896eac148dfc44232f8763be08d45e7ee795de6e`). Main baseline for the SQLite
candidate remains `82968b4fc9537daf62c2008331f5e5ce5d32b6c6`.

## Current evidence and finding

The frozen candidate manifest enforced its complete forensic source set, so a
workflow-only or unrelated-crate edit failed 10 of 74 acceptance tests
(`frozen source manifest is not bound to the current candidate source`) and
forced a full Go/Rust recapture for routine dependency maintenance
(`danieljustus/symaira-corekit#290`). Verification now binds only the enforced
port inputs — workspace build inputs, `rust/symaira-core-sqlite/**`, its
workspace path dependency `rust/symaira-core-fs/**`, and
`scripts/rust-port/sqlite/**` — while the manifest keeps recording the full set
as forensic context. Decision and per-file-class table:
`docs/rust-port/adr-rust-003-candidate-source-scope.md`.

Fresh artifacts, both generated in the worktree above:

- `testdata/rust-port/sqlite/candidate-source.json`, SHA-256
  `33af092cff62dd6e7012ef9d2c94c1c42bb10e81baf4eea15fa292fb56116e1f`
  (70 recorded files, 39 enforced).
- `testdata/rust-port/sqlite/differential-macos-bound-candidate-scope-20260920.json`,
  SHA-256 `943aa645577fe3040a50687f7764865f0c98525959d7bff847898003a640775f`,
  typed verdict `passed` at revision `896eac1…`, native darwin/arm64, six cases,
  42 checked fields, nine explicitly accepted differences, zero unresolved.

Local results: 78 SQLite acceptance tests and 1 provenance test passed; the
scope negative control (workflow, `.gitattributes` and unrelated-crate edits)
stayed green; the binding control (edit to `rust/symaira-core-sqlite/src/lib.rs`)
still failed 10 tests + 2 errors; `cargo fmt --all --check`, the
`symaira-core-sqlite` package tests (including the consuming-close compile-fail
doctest) and Clippy with `-D warnings` passed; `docs/rust-port/validate.py`
passed. The earlier capture
`differential-macos-bound-rust006-upload-artifact-v7-20260920.json` is retained
unchanged as historical evidence.

Generation is not approval, so the new manifest and capture were independently
reviewed: an adversarial review reproduced the capture at the integrated
revision and found the verdict, case IDs, checked fields, accepted differences,
native identity and the 39-file enforced subset of the 70 recorded files
identical; only the revision, the example binary digest and the capture
timestamps differ, as expected. The native SQLite lanes passed on ubuntu-latest,
macos-latest and windows-latest in the PR #291 run. The consumer/value gates
remain open.

## Resume without restarting

From a fresh worktree of `main`:

```sh
python3 -m unittest discover -s scripts/rust-port/sqlite -p 'test_*.py'
python3 -m unittest discover -s scripts/rust-port -p 'test_rust_sqlite_provenance.py'
make rust-sqlite-contract
```

`make rust-sqlite-refreeze` is the documented recapture path for a genuine
port-input change. It regenerates the manifest and writes a new capture; it
never runs automatically, and it does not repoint the acceptance tests.

Next: re-confirm the Desktop value gate and the two-consumer cost evidence
before promoting SQL-001 through SQL-006 in the contract matrix; RUST-014 needs
an explicit registry authorization and RUST-015 stays blocked on released
consumer evidence. Remaining CoreKit contracts, consumer/value gates and native
foreign-platform evidence stay open. No PR/release/product cutover; no history
rewrite.
