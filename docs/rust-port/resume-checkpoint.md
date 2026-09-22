# Resume checkpoint — SQLite and MCP-config slices complete, RUST-014/015 open

## Active checkpoint — RUST-015 local reviews reconciled (2026-09-23)

- Mode/status: execute / running; local evidence reviews reconciled, migration
  **not complete**. Checkpoint integration is the current gate.
  Integrated base `a3b1b24b8de779fb4c5710544b98250f1bc8e1ae`; coordinator owns
  `migration/rust015-runtime-capture` in `.worktrees/rust015-consumer-release`.
  Repository WIP is this checkpoint only; consumer checkouts remain read-only.
- Verified: Vault source `5851a5e8c63fcd34a083b8e28930b47158d1dee8`, local
  native macOS arm64 Rust/Go builds; 11 runtime cases and 26 encrypted-switchback
  cases passed, with seven complete semantic JSON comparisons. Go reads both
  an existing entry updated by Rust and a new Rust entry after the real local
  executable switchback; it also reads a second Rust-initialized test vault.
  These are synthetic passphrase/memory-keyring cases, not a production rollout.
- Frozen Vault anchor: `vault-5851a5e/evidence-index.json`, SHA-256
  `d467ffe425834556cc6dbf3db327ab488e2fe534e063e332b9b20f60fb0e663a`.
  Coordinator verified all 327 regular files, three declared Git-helper links,
  and all 1715 source entries against an independent `git archive`. Artifact
  paths resolve under the external `corekit-rust015-runtime` workspace below.
- Review: Vault `deleg_2754d646` / `sa-0-1d313b1d` APPROVE is reconciled for
  limited local claims only. After delivery, the coordinator rechecked the exact
  51882-byte index, all indexed files/links, the source archive, exact executed
  case IDs, seven comparisons and the preserved final updated state.
  Receipt: `vault-5851a5e/review-deleg_2754d646.md` beside the frozen index.
  Browse review `deleg_e14b7382` / `sa-0-84da9b44` is reconciled: APPROVE for
  evidence validity only; the genuine flow-list parity failure is not waived.
- Async: no evidence review remains pending. Vault Rust build
  `proc_9771a4765e26` is consumed. Go build
  `proc_c4b4201c90d4` has a verified successful final report and executed artifact;
  a later process notice is duplicate evidence, not a reason to rebuild.
- Next: integrate this documentation-only capture checkpoint after its focused
  validation and exact-head CI, then reconcile the consumer-owned prerequisites
  before any new capture. Existing stop-checkpoint PR #313 is older overlapping
  documentation, not release authorization; its branch is preserved unchanged.
  Brain #662 and EraseMe #1035 remain consumer implementation defects, not
  environmental walls. RUST-014/015 and consumer release anchors stay unchanged:
  released-artifact provenance, required native targets and release-bound recovery
  remain open. No tags, publication, installed cutover or Go removal is authorized.

## Source-bound capture details

