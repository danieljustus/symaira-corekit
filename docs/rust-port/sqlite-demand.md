# RUST-006 demand and execution checkpoint

Tracking: [corekit #256](https://github.com/danieljustus/symaira-corekit/issues/256).

## Oracle review checkpoint

**Current checkpoint superseding the historical draft below:** the repaired
11-file oracle bundle `2cead3b8bd3ba8a13b8d0009df1b11e2648a820f1de8f03e0ef5a5c12ffb8bd9`
received independent PASS for bounded macOS preparation. Repaired files were
transferred without cherry-picking the draft commit into this coordinator
worktree. Six Go race tests, vet, fresh capture/drift check and 19 Python
mutation/process tests passed again here. Run helper Go tests from the nested
`scripts/rust-port/sqlite` module, not the repository root.

The private Rust connection/migration implementation now exact-pins rusqlite
0.40.2 (bundled, defaults disabled). Scoped Cargo check and strict Clippy passed;
audit and deny passed with non-fatal duplicate warnings. Tests and differential
adapter implementation are assigned to `.worktrees/rust-006-parity` on branch
`rust/rust-006-parity`, with an explicit coordinator source snapshot. Their
results and native/consumer/cost gates remain pending. Shared manifests and
lockfile remain coordinator-owned. No SQL matrix row is marked complete.

### Historical rejected draft

The first draft at `99ba046e24d5f90712d67b69815bc5fefc307af8` exists in
`.worktrees/subagent-sa-0-b32f4dcc`, not in the coordinator worktree. It is
not integrated or accepted. Independent execution of its helper test and
vet passed, but review found hardcoded WAL observations, incomplete source
provenance, insufficient error/state observations and missing locking and
mutation/rejection proof. Repair this artifact and re-review before Rust
implementation; no SQL contract status is promoted by its six case IDs.

Upstream reuse was rechecked: `rusqlite/rusqlite` is active and MIT-licensed.
Desktop's cited revision exact-pins `rusqlite =0.40.2` with bundled SQLite;
EraseMe's cited revision uses `0.37` with backup/bundled. A shared crate must
resolve this version skew explicitly rather than assuming interchangeable
`Connection` types. No dependency was added by this checkpoint.

## Current Rust differential checkpoint (supersedes earlier assignments)

RUST-006 remains **in_progress**, not parity-complete. The assigned test worker
used an unrelated automatic checkout and returned no changes; no worker is
currently implementing this slice. The coordinator implemented and exercised
`rust/symaira-core-sqlite/tests/contracts.rs`,
`rust/symaira-core-sqlite/examples/sqlite-observe.rs`, and
`scripts/rust-port/sqlite/diff.py` in `.worktrees/rust-006-sqlite`.

The native macOS diagnostic capture is retained at
`../../testdata/rust-port/sqlite/differential-macos-partial.json`
(SHA-256 `137e5ffeca6ffd560cf8ded7b5fcc721c2f408cc618c1a47f556d1493579729d`).
It contains both real adapter reports, source identities and the partial verdict:
six SQL groups, 41 enumerated comparison fields, nine unresolved differences.
Eight differences concern driver/OS diagnostic wording; the ninth is Go's
closed database handle, which cannot be passed safely after Rust's consuming
`Connection::close`. No normalization or approved-difference waiver clears them.
This capture is diagnostic evidence for the dirty candidate, not release evidence.
It remains unchanged as the regression anchor. After comparator hardening, a
fresh execution is retained separately as
`../../testdata/rust-port/sqlite/differential-macos-controls.json`; it still
reports the same nine differences. Seven comparator controls now reject missing
case IDs, adjacent large integers, missing NULL fields, boolean/integer aliasing,
rollback drift and policy drift, and preserve the historical partial verdict.

Executed on this candidate:

- SQLite all-target/all-feature tests: five tests passed.
- Full Cargo workspace tests and strict all-target/all-feature Clippy: exit 0.
- `GOTOOLCHAIN=go1.26.6 make build test`: exit 0, including Go race tests.
- Fresh Go oracle generation, `generate.py --check`, and 26 Python tests
  (19 generator tests plus seven comparator controls): exit 0.
- `python3 docs/rust-port/validate.py` and `git diff --check`: exit 0.
- `python3 scripts/rust-port/sqlite/diff.py --output <new-report>`: exit 1,
  intentional partial verdict retaining the nine differences above.

For repeatable local oracle execution, first expose the installed compiler,
not the HOME-dependent Go downloader wrapper:
`export PATH="$(GOTOOLCHAIN=go1.26.6 go env GOROOT)/bin:$PATH"`.
The isolated HOME otherwise makes that wrapper report the toolchain as missing;
the pinned physical compiler was verified and successfully reran the capture.

**Approved target contract:** the maintainer accepted the recommended typed
Rust error phase/cause contract and consuming close in the continuation approval.
Raw provider/OS wording is retained as diagnostic evidence, not a byte-equivalence
requirement. `typed_contract.py` requires matching classified SQLite primary codes
or I/O kinds plus the exact migration phase; missing/unclassified/wrong causes
fail. Only the named consuming-close case is waived, backed by the Rust
compile-fail doctest. The strict historical comparator remains available.
`diff.py --typed-errors` passed all six scenario groups locally, retaining the
nine approved differences in `differential-macos-typed.json`; this does not waive
state, schema, rollback, timing or native-platform requirements.

**Review repair checkpoint:** the first typed-contract review found missing
Rust success validation and insufficient source binding. Historical captures
remain authentic but cannot satisfy current acceptance. The Rust adapter now
emits computed per-case success and compiled OS/architecture identity.
`evaluate` requires success, matching native identities, and a pre-frozen source
manifest. Capture checks the exact source inventory before building and after
execution; it verifies base ancestry and records the actual revision separately.
`candidate.py` is an explicit freeze operation, never run automatically by CI.
The frozen `candidate-source.json` and fresh `differential-macos-bound-rust006-20260916.json`
must receive independent review together before being acceptance evidence.
The old state-only comparator is private and used only by historical regression
tests, not the live acceptance entrypoint.

The repaired local capture passed six groups with the approved differences;
42 Python tests, five Rust contract tests, the consuming-close compile-fail
doctest and strict Clippy passed. Native SQLite CI lanes for Linux/macOS/Windows
are prepared in `ci.yml` for main pushes/manual dispatch, with retained report
artifacts. They have **not executed**. Exact source/fixture LF checkout rules are
declared in `.gitattributes`; native checkout/runtime verification is still open.

**Historical independent local review: PASS for the prior source snapshot.**
The immutable review bundle remains at
`../../testdata/rust-port/sqlite/review-source-bundle.json`, SHA-256
`0a9bfee3ad56ee3e49b4ebc88b1d4d57f742c6bf1bda664d172f57dcc81045d0`.
It verified the then-frozen candidate, but it cannot approve later source bytes.

The current candidate repairs local oracle reproducibility: it resolves the
pinned Go compiler before replacing `HOME`, so the isolated runtime does not
mistake an installed `go1.26.6` for a missing download. The dependency inventory
has a bounded 300-second allowance for a cold isolated Go cache. The explicit
candidate-source manifest was regenerated for this change. The prior macOS
capture remains in `differential-macos-bound.json` as historical evidence for
its original source snapshot. The fresh macOS arm64 capture for RUST-014 is
retained in `differential-macos-bound-rust014.json` with SHA-256
`dc5a5ec9eb7c9f0fc85a4610806a41811e4df80361094f11262ad1e76f44de2d`; its
six-group typed differential passed with Go `go1.26.6`, and it measured the
Rust busy wait at 5.069667334 seconds. This is a real local capture, not a
synthetic fixture.

The latest review repair validates the complete Rust observation shape before
comparison: connection policy, migrations/schema/data/timestamps, rollback and
negative corpus must all pass independently of Rust's per-case `success` flag.
The measured Rust contention duration is now an enforced 4.5–6.0 second contract
for the configured 5000 ms timeout. Two mutation controls remove a Rust negative
observation and the timing measurement; both must fail before Go/Rust comparison.
The local SQLite test suite now has 48 Python controls. These additions resolve
review findings but still require independent review of the refreshed source
manifest before becoming acceptance evidence.

**Next action:** independently review the refreshed candidate manifest, then
execute native Linux/macOS/Windows, consumer-integration and cost gates. These
remain pending. No SQL matrix row is promoted; no publication or Go removal is
authorized by this checkpoint. Existing files and both recovery worktrees are
preserved.

## Native CI checkpoint on 933cb157

Candidate `933cb157914f84683f5a5546766a87f9dd7d34b4` is pushed in
[PR #257](https://github.com/danieljustus/symaira-corekit/pull/257).
[Native run 34316388944](https://github.com/danieljustus/symaira-corekit/actions/runs/34316388944)
passed the Linux SQLite lane, failed the Windows lane on an unclassified private
Go fsutil mkdir sentinel, and failed the macOS lane on a false Rust case-success
observation. The macOS exception path did not retain its raw report, so the
specific false predicate is unknown; no timing threshold is relaxed or cause
assumed. The repair records raw observations on validation failure and retains
the measured Rust busy duration. The Windows classifier recognizes only the
exact pinned mkdir sentinel with an independently observed regular-file target.

Linux and Windows reports were downloaded and verified against the reviewed
manifest and exact candidate revision. Retained files are
`native-933cb157-linux.json` (SHA-256
`4c2acf7f79d38df64c3ab900782b029764ed67be00b3a9a22cb6cc4b6f5bf325`)
and `native-933cb157-windows.json` under `testdata/rust-port/sqlite/`.
The Windows JSON is an LF-only derivative (SHA-256
`94c93576a41edd4702312ba317687d71f0612fd04fa23630ece516ccc3074bf7`);
its complete original bytes are retained as `native-933cb157-windows-original.b64`
(decoded SHA-256 `5a039ca8ba0925623a58667ea15f2cebeaa98c45ebf33f2e71d25ab162d5f435`).
Parsed original/derived JSON values were verified identical. These historical
reports do not certify the subsequent repair revision. Local repair validation
passed the Go race/vet helper, strict Clippy, fresh differential and 46 Python
tests. Native rerun remains required; the original review does not cover these
subsequent harness edits.

## Manual native rerun on a2f06fa7

The deliberately dispatched native CI run
[`34361781764`](https://github.com/danieljustus/symaira-corekit/actions/runs/34361781764)
ran the otherwise PR-skipped SQLite job on the exact merged PR head. Linux
passed. macOS retained a raw report and failed correctly: Rust measured
7.087585583 seconds for the 5000 ms busy-timeout contract, so
`within_busy_timeout` was false rather than silently widened. Windows failed
before capture because the isolated Go runner checked `bin/go` instead of the
actual `bin/go.exe`. This follow-up fixes that Windows lookup and adds a
platform-specific regression control. A fresh native rerun is still required.
The macOS timeout overrun remains a real parity/lifecycle blocker: do not relax
the 4.0–6.0 second contract, mark SQL-002 complete, or treat local macOS success
as native-CI proof until there is a behavior-preserving root-cause fix.

## Scope and decision

The SQLite slice may begin because two real Rust consumers implement the shared connection policy: a 5000 ms busy timeout, foreign-key enforcement and WAL. This establishes demand, not adoption or parity. Consumer schemas and product-specific migrations remain outside CoreKit. In particular, EraseMe's `user_version` schema lifecycle differs from Desktop's per-file transactional migration runner; do not claim those algorithms are identical.

Verified GitHub sources:

- Desktop [#863](https://github.com/danieljustus/symaira-desktop/pull/863), merged commit `c19389fb0c38efa2c5a795084c23d789fc8a40ff`: `crates/symdesk-index/src/lib.rs`, `Sidecar::open` and `migrate`.
- Desktop [#867](https://github.com/danieljustus/symaira-desktop/pull/867), merged commit `b7fbd1431f12b4a21569e5efd08e4958ea900638`: database interoperability harness. Existing evidence, not a new native run in this session.
- EraseMe [#883](https://github.com/danieljustus/symaira-eraseme/pull/883), open head `742a764f4011224a30df07aae1074c7aba2d8094`: portable connection helper.
- EraseMe [#886](https://github.com/danieljustus/symaira-eraseme/pull/886), open head `c1e7b45b9100805386a3aa44c8eecd82eb4978e7`: `crates/symeraseme-core/src/storage/store.rs`, schema lifecycle and repository tests.
- EraseMe [#888](https://github.com/danieljustus/symaira-eraseme/pull/888), open head `1ab2370d09cf59c68561995dadab896fbf70cb52`: projection implementation. Open work is demand evidence only, never released-consumer evidence.

## Baseline at 7150c0ad4cd20e59958262df34bf8035ba9f1e8b

Observed locally on macOS arm64 with Go 1.26.6 and Rust 1.98.0:

- `GOTOOLCHAIN=go1.26.6 make build test lint`: exit 0, race tests and lint passed.
- Explicit-root Cargo format, all-target/all-feature Clippy and workspace tests: exit 0. Doctest runner succeeded but there are no doctest cases.
- `make rust-port-validate`: exit 0; live two-consumer adoption and retained benchmark validation passed. This is not a fresh performance measurement.
- Release and consumer verifier unittest discovery: 6 and 40 tests passed respectively.
- `make port-fixture-source-check port-oracle-selftest mcp-differential`: exit 0; 46 MCP differential cases passed.
- `python3 scripts/rust-port/diff_fs_secret.py`: exit 0; 13 observable rows passed.
- Explicit-root `cargo semver-checks check-release` and `python3 port/release/verify.py --dry-run`: exit 0. No registry publication or public-byte readback performed.

These results certify the existing base only, not the forthcoming SQLite implementation or native Linux/Windows execution.

## Dependency order and ownership

1. RUST-006 oracle: production Go observations, source provenance, isolation and negative controls. Worker owns only `scripts/rust-port/sqlite/` and `testdata/rust-port/sqlite/`.
2. Coordinator: freeze the shared Rust manifest/dependency and narrow connection/migration API after reviewing the oracle.
3. Rust implementation, exact differential comparison and independent review.
4. Native locking/migration/rollback tests, two consumer integrations removing duplication, and 10-run cost evidence. Keep RUST-006 non-complete until these pass.

Owned worktree: `.worktrees/rust-006-sqlite`; branch `rust/rust-006-sqlite`; base as above. No publication, Go removal, production data access or sibling-repository changes are authorized by this slice. RUST-007 through RUST-012 remain deferred pending their own demand evidence. RUST-014 still lacks authorized registry evidence; RUST-015 still requires released consumer and rollback evidence.

## Bounded SQL-006 execution checkpoint — 2026-09-16

This section is the current handoff for the assigned worktree. Earlier capture
sections remain historical evidence and were not relabeled or overwritten.

### Candidate decision and preserved delta

- Worktree: `/Volumes/1TB_NVMe_SN850X/Dev/Symaira_Dev/Repos/symaira-corekit/.worktrees/rust-batch-20260916`; branch `migration/rust-batch-20260916`; base and candidate revision `82968b4fc9537daf62c2008331f5e5ce5d32b6c6`.
- Canonical candidate: the current assigned integration source at that exact
  base, after the bounded acceptance/provenance repairs. It was selected over
  retained `migration/rust-integration-20260913` (`62edd99`),
  `migration/rust-watch-sql006-errors-20260913` (`91c9ff9`),
  `repair/checkpoint-provenance-repair` (`2b4d51b`) and
  `migration/rust-watch-sql006-review-repair-20260913` (`3c3dfad`) because
  those trees are older/divergent and their actual diffs either remove
  regression controls or carry stale acceptance references. No whole retained
  stack was transplanted; the audit is `/private/tmp/sql006-candidate-diff-audit.txt`.
- The pre-existing `docs/rust-port/work-items.json` delta was preserved and
  audited, not reverted: it replaces the invalid
  `python3 scripts/rust-port/diff.py --suite sqlite --native` and unavailable
  `cargo nextest run -p symaira-core-sqlite` references with the existing
  `make rust-sqlite-contract` command and the actual `rust-sqlite-native` CI
  lane. Its SQL-006 status remains `in_progress` pending native and consumer
  gates.

The fresh source manifest is `testdata/rust-port/sqlite/candidate-source.json`
(SHA-256 `c130f8099d637d2cb4e5be23218bff877847824d2aa595c4577b1d6fbc35044e`,
68 source files). The Go oracle is pinned to
`f3d3eb79b9b1f31b4f973d2ed518a8292cedf588` (7 source files); the helper
provenance inventory has 22 files. Acceptance now recomputes both candidate
source hashes and Go oracle/helper hashes, validates the pinned isolation
contract, and rejects co-mutated reports/manifests. `typed_contract.py` treats
missing or malformed causes as failed controls rather than raising an
unvalidated attribute error.

### Fresh evidence and exact local results

| Step | Command | Result / counts | Absolute logs or artifact |
|---|---|---|---|
| Freeze | `python3 scripts/rust-port/sqlite/candidate.py --output testdata/rust-port/sqlite/candidate-source.json` | exit 0; base `82968b4fc9537daf62c2008331f5e5ce5d32b6c6`; 68 source files | `/private/tmp/sql006-freeze.S0whFe/stdout`, `/private/tmp/sql006-freeze.S0whFe/stderr` |
| Strict differential | `python3 scripts/rust-port/sqlite/diff.py --output testdata/rust-port/sqlite/differential-macos-bound-rust006-20260916-strict.json` | exit 1, intentional `partial`; 6 case IDs, 42 checked fields, 9 retained differences | report SHA-256 `8633ce9697de55677e2a0d692973329b45989572c899315b5277b1807dcc7bdf`; `target/sql006-run/logs/capture-strict-private-tmp.{stdout,stderr}` |
| Typed differential | `python3 scripts/rust-port/sqlite/diff.py --typed-errors --output testdata/rust-port/sqlite/differential-macos-bound-rust006-20260916.json` | exit 0, `passed`; 6 case IDs, 42 checked fields, 9 explicitly accepted differences, 0 remaining | report SHA-256 `8879ac65e7abbad13720d6d6a5c98430e69a1f89159be6a5eb694ccb5d4710b2`; `target/sql006-run/logs/capture-typed-private-tmp.{stdout,stderr}` |
| Required Python SQLite suite | `python3 -m unittest discover -s scripts/rust-port/sqlite -p 'test_*.py'` | exit 0; 69 tests | `target/sql006-run/logs/python-sqlite-post-provenance.{stdout,stderr}` |
| Required provenance suite | `python3 -m unittest discover -s scripts/rust-port -p 'test_rust_sqlite_provenance.py'` | exit 0; 1 test | `target/sql006-run/logs/python-provenance-post-repair.{stdout,stderr}` |
| Docs validator | `python3 docs/rust-port/validate.py` | exit 0; 124 contracts, 15 work items, 110 Go test patterns, 0 ready items | `target/sql006-run/logs/docs-validate-post-repair.{stdout,stderr}` |
| Whitespace check | `git diff --check` | exit 0 after final docs edit | `target/sql006-run/logs/git-diff-check-final.{stdout,stderr}` |
| Go oracle acceptance reference | `GOTOOLCHAIN=go1.26.6 go test -count=1 ./sqlitekit -run 'TestMigrate_ReadDirFailure|TestMigrate_VersionQueryFailure|TestMigrate_CreateTableFailure|TestMigrate_InMemory'` | exit 0; 4 selected Go tests | `/private/tmp/sql006-go-oracle.0J8l32/{stdout,stderr}` |
| Focused Make entrypoint | `make rust-sqlite-contract` | exit 0; 25 Rust integration tests + 1 doctest, 69 Python tests, 1 provenance test, typed report passed with 9 accepted/0 remaining | `target/sql006-run/logs/make-rust-sqlite-contract-rerun.{stdout,stderr}`; generated `target/sqlite-contract-report.json` is ignored |

Successful Go/Cargo runner invocations used these resolved paths (all `0700`):
`/Volumes/1TB_NVMe_SN850X/Dev/Symaira_Dev/Repos/symaira-corekit/.worktrees/rust-batch-20260916/target/sql006-run/{tmp,go-tmp,home,go-caches,cargo-home,cargo-target,logs}`
on `/Volumes/1TB_NVMe_SN850X`, with runtime `TMPDIR`
`/private/tmp/sql006-capture-20260916-final` (`0700`) because CoreFS rejects
the group-writable `/Volumes` ancestor. `dev-external --status` was PASS
(`mounted=true`, `verified_links=0`); `df -h` reported 43 GiB available on `/`
and 242 GiB on `/Volumes/1TB_NVMe_SN850X`. `PATH=/Users/daniel/sdk/go1.26.6/bin:$PATH`
was used only to discover the preinstalled pinned Go toolchain; runner
subprocesses had isolated HOME/XDG and explicit Go/Cargo caches.

The strict nonzero differential is retained as real evidence; no diagnostic
wording was normalized away. The named typed-error/consuming-close exception
is the only acceptance waiver. Existing historical failure/capture files were
left unchanged. The local run does not prove native Linux/macOS/Windows
runtime behavior, consumer integration/release, or value/cost gates.

### Read-only consumer demand and cost-gate proposal

The following was read from the current consumer checkouts; neither checkout
was edited and no real user store was opened.

| Consumer / current HEAD | Source and API demand | Exact SQLite dependency observed |
|---|---|---|
| Desktop `18373cd42eca63fbf74c7d6dc48027c031b3184d` | `crates/symdesk-index/src/lib.rs:271-281` calls `symaira_core_sqlite::open_with_existing_parent`, then the consumer's `migrate` and `backfill_norm_index`; the crate also uses `rusqlite::Connection` directly. | Root `Cargo.toml` pins CoreKit SQLite to git rev `62edd9903983d9369373565cc1e50da3fef43176`; `rusqlite = "=0.40.2"`, `default-features = false`, `bundled`; `Cargo.lock` resolves `0.40.2`. |
| EraseMe `85cf1223d90879453f10eb0a9afccbc335fec323` | `crates/symeraseme-core/src/storage/mod.rs:23-41` owns `open`, parent creation, `Connection::open`, 5-second `busy_timeout`, `foreign_keys` and WAL; `storage/store.rs:17-73` owns `Store::open`, `user_version`, schema initialization and `SCHEMA_VERSION = 2`. | Root workspace `Cargo.toml` uses `rusqlite = "0.37"` with `backup` and `bundled`; `Cargo.lock` resolves `0.37.0`. This `Connection`/schema lifecycle is not interchangeable with Desktop's API. |

Concrete proposal, not executed here: after a separately approved candidate
pin in disposable consumer worktrees, run these existing commands without
editing this repository:

```sh
# symaira-desktop
cargo test --manifest-path Cargo.toml -p symdesk-index --locked
cargo build --release --manifest-path Cargo.toml -p symdesk-index --locked

# symaira-eraseme
cargo test --manifest-path Cargo.toml -p symeraseme-core --locked
cargo build --release --manifest-path Cargo.toml -p symeraseme-core --locked
```

The value gate is four green consumer commands plus standalone-first behavior
and schema/API compatibility. The cost gate compares clean and warm release
builds and release artifact sizes against each consumer's prior exact pin, with
the existing 110-% regression limit. Those comparisons, native runs, released
consumer pins and release evidence remain open; no benchmark was run in this
checkpoint.

## Native macOS gate — 2026-09-17

The exact candidate was rechecked on the real macOS arm64 host without changing the SQL-006 implementation or resetting the pre-existing WIP. The checked-out branch is `migration/rust-batch-20260916` at `82968b4fc9537daf62c2008331f5e5ce5d32b6c6`; the Go oracle remains `f3d3eb79b9b1f31b4f973d2ed518a8292cedf588`. The current Makefile has no `rust-sqlite-native` target; the native path is the CI-equivalent command sequence in `.github/workflows/ci.yml` (`cargo test`, package Clippy, Python SQLite tests, typed differential). Status snapshot: before and after were both 17 tracked modified files plus 2 untracked non-ignored differential artifacts; the final HEAD tree is `d140d69bdb170c7ac44da8854be8fa3a91518bc8`, and the final non-ledger tracked diff SHA-256 is `291f0f1f199a0aa39a88c3002aa85132808b606ab589cc50e8956e4aab8eecbe`.

The first all-NVMe runtime attempt intentionally exercised the macOS path contract and failed before acceptance: `cargo test` exit 101, with 4 of 6 `contracts.rs` tests passing and 2 failing on `Directory(InsecureDirectory(...))` because the NVMe volume ancestor is mode `0775`. This is retained at `target/sql006-native-macos-20260917/logs/cargo-test.stderr`; it was not normalized away. The successful rerun kept HOME/XDG/Go/Cargo caches and `CARGO_TARGET_DIR` in the mode-0700 NVMe run root, while using mode-0700 `/private/tmp/sql006-native-macos-20260917` for runtime temp files, the secure macOS location required by CoreKit's existing parent-security contract.

| Check | Result | Evidence |
|---|---|---|
| Cargo SQLite package tests | exit 0; 25 integration tests + 1 doctest | `target/sql006-native-macos-20260917/logs/cargo-test-private-tmp.stdout` / `.stderr` |
| Cargo Clippy package gate | exit 0; `--all-targets --all-features --locked -- -D warnings` | `target/sql006-native-macos-20260917/logs/cargo-clippy.stdout` / `.stderr` |
| Python SQLite helper suite | exit 0; 69 tests | `target/sql006-native-macos-20260917/logs/python-sqlite.stderr` |
| SQLite provenance suite | exit 0; 1 test | `target/sql006-native-macos-20260917/logs/python-provenance.stderr` |
| Go SQL-006 oracle focus | exit 0; 4 selected tests | `target/sql006-native-macos-20260917/logs/go-sqlite-focused.stdout` / `.stderr` |
| Typed Go↔Rust differential | exit 0; 6 cases, 42 fields, 9 explicitly accepted differences, 0 remaining | `target/sql006-native-macos-20260917/sqlite-native-report.json`, SHA-256 `036f6333c72fc6195b58c3ff49f34739839c36f09914face9a38fc9c3eddd30a` |
| Formatting / whitespace | `cargo fmt --all --check` and `git diff --check`, both exit 0 | `target/sql006-native-macos-20260917/logs/cargo-fmt.stdout`, `git-diff-check.stdout` |
| Documentation validator | exit 0 | `target/sql006-native-macos-20260917/logs/docs-validate.stdout` |

The differential report records native identity `darwin/arm64`, candidate base and revision equal to `82968b4fc9537daf62c2008331f5e5ce5d32b6c6`, and measured busy contention of 5.062894375 seconds. `dev-external --status` was PASS before each heavy run (`mounted=true`); the NVMe run root, HOME/XDG roots, caches and runtime exception were mode 0700. No real stores or secrets were accessed.

This closes only the local native macOS gate for the dirty candidate; SQL-006/RUST-006 remains `in_progress`. Native Linux and Windows runtime lanes remain open and cannot be inferred from this host. Consumer pins/smokes, Value, Cost, RUST-006 promotion and RUST-014/015 release/consumer gates remain open. No consumer, release, PR, push, cutover, Go deletion, benchmark or `Arbeitsstand.md` change was made.

## Post-squash source-bound capture — 2026-09-17

The squash merge of #284 preserved the candidate source bytes but removed the
branch-only capture revision from `main`. The existing validator correctly
rejected that report in all three SQLite-native CI lanes before the live
differential ran. The old capture is retained as historical evidence; it was
not rewritten.

A fresh branch from `main` at `2f995ca721f87d525324c0241835a588d6421966`
now records that reachable revision before its fixture changes are committed.
The regenerated source manifest has 68 files and SHA-256
`b1486fa30b58154f820d73e2b8496b12d78181e50113dc04613ae786f8de6774`.
The new native macOS arm64 report is
`testdata/rust-port/sqlite/differential-macos-bound-rust006-post-squash-20260917.json`
(SHA-256 `8e3d6b0c099e3ba83ae9699ca6cac29c69498079881f3e6533a173aa86861641`):
six case IDs, 42 checked fields, zero unresolved differences and nine explicit
typed-contract differences.

The CI-equivalent package checks passed locally: 25 Rust integration tests plus
one doctest, package Clippy with `-D warnings`, 71 SQLite Python tests and one
provenance test. The `dev-external` preflight reported only an unrelated missing
Brain `target` link; the capture used its explicit target directory on the
mounted NVMe and did not modify Brain. This restores a valid source-bound
fixture for review and a fresh CoreKit CI run only. It does not complete a
cross-platform native gate, consumer adoption, cost/value evidence, RUST-006,
release work or a Go cutover.

## SQL-006 cost-gate provenance refresh — 2026-09-17

SQL-006 adds `cost_gate.py` and `test_cost_gate.py` to the SQLite helper tree,
which the source-bound contract deliberately freezes. The active manifest was
therefore refreshed from 68 to 70 files (SHA-256
`f06e39bde1d9f5dcc01d3244f72ee003828e151c3f47a57479f3b565a76511a5`),
and the active post-squash capture (SHA-256
`238f390580e20e6ec5c7075cce782a9aaab891e773f4920727440bdbc925410d`)
was recaptured at reachable candidate revision
`8a091aebcd1179786738647aa1cced5a82152f4b`. Its Go oracle now binds
24 helper files; the typed differential remains six cases, 42 checked fields,
nine explicit differences and zero unresolved differences. Older historical
captures remain unchanged.

The synthetic Windows self-check no longer treats unavailable POSIX mode bits
as a privacy proof; a non-test SQL-006 validation still fails closed there.
Resolved runtime aliases are also compared canonically, so macOS `/var` aliases
and Windows path normalization cannot reject the portable self-test. The real
frozen runtime remains the private macOS NVMe mount. The affected Rust package
tests, Clippy, 73 SQLite Python controls, provenance control and a fresh typed
live differential all passed on that mount. This fixes only the CI provenance
and portable self-test path; it does not rerun or change the 80-build cost
evidence, its thresholds, promotion, release or Go cutover.
