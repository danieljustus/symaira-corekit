# Resume checkpoint — SQLite and MCP-config slices complete, RUST-014/015 open

Owner: migration coordinator. No active CoreKit writer worktree. `RUST-006` is
`complete` and SQL-001 through SQL-006 are `parity` since the promotion decision
recorded in `sqlite-demand.md`; the scoped candidate-source change is integrated
as `541683a` (PR #291). Main baseline for the SQLite candidate remains
`82968b4fc9537daf62c2008331f5e5ce5d32b6c6`.

## Current state

`RUST-010` (MCP configuration discovery) is `complete`: the crate, the pinned
oracle harness and the corpus exist and the MCFG-001…MCFG-005 rows are `parity`
(see the slice section below). `demand-assessment.md` records the two Rust
consumers that duplicated the concern and the searches that show why `RUST-007`,
`RUST-008`, `RUST-009`, `RUST-011` and `RUST-012` stay `deferred`. Every
demand-driven item points at that document through `demand_evidence`; no
demand-driven item is `ready` any more.

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

## MCP-config discovery slice (RUST-010)

`rust/symaira-core-mcpcfg` ports the Go `mcpcfgkit` package: the client source
table, JSONC comment stripping, JSON/YAML normalisation, glob expansion,
transport and env merging, and the stable findings of `ScanAll`.

`scripts/rust-port/mcpcfg-differential.py --check` extracts the pinned oracle
commit `f3d3eb79b9b1f31b4f973d2ed518a8292cedf588` (v0.17.0) with `git archive`,
builds `scripts/rust-port/mcpcfg-oracle` against that extraction, and compares
exit code, stdout and stderr of both implementations for every case in
`testdata/rust-port/mcpcfg-cases.json` (24 cases, corpus coverage of
MCFG-001…MCFG-005 enforced). The five Go oracle commands named by the MCFG rows
exit 0.

Two boundaries are deliberate and documented in the crate:

1. Third-party parser text is not part of the frozen contract. Observations carry
   the `mcpcfgkit`-authored prefix (`parse JSON`, `parse "<key>"`, `parse YAML`,
   `key not found: "<key>"`, `key "<key>" is not an object`, `read failed`) plus
   a stable kind; the wrapped `encoding/json`, `yaml.v3` and OS detail is elided
   because it cannot be reproduced byte-for-byte.
2. Go builds `Server.EnvKeys`/`EnvValues` by iterating a map, so their order is
   unspecified. The observation layer sorts the index-aligned key/value pairs by
   key on both sides; comparing the raw order would have compared a random
   permutation. The first single PASS of this corpus was luck — the negative
   control run exposed it.

Evidence: `make rust-mcpcfg-contract` (fmt, check, Clippy `-D warnings`, tests),
7 unit tests plus 10 contract tests in `tests/parity.rs`, five consecutive
differential runs all `PASS` (determinism after the env-order fix), and three
negative controls that all fail as intended — mutating the Rust transport
resolution, collapsing the Go helper's finding kinds, and dropping one corpus
case (refused as a coverage mismatch). A CI job `rust-mcpcfg` runs the contract
on ubuntu/macos/windows and the differential on Linux.

## SQLite cost evidence (re-measured 2026-09-20)

The `SQL-006-80-BUILD` cost report of 2026-09-17 cannot be re-validated at any
revision of `main`: it binds `runner_sha256` to the bytes of `cost_gate.py` at
measurement time (`9e7b46c3…`) while that file changed inside PR #286 after the
measurement (`6da087b9…` today), so `cost_gate.py --check` failed with
`runner/validator hash mismatch`. The contract hash still matches (`3889439…`).

The gate was re-run over 80 builds (2 consumers × clean/warm × 10 samples, Rust
1.98.0, Go 1.26.6) and the new report validates:

```
$ NVME_RUNTIME=/Volumes/SymairaSecureRuntime NVME_STORAGE=/Volumes/1TB_NVMe_SN850X/Dev/Symaira_Dev \
  python3 scripts/rust-port/sqlite/cost_gate.py --check \
  --report /Volumes/SymairaSecureRuntime/BuildTargets/reports/sql006-consumer-cost-20260920-v1.json
{"report": "…/sql006-consumer-cost-20260920-v1.json", "status": "passed"}
```

- Report SHA-256 `ecfcb3700f86a8c09db708f009ddabd641a8aa97294076f4eca7de1c0c66f961`,
  80 of 80 cells, all six thresholds passed against the `1.10` limit: desktop
  time `0.989` clean / `0.979` warm, desktop artifact size `1.000004`, eraseme
  time `0.990` clean / `1.005` warm, eraseme artifact size `1.000`.
- The 2026-09-17 report stays on the volume as historical evidence.
- Re-measurement command: the `--check` line above; the run itself is
  `cost_gate.py --run --report <path>` with the same two environment variables.

Two environment repairs were required first:

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
3. That symlink exposed a `.gitignore` defect: `target/` matches only real
   directories, so the symlink showed as untracked and the release verifier
   rejected the checkout as dirty. `.gitignore` now uses `/target` plus
   `/fuzz/target/`. `symaira-vault/.gitignore` has the same defect (`/target/`)
   and is reported on vault#1080.

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

Artifacts on `main` before this branch (kept as history):

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

The MCP-config slice changed two enforced build inputs (`Cargo.toml` gained the
`rust/symaira-core-mcpcfg` member and a pinned `yaml-rust2` workspace dependency,
which `Cargo.lock` records), so the candidate was re-frozen on this branch with
the documented path — and in the order that path requires: the acceptance tests
were repointed to the final capture name *before* the manifest was written,
because `scripts/rust-port/sqlite/**` is itself enforced.

- `testdata/rust-port/sqlite/candidate-source.json`, SHA-256
  `fe68e798076dd4e6c348e7dd4c5f9999894a2dc1fcc2cbd3cf11a397301a3496`
  (74 recorded files, 39 enforced).
- `testdata/rust-port/sqlite/differential-macos-refreeze-20260920T175852Z.json`,
  SHA-256 `b3455f44fc38dea426220f0f0a2bef6a9f434dcea055f47205f926be1a4f2797`,
  typed verdict `passed` at revision `6e79b58…`, native darwin/arm64, six cases,
  42 checked fields, nine explicitly accepted differences, zero unresolved.
- 78 SQLite acceptance tests and the provenance test pass against the re-frozen
  pair; the five files that name the current capture were repointed in the same
  commit.

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

Next: no demand-driven item is `ready`. `RUST-014` needs an explicit publication
decision plus registry evidence; `RUST-015` needs the four classes in
`consumer-rollout-findings.md` closed. A further slice requires new
two-consumer demand evidence in `demand-assessment.md`. No release, publication,
Go removal or product cutover is authorized here.