- Capture base (historical, not the current execution status):
  `a3b1b24b8de779fb4c5710544b98250f1bc8e1ae` (PR #320 merged; #319 closed).
  The report-hash verifier is integrated; it does not prove Rust execution.
- Item/owner: RUST-015 prerequisite, migration coordinator; branch
  `migration/rust015-runtime-capture`, owned isolated worktree
  `.worktrees/rust015-consumer-release`. Only this checkpoint is modified in
  the repository; no production consumer record, tag or artifact is changed.
- Integrated evidence: PR #320 head `dd7208af5cbd29b3ac7a59848c4eefb2fc055f2b`,
  independent review `deleg_27a7df23` APPROVE; all four reviewed hashes matched.
  CI `35782954230`, attempt 1, all 36 jobs passed; `proc_87ecdc86193f` exited 0.
  Exact-head CI, review threads, merged PR and closed issue were read back.
  Local `make rust-release-contract` (`proc_7e3d7712bf70`, exit 0) passed
  53 consumer tests, 14 release tests, pin regression and packaging.
  SemVer compatibility remains unverified: unpublished crates were skipped.
- Previous slice: PR #318 integrated at
  `d31603ff042392fd8cee2dd0284dd2667123d703`; #316/#317 closed after both reviews,
  the release wrapper and all 36 jobs in CI `35780231128` passed at
  `11e4f6d189108cf8ff48515c622ecf29baf49c2a`.
- Active capture: immutable EraseMe source
  `8986a3db3d60d37b89368d37e15f1e98c60672f2`, exported with the existing
  `bench.archive_checkout` origin check. The local script reuses
  `bench.isolated_env`, freezes the complete archive inventory before build,
  checks explicit Cargo workspace/package/target paths, and records toolchain,
  raw command results and artifact hash; source inventory must still match
  afterward. No consumer checkout or installed executable is modified.
- Verified build: `proc_4d1475a21809` exited 0; Rust 1.98.0, clean locked release
  build, 2052 frozen source files unchanged before/after. Native macOS arm64
  artifact SHA-256 `7599f33f4f0c31dbacbfcde2cdcd62359a41e077530aa1fa6a4d71f8e75385de`.
  The failing-command wrapper control retained exit 1 and raw logs.
- Evidence root: `/Volumes/1TB_NVMe_SN850X/AI/Hermes Workspace/corekit-rust015-runtime/eraseme-8986a3d`.
  Frozen `evidence-index.json` binds 87 files, SHA-256
  `ef6e9f2e23edf26aebddd55149f5c060ccc9e90deb78182e638e6cc031902d4f`.
  It includes raw failures and the exact producer versions, not only passing runs.
- Runtime: `runtime-002/runtime.json`, SHA-256
  `5f736b1bd9df69ed0eacdfd548cccfc364930ca25af071bbc7124c44fdc80780`.
  Three real CLI cases (`version --json`, `status --output json`,
  `requests list --output json`) passed on three explicitly synthetic requests.
  Four sandbox controls prove denied network, child exec, operator-home and
  repository reads; empty PATH and isolated HOME/XDG/data were used.
- Binary-only rollback FAILED: Rust changes the copied fixture's user_version
  from 1 to 2; the retained Go artifact refuses schema 2 (exit 1), even though
  its version command succeeds. `rollback-001/rollback.json` SHA-256
  `0e107f2f095423475250c49b81be4bce1e1b0757c8deabd675a913e42d9ecae8`.
  The Go artifact says `dev` and has no VCS build metadata; its filename is not
  release identity. Filed `danieljustus/symaira-eraseme#1035`; also notified
  that repository's release-preparation PR #1032 and CoreKit #249.
- Backup/restore rehearsal passed: `restore-002/restore.json`, SHA-256
  `6715316490322d0ef747fb61259edfc328ea3d28f0cbff0f0a885e5ee95c5bc5`.
  Four executed steps: Go baseline (schema 1), Rust (2), expected Go rejection
  (2), actual pre-upgrade SQLite backup + Go executable restore (1). All nine
  table schemas/rows and nonempty request readback equal the Go baseline.
  No post-upgrade writes or encrypted store were tested: later-write retention
  and published rollback remain unproven. The binary-only failure is not waived.
- EraseMe review reconciled: `deleg_5f03ee20` / `sa-0-7d2e4659` APPROVE for
  the exact frozen index above and limited local claims only. The reviewer
  independently compared all 2052 archive entries and 87 evidence files;
  coordinator readback confirmed the unchanged index/files, source manifests,
  executable digest and passed/failed/passed runtime/rollback/restore outcomes.
  Receipt: `eraseme-8986a3d/review-deleg_5f03ee20.md` beside the frozen index.
  This approval does not waive the binary-only failure or promote release gates.
- Desktop build `proc_8dc1d873ad18` consumed: exit 0, immutable source
  `4c0c246bbab80d105987caf21ca16cbbdda59c89`, 6799 source files unchanged.
  Local Rust artifact SHA-256
  `caf1975651d877b93124ea174578325318a752d4d1c2f31da4287534f29645e0`.
  Evidence root is `corekit-rust015-runtime/desktop-4c0c246` in the same
  Hermes Workspace. Frozen `evidence-index.json` binds 91 files, SHA-256
  `40576a2de55fee31c82cde119cfff648b4d8b070317b751566c67fc0efa6a3df`.
- Desktop runtime: `runtime-002/runtime.json`, SHA-256
  `93442e014af91417329a27a323a1a5209129e269c2c487143a0b1c6f07995a22`.
  Four exact cases passed: version, nonempty document listing, matching search
  and absent-term search. Two synthetic Markdown documents stay byte-identical;
  the native sidecar is created and passes SQLite integrity_check. Four sandbox
  denial controls passed. `runtime-001` preserves an incorrect harness
  expectation: explicit SYMDESK_SIDECAR intentionally suppresses metadata.json.
  The corrected run tests that actual branch; no product behavior was changed.
- Desktop local rollback: `rollback-001/rollback.json`, SHA-256
  `4243facc00ecf193b3767f0240250e23afe318530e764c3a010c0f1bfdd45e41`.
  Go baseline -> Rust -> restored Go executed nine commands at the same active
  executable path and synthetic vault/index. Final Go JSON readback equals the
  baseline; document bytes and SQLite integrity survive. The retained Go binary
  reports `(devel)` without VCS metadata: no public-release identity, signing,
  installed cutover, encrypted state or post-upgrade user edits are established.
- Desktop review reconciled: `deleg_4164cec6` / `sa-0-25516407` APPROVE for
  the frozen local capture only. Coordinator readback verified all 91 indexed
  files, 6799 source entries, 13 raw command records, sidecar/artifact hashes and
  byte-identical Go baseline/restored streams. Restored Go artifact SHA-256:
  `3e027c16488d030f0ce76e99ba6152a235c514d1ac90246b2d479c72da66ac7d`.
  Receipt: `desktop-4c0c246/review-deleg_4164cec6.md`. This does not establish
  public release provenance, complete API parity or post-upgrade-write recovery;
  no consumer release manifest evidence is promoted.
- Vault Rust build `proc_9771a4765e26` consumed: exit 0, immutable source
  `5851a5e8c63fcd34a083b8e28930b47158d1dee8`, package `symvault-cli`, binary
  `symvault`, artifact root `corekit-rust015-runtime/vault-5851a5e`.
  Locked Rust 1.98.0, 1715 source entries unchanged, artifact SHA-256
  `a6477bbc678c0252f34cb51c94246a3c7869e8670c8933c803e586d3133df40d`.
- Vault same-source Go reference rebuilt by `build_vault_go.py` /
  `proc_c4b4201c90d4`: effective Go 1.26.6, CGO disabled, read-only module
  resolution, final build exit 0. Artifact SHA-256
  `03f1eb95dd49625ae000eddfb8e3f528dc106651f84bed3c54b53077c3e9885f`.
  It does not reconstruct or authenticate the missing historical released binary.
- Vault runtime: `runtime-002/runtime.json`, SHA-256
  `76c88261e85d1b3a96984563b17b8a1664438e3ac0fd5d894819793a35c46a22`.
  Eleven CLI cases passed, including actual encrypted init/add/get/list and
  wrong-passphrase, absent-query and duplicate-add rejection. Captured file
  bytes/modes remain unchanged by those rejected operations. Memory-only auth
  status was read back. The sandbox denies network, Mach lookups, operator home
  and repository reads, and child executables except the tested binary and the
  exact real Git helper needed by init/auto-commit. Four denial controls passed.
  No real OS keychain, Touch ID or operator credentials were exercised.
  `runtime-001` retains the harness's incorrect missing-field diagnostic
  expectation; the actual native fallback reports an entry-path lookup failure.
- Vault encrypted switchback: `comparison-001/comparison.json`, SHA-256
  `586fe3b9b18909173f44149f668c019018658a75228b8bc4ba0c6a31defa3df2`.
  Twenty-six executed cases and seven complete JSON comparisons passed: Go
  initializes and writes, Rust decrypts, updates the old entry and adds another,
  then restored Go reads both later writes. Identity/config bytes are preserved.
  A second independently initialized Rust vault/identity is also read by Go.
  The active executable is actually replaced Go -> Rust -> Go; no pre-upgrade
  backup is substituted for the updated store. A wrong-passphrase rejection
  under restored Go preserves captured files. Compiler/runtime producers,
  failures and raw streams are retained. Independent review `deleg_2754d646`
  APPROVE is reconciled against the unchanged frozen anchor. The reviewer
  independently verified 327 regular files, three helper links, all 1715 source
  entries against Git archive, build identities, exact case IDs and seven complete
  JSON comparisons. Coordinator readback confirmed those integrity anchors,
  executed case counts, Go/Rust/Go switching and preserved post-Rust state.
  Receipt: `vault-5851a5e/review-deleg_2754d646.md`. No OS-keyring/Touch-ID,
  crash/concurrency/recipient-revocation, full API-parity or production rollback
  claim is made; excluded compiler/download caches remain outside the index.
  CoreKit #249 was updated and read back (`issuecomment-5785373819`).
- Brain/Browse build `proc_08cd8edb54a5` consumed: exit 0, immutable source
  `a92385d2deecc08d1fd96869908b81b7abd355fe`, nested workspace `browse/`,
  package `symbrowse-cli`, binary `symbrowse`; 2318 archive entries and effective
  Darwin/arm64 build verified. Local artifact SHA-256
  `c4e2e3164d624a6f3e03c2682e9ce389bc13ccb058997534804bbb71b2dbd168`.
  Root: `corekit-rust015-runtime/brain-browse-a92385d`. The nested workspace,
  not Brain's root CLI workspace, owns the CoreKit Rust dependency.
- Brain/Browse `runtime-001/runtime.json` SHA-256
  `64be0014bd5c1f2bcff228e8d49ad57151e33384f50f50702b073de43e3f89fb`:
  four native cases passed (version, flow validate, nonempty flow discovery,
  invalid-flow rejection with exit 2). The input derives from the checked-in
  workflow fixture; its five steps are parsed, **not executed in a browser**.
  Input files and isolated HOME/XDG state remain unchanged. Four sandbox denial
  controls passed; exact build/runtime producers are retained beside reports.
- Browse Go reference `proc_74cf88465136` consumed: exit 0, same archived
  source, effective Go 1.26.6, CGO disabled, read-only module resolution.
  Artifact SHA-256 `00f3361724ceb530f4a2fd3067de11a46db31efaf9862bc9fb21b092177bab7d`.
  It is a locally rebuilt reference, not a published historical fallback.
- Browse comparison executed and FAILED as intended on a real divergence:
  `comparison-001/comparison.json` SHA-256
  `7df00ff419a60bec477e292a90f2c2fbf209c0128cbf5ceac7648885e596d4d1`,
  producer exit 1 / `parity_failed`. Go emits `data.flows`, Rust emits an array
  at `data`; contained entries are equal. The complete JSON comparator retains
  the mismatch. Filed and read back `danieljustus/symaira-brain#662`; this is
  unresolved consumer implementation work, not an environmental blocker.
  A separate same-source Go -> Rust -> Go switch executed six commands and
  restored byte-identical Go output. That does not waive the parity failure.
- Brain/Browse frozen `evidence-index.json` binds 75 files, SHA-256
  `c9d2f1c262f5e93a9bf88ba9390876f38e63281b031690c0fe738e226c7a0e3a`.
  Review `deleg_e14b7382` / `sa-0-84da9b44` APPROVE is reconciled for positive
  and negative evidence validity only, not product parity or rollback readiness.
  The reviewer verified all 2318 source entries against an independent Git
  archive, all 75 indexed files, four runtime cases and six switch commands.
  Coordinator readback confirmed the unchanged frozen index/files, source tree,
  report hashes, runtime case IDs/exits and the still-failed full JSON comparison.
  Receipt: `brain-browse-a92385d/review-deleg_e14b7382.md`. Both compiler
  producers, raw command records, input files and comparison producer are retained.
  CoreKit #249 was updated and read back (`issuecomment-5785064063`).
- Reviews complete: all four frozen captures have independent evidence-validity
  approval and coordinator readback; none is public-release or cutover approval.
  Keep the consumer-owned #662 mismatch and EraseMe #1035 rollback failure
  visible. Missing local adapters remain work; all consumer checkouts stay
  read-only, no installed program is replaced, and RUST-015 stays non-complete.
- Probe hygiene: SQLite `mode=ro` created `-wal`/`-shm` beside the tracked
  fixture. Both known probe sidecars were moved, not deleted, to
  `corekit-rust015-runtime/read-only-probe-sidecars`; the fixture still matches
  its Git bytes and the consumer checkout is clean. Further static fixture
  inspection must use `mode=ro&immutable=1` or a disposable copy.
  The first restore correctly stopped on a nonempty WAL: Python connection
  context managers do not close connections. Explicit `contextlib.closing`
  fixed the harness without dropping WAL or weakening schema checks; both
  producer versions and the failed report remain in the frozen index.
- Residuals: consumer implementation fixes, release-bound safe rollback,
  broader post-upgrade-write/encrypted-state recovery, public release readback and
  Vault's missing historical standalone artifact are unfinished (#249 open).
  Local capture/adapters are work, not external walls. RUST-014/015 remain
  non-complete. Registry/publication requires separate authorization; no release,
  Go removal or product cutover is authorized.

## Previously integrated state

Owner: migration coordinator. `RUST-006` is
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

`RUST-015` stays `blocked`. `consumer-rollout-findings.md` splits the verifier
findings into four classes; the stale-`rust.status` class is fixed as of
2026-09-21, and the class-3 open question (remove the dev-storage symlinks or
give the gate a generated-tree rule) is decided the same day in favour of the
gate: `_check_checkout_snapshot` prunes `FORBIDDEN_PATH_PARTS` before the
symlink check, so a `target` tree is excluded whether it is a real directory or
a symlink. Tracked paths are still resolved and rejected, and a non-generated
symlink directory is still a finding. The workspace run moved 22 → 20 findings;
the remaining class-3 findings (brain 3, eraseme 2) were consumer-side. Class 3
closed 2026-09-22: symaira-brain PR #651 (merged `a7002cc1`, closes brain#635)
untracked the three `.cursor`/`.phase0-evidence` paths — `git ls-tree` at the
merged revision lists none — and `.agents`/`.windsurf` joined
`FORBIDDEN_PATH_PARTS` in corekit PR #310 (merged `df8659e3`) after `readlink`
proved the eraseme links resolve *inside* the checkout to the tracked `skills/`
tree (the earlier "points outside" premise in `consumer-rollout-findings.md`
is corrected there). The 2026-09-22 run reports 17 findings (5 stale
`checkout_commit`, 10 missing evidence, 2 transient `checkout.dirty`) and zero
`checkout.path`. Evidence: 50 tests in `port/consumer` — exclusion, a
non-forbidden-symlink negative control and tracked-path rejection under the new
names.

Earlier the same day: brain, browse and desktop now record their real Git adoption
(revision `d382b861`, `symaira-core-version`, `=0.0.0`) and the verifier reads
brain's nested `browse/` Cargo workspace through the record's new `cargo_root`
field. Remaining: stale `checkout_commit` records (deliberately re-pinned at
the evidence snapshot) and the missing `evidence.standalone`/`rollback` for all
four records; consumer checkout hygiene closed 2026-09-22 (see above). Tracked
in corekit#249; eraseme#993, desktop#984, vault#1080 and symaira-brain#635 are
closed. `danieljustus/symaira-browse` was removed from `docs/consumers.json`
the same day: the repository is gone from GitHub and Browse lives on as the
optional module `symaira-brain/browse/` (product-boundaries.md, confirmed by
the user) — gate scope is four released consumers.

`RUST-014` stays `in_progress`. `python3 port/release/verify.py --dry-run` passes
and the release/consumer governance tests pass, but registry evidence does not
exist and the crates stay `publish = false`. `cargo semver-checks check-release`
must not be counted as API-compatibility evidence — it skips every candidate
(`Skipping <crate> v0.0.0 (current)`) because nothing is published, and the
dry-run now prints `semver baseline: none … API compatibility stays unverified`.
`release-manifest.md` fixes the sequencing: no publication before the full
migration, consumer rollout and registry evidence are complete, so no
publication decision is available yet.

## Consumer-record refresh (2026-09-21)

`docs/consumers.json` records for `symaira-brain`, `symaira-browse` and
`symaira-desktop` said `rust.status: not_adopted` while their tracked Cargo
manifests and locks pin `symaira-core-version` from CoreKit git revision
`d382b861` (`v0.17.0-20-gd382b861`). The refresh records the verified facts and
adds `cargo_root` support to `port/consumer/verify.py` so brain's nested
`browse/` Cargo workspace is read where the pin actually lives; three
regression tests cover the nested lock, the missing-`cargo_root` negative
control and the path-escape checks.

Evidence: `python3 -m unittest discover -s port/consumer -p 'test_*.py'` — 47
tests pass. The verifier run against the workspace moved from 25 to 22
findings: all nine `rust.not_adopted.present` findings are gone, no `rust.*`
finding replaced them, and the remaining findings are the open classes in
`consumer-rollout-findings.md`. Consumer checkouts move constantly (several
branch switches during the run), so `checkout.commit` and `checkout.path`
messages are a snapshot, not a stable list.

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
  `39cc0a4def6d3705dcd91e410cd07a388440572e75cc580f951caa078201c257`
  (74 recorded files, 39 enforced).
- `testdata/rust-port/sqlite/differential-macos-refreeze-20260920T175852Z.json`,
  SHA-256 `5f4903b0dd7dad967600b3891e101041c72146019107f48f6b4381c5a4cf7597`,
  typed verdict `passed` at revision `3b9ed28…` (regenerated on `main` after the
  squash merge and again for the merge-survival guard, see below), native
  darwin/arm64, six cases, 42 checked fields, nine explicitly accepted
  differences, zero unresolved.
- 79 SQLite acceptance tests and the provenance test pass against the re-frozen
  pair; the five files that name the current capture were repointed in the same
  commit.

**Merge-survival correction (#299, guard from #300).** The capture was first
generated inside the `migration/rust-010-mcpcfg` worktree, so it recorded that
branch commit as `candidate_revision`. Squash-merging #298 destroyed the commit
and every ancestry control failed on `main` at `b529bde` while the branch CI had
been green. Regenerated with HEAD on `main` under the *same* capture file name
and re-run through the full lineage.

The generator now detects the situation instead of relying on review:
`candidate.merge_survival()` reports whether the recorded revision is reachable
from the base branch, `diff.py` prints an explicit warning when it is not, and
`test_acceptance.test_current_capture_revision_survives_a_squash_merge` asserts
it — so PR CI fails *before* the merge rather than `main` failing after it.

Verification of that change: 79 SQLite acceptance tests and 1 provenance test
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
decision plus registry evidence; `RUST-015` needs classes 1 and 4 in
`consumer-rollout-findings.md` closed (classes 2 and 3 are fixed; class 1 is
deliberately re-pinned at the evidence snapshot). A further slice requires new
two-consumer demand evidence in `demand-assessment.md`. No release, publication,
Go removal or product cutover is authorized here.
