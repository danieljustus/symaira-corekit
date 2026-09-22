# RUST-015 released-consumer gate: what actually blocks it

`python3 port/consumer/verify.py --released-consumers` returns `status: blocked`
for CoreKit. The findings are not one missing artefact; they fall into four
classes, and only class 4 is the genuine "no released consumer yet" work.
Classes 2 and 3 are closed (2026-09-21 and 2026-09-22); classes 1 and 4
remain open with the reasons below.

Run 2026-09-21 (corekit `main` `53aee98` with the record refresh applied),
consumers at their then-current heads: brain `46d2c1b5`, browse `c9ab83cc`,
desktop `4ea77f3c`, eraseme `91343c6f`, vault `a28b6a09`. Consumer checkouts
are actively moving, so the per-repo counts differ between runs; the classes
do not.

Run 2026-09-22 (corekit `main` `df8659e3`): 17 findings — 5 stale
`checkout_commit`, 10 missing evidence and 2 transient `checkout.dirty`
(brain and vault hold another session's uncommitted work; a working-tree
state, not a committed-state class). Zero `checkout.path` findings remain.

| Class | Findings | Where |
| --- | --- | --- |
| 1 — stale `checkout_commit` | 5 | all five records |
| 2 — wrong `rust.status` | 0 — fixed | — |
| 3 — consumer checkout hygiene | 0 — fixed 2026-09-22 | — |
| 4 — missing standalone/rollback evidence | 10 | all five consumers |

## 1. Stale `checkout_commit` — deliberately re-pinned at closure, not now

Every consumer moved on; the records still name the checkouts of an earlier
verification. Refreshing them is not forgotten bookkeeping — it is the first
step of closing class 4, because the recorded commit is the snapshot the gate
reads back: the standalone/rollback reports must be committed *in the consumer*
at exactly that commit.

Consumers are mid-work: during the 2026-09-21 run their checkouts switched
branches repeatedly (brain `migration/rust-continue-20260920` → `main` →
`docs/migration-merge-record` → `fix/632-guard-scan-pin`; vault
`fix/migrate-pseudonymize-data-loss` → `fix/port-pins-survive-squash` →
`main`). Pinning a moving feature-branch tip as an "immutable consumer
snapshot" would record a commit that is not a release snapshot and is stale
within hours. The re-pin happens when the evidence exists, against each
consumer's released commit.

## 2. Wrong `rust.status` — fixed 2026-09-21

The records for brain, browse and desktop said `rust.status: not_adopted` while
their tracked Cargo manifests and locks pin `symaira-core-version` from the
CoreKit git revision `d382b861` (`v0.17.0-20-gd382b861`, version `=0.0.0`). The
refresh records what the checkouts contain:

- `symaira-brain` pins from a nested Cargo workspace (`browse/`), so the record
  uses the verifier's new explicit `cargo_root` field: workspace dependency
  resolution and the lockfile are read from `browse/`, while every other check
  still binds the checkout root. Without the field the verifier would read the
  brain root lockfile, which does not contain the pin, and report a false
  `rust.lock.unique` finding.
- `symaira-browse` (`Cargo.toml`, `crates/symbrowse-protocol/Cargo.toml`) and
  `symaira-desktop` (`Cargo.toml`, `crates/symdesk-core/Cargo.toml`) pin from
  their root workspaces.
- Each refreshed record carries the release the pin descends from (`v0.17.0`)
  and evidence `missing` — nothing is claimed that the gate does not read back.

Effect: the nine `rust.not_adopted.present` findings are gone and the gate now
evaluates the real pins.

## 3. Consumer checkout hygiene — closed 2026-09-22

Snapshot of the 2026-09-21 run, *before* the generated-tree rule below:

- `symaira-brain` (4): a `target` symlink directory plus tracked paths under
  `.cursor/` (`.cursor/rules/symbrain.mdc`, `cmd/symbrain/.cursor/rules/symbrain.mdc`)
  and `.phase0-evidence/PHASE0_REPORT.md` — filed as
  [symaira-brain#635](https://github.com/danieljustus/symaira-brain/issues/635).
- `symaira-eraseme` (2): symlinked skill directories
  (`.agents/skills/symaira-eraseme`, `.windsurf/skills/symaira-eraseme`) —
  [eraseme#993](https://github.com/danieljustus/symaira-eraseme/issues/993).
- `symaira-vault` (1): a `target` symlink directory; the `.agentsroom` findings
  of the 2026-09-20 run are gone —
  [vault#1080](https://github.com/danieljustus/symaira-vault/issues/1080) tracks
  the `.gitignore` defect behind the symlink handling.
- `symaira-desktop`: none this run; the 2026-09-20 `.build` findings are gone —
  [desktop#984](https://github.com/danieljustus/symaira-desktop/issues/984).

### Decided 2026-09-21: the gate gains the generated-tree rule

`target` symlink directories are this machine's dev-storage layout
(`dev-external` symlinks build trees onto the NVMe), not tracked consumer
source. The open question — remove the symlinks on the verifying checkout, or
give the gate an explicit generated-tree rule — is decided in favour of the
gate, because the checkout layout is not the consumer's and would have to be
un-done on every verifying machine.

The walk already pruned `FORBIDDEN_PATH_PARTS` (`target`, `.cursor`, `.build`,
`node_modules`, …) for real directories; the symlink check simply ran first, so
the same tree produced a finding when it was a symlink. `_check_checkout_snapshot`
now prunes the forbidden name first and rejects symlink directories only outside
that set. The security boundary is unchanged: every *tracked* path is still
resolved and rejected if it is a symlink or contains a forbidden component, and
a non-generated symlink directory (e.g. an ignored `rustlink` pointing at a
hidden Cargo source tree) is still a finding — both covered by existing tests,
plus `test_symlinked_generated_tree_is_excluded_like_a_real_one`.

Effect on the 2026-09-21 run: 22 → 20 findings. The three `target` findings are
gone. What remained after that rule was:

- `symaira-brain` (3): tracked files under forbidden tooling paths
  (`.cursor/rules/symbrain.mdc`, `cmd/symbrain/.cursor/rules/symbrain.mdc`,
  `.phase0-evidence/PHASE0_REPORT.md`) — the consumer tracks source-shaped files
  in trees the gate treats as generated. Consumer-side, symaira-brain#635.
- `symaira-eraseme` (2): the symlink directories
  `.agents/skills/symaira-eraseme` and `.windsurf/skills/symaira-eraseme`.

### Closed 2026-09-22 — and one correction

**Correction:** the eraseme links do *not* point outside the checkout. The
earlier claim in this document ("symlink out of the checkout into an external
skills source … they point at content outside the pinned snapshot") was wrong:
`readlink` shows `../../skills`, which resolves to `<checkout>/skills`, a
tracked in-repo directory, and both links are untracked and gitignored
(eraseme#998). The decision not to treat them as generated trees rested on
that false premise. They are agent-tooling links created by
`scripts/setup-agents.sh` — the same script that creates the already-excluded
`.claude`/`.cursor` links — so `.agents` and `.windsurf` join
`FORBIDDEN_PATH_PARTS` (corekit PR #310, merged `df8659e3`), with tests for
the exclusion, a non-forbidden-symlink negative control, and tracked-path
rejection under the new names.

**brain:** the three tracked paths are untracked with `.gitignore` entries and
stay on disk (symaira-brain PR #651, merged `a7002cc1`, closes
[symaira-brain#635](https://github.com/danieljustus/symaira-brain/issues/635)).
`git ls-tree -r a7002cc1` lists zero paths under `.cursor/` or
`.phase0-evidence/`. The local brain checkout has not pulled that revision yet
(its working tree is owned by another session), so the gate has not re-read a
clean checkout at `a7002cc1`; the merged revision itself is verified empty.

Effect: zero `checkout.path` findings in the 2026-09-22 run. Class 3 is closed;
the issues it tracked (symaira-brain#635, eraseme#993, desktop#984,
vault#1080) are all closed.

## 4. The genuine released-consumer evidence — five consumers, 10 findings

`rust.evidence.standalone` and `rust.evidence.rollback` read `missing` for all
five records now that brain, browse and desktop carry honest adoption records.
This is the class the gate is really about: a *released* consumer that runs
standalone and can roll back, with the verifier hashing the artifact and
matching the committed report at the pinned checkout. It needs those
consumers' own release runs; CoreKit cannot manufacture it.

Closure sequence: consumers released → checkout re-pinned to the released
commit (class 1) → standalone/rollback reports committed there → gate re-run.

## Decision

- `RUST-015` stays `blocked`. Classes 2 and 3 are closed; classes 1 and 4
  remain, and class 1 is deliberately coupled to class 4 rather than refreshed
  mid-flight.
- Class 3's fixes live in symaira-brain#635 (closed) and CoreKit PR #310; the
  CoreKit tracking issue danieljustus/symaira-corekit#249 stays open for
  classes 1 and 4.
- No CoreKit release, registry publication, Go removal or consumer rollout is
  authorised by this document. `RUST-014` remains `in_progress` for the same
  reason: `port/release/manifest.json` may not move off `not-run` before this
  gate is complete.
