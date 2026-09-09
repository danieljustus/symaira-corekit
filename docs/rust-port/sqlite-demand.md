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
The frozen `candidate-source.json` and fresh `differential-macos-bound.json`
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
candidate-source manifest was regenerated for this change. The fresh macOS arm64
capture retained in `differential-macos-bound.json` has SHA-256
`fd80b18fdbe3757d64fca9b375fcbaa34f337e51988991eca47033280d1c248d`; its
six-group typed differential passed with Go `go1.26.6`, and it measured the
Rust busy wait at 5.200130959 seconds. This is a real local capture, not a
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
