# RUST-015 released-consumer gate: what actually blocks it

`python3 port/consumer/verify.py --released-consumers` returns `status: blocked`
for CoreKit. The findings are not one missing artefact; they fall into four
classes, and only class 4 is the genuine "no released consumer yet" work.
Class 2 is closed as of 2026-09-21; classes 1, 3 and 4 remain open with the
reasons below.

Run 2026-09-21 (corekit `main` `53aee98` with the record refresh applied),
consumers at their then-current heads: brain `46d2c1b5`, browse `c9ab83cc`,
desktop `4ea77f3c`, eraseme `91343c6f`, vault `a28b6a09`. Consumer checkouts
are actively moving, so the per-repo counts differ between runs; the classes
do not.

| Class | Findings | Where |
| --- | --- | --- |
| 1 — stale `checkout_commit` | 5 | all five records |
| 2 — wrong `rust.status` | 0 — fixed | — |
| 3 — consumer checkout hygiene | 7 | brain (4), eraseme (2), vault (1) |
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

## 3. Consumer checkout hygiene — consumer-side, moving

Snapshot of the 2026-09-21 run:

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

`target` symlink directories are this machine's dev-storage layout
(`dev-external` symlinks build trees onto the NVMe), not tracked consumer
source. The gate rejects any symlink directory inside a checkout, so a consumer
cannot pass while such a symlink exists; whether closure removes the symlinks
on the verifying checkout or the gate gains an explicit generated-tree rule is
still open and recorded here.

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

- `RUST-015` stays `blocked`. Class 2 is closed; classes 1, 3 and 4 remain, and
  class 1 is deliberately coupled to class 4 rather than refreshed mid-flight.
- Class 3 is consumer-side work tracked in the affected repositories
  (symaira-brain#635, eraseme#993, desktop#984, vault#1080) and in the CoreKit
  tracking issue danieljustus/symaira-corekit#249.
- No CoreKit release, registry publication, Go removal or consumer rollout is
  authorised by this document. `RUST-014` remains `in_progress` for the same
  reason: `port/release/manifest.json` may not move off `not-run` before this
  gate is complete.