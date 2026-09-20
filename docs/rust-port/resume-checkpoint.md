# Resume checkpoint — SQLite slice complete, RUST-010 ready, RUST-014/015 open

Owner: migration coordinator. No active CoreKit writer worktree. `RUST-006` is
`complete` and SQL-001 through SQL-006 are `parity` since the promotion decision
recorded in `sqlite-demand.md`; the scoped candidate-source change is integrated
as `541683a` (PR #291). Main baseline for the SQLite candidate remains
`82968b4fc9537daf62c2008331f5e5ce5d32b6c6`.

## Current state

`RUST-010` (MCP configuration discovery) is `ready`: `demand-assessment.md`
records the two Rust consumers that duplicate the concern and the searches that
show why `RUST-007`, `RUST-008`, `RUST-009`, `RUST-011` and `RUST-012` stay
`deferred`. Every demand-driven item now points at that document through
`demand_evidence`.

`RUST-015` stays `blocked`, but no longer for an unexamined reason:
`consumer-rollout-findings.md` splits the 32 verifier findings into stale
`checkout_commit` records, stale `rust.status`, consumer checkout hygiene, and
the genuine missing `evidence.standalone`/`rollback` for eraseme and vault.
Tracked in corekit#295 plus eraseme#993, desktop#984 and vault#1080.

`RUST-014` stays `in_progress`. `python3 port/release/verify.py --dry-run` passes
and the release/consumer governance tests pass, but registry evidence does not
exist and the crates stay `publish = false`. `cargo semver-checks check-release`
must not be counted as API-compatibility evidence — it skips every candidate
(`Skipping <crate> v0.0.0 (current)`) because nothing is published, and the
dry-run now prints `semver baseline: none … API compatibility stays unverified`.
`release-manifest.md` fixes the sequencing: no publication before the full
migration, consumer rollout and registry evidence are complete, so no
publication decision is available yet.

## SQLite cost evidence (re-measurement in progress)

The `SQL-006-80-BUILD` cost report of 2026-09-17 lives on the secure-runtime disk
image and is **not** re-readable as-is: the volume was detached, and after
mounting it the verifier still rejects the report —

```
$ NVME_RUNTIME=/Volumes/SymairaSecureRuntime NVME_STORAGE=/Volumes/1TB_NVMe_SN850X/Dev/Symaira_Dev \
  python3 scripts/rust-port/sqlite/cost_gate.py --check \
  --report /Volumes/SymairaSecureRuntime/BuildTargets/reports/sql006-consumer-cost-20260917-v1.json
FAIL SQL-006 cost gate: runner/validator hash mismatch
```

The report binds `runner_sha256` to the bytes of `cost_gate.py` at measurement
time (`9e7b46c3…`); the current runner is `6da087b9…`, because that file changed
inside PR #286 after the measurement. The contract hash still matches
(`3889439…`). The report therefore cannot be re-validated at any revision of
`main`; a fresh measurement is required.

Two repairs were needed before a re-run could start at all:

1. The secure-runtime disk image
   (`BuildTargets/SymairaSecureRuntime.sparsebundle` on the Dev NVMe) was
   detached; it is mounted again at `/Volumes/SymairaSecureRuntime`.
2. `dev-external --status` rejected the dev-storage layout because
   `Repos/symaira-corekit/target` and `Repos/symaira-vault/target` had been
   replaced by real directories instead of symlinks. The two replaced trees were
   moved (not deleted) to
   `/Volumes/1TB_NVMe_SN850X/AI/Hermes Workspace/dev-cache-repair-20260920/` and
   the symlinks to `Symaira_Dev/builds/<repo>/target` were restored;
   `dev-external --status` now reports `mounted: true, verified_links: 9`.

The 80-build re-run (`cost_gate.py --run`) writes
`BuildTargets/reports/sql006-consumer-cost-20260920-v1.json` and was still
running when this checkpoint was written. Until it passes, the promotion of
`RUST-006` rests on the earlier validated report plus the byte-identical crate
revision (consumers pin `0f441fb`; `git diff 0f441fb..541683a` over the crate,
its path dependency and the build inputs is empty). Update this section with the
new report path, hash and verdict when the run finishes.

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

Next: `RUST-010` is the only `ready` item — its slice needs the contract fixtures
and differential suite that its acceptance commands name. `RUST-014` needs an
explicit publication decision plus registry evidence; `RUST-015` needs the four
classes in `consumer-rollout-findings.md` closed. No release, publication, Go
removal or product cutover is authorized here.
