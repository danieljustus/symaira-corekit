# RUST-015 released-consumer gate: what actually blocks it

`python3 port/consumer/verify.py --released-consumers` returns `status: blocked`
for CoreKit (run 2026-09-20, `main` `33eb0c6`). The 32 findings are not one
missing artefact; they fall into four classes, and only the last one is genuine
"no released consumer yet" work.

## 1. Stale `checkout_commit` in `docs/consumers.json` — all five records

| Consumer | recorded | current HEAD |
|---|---|---|
| symaira-brain | `5608965` | `c83ebad` |
| symaira-browse | `5f98dfa` | `c9ab83c` |
| symaira-desktop | `2de1ba0` | `99f4dbe` |
| symaira-eraseme | `76b2f6b` | `9b54841` |
| symaira-vault | `a57f565` | `622ec61` |

The gate requires the checkout HEAD to equal the recorded commit, so every
consumer that moved on makes the gate red. CoreKit-side bookkeeping.

## 2. Stale `rust.status` for brain, browse and desktop — 9 findings

The records still say `rust.status: not_adopted`, while the verifier finds
`symaira-core-version` in their tracked `Cargo.toml`/`Cargo.lock`
(`browse/Cargo.*`, `crates/symbrowse-protocol/Cargo.toml`,
`crates/symdesk-core/Cargo.toml`, …). `not_adopted` and an adopted pin cannot
coexist, so these records are factually wrong. CoreKit-side bookkeeping.

## 3. Consumer checkout hygiene — 12 findings in three repositories

Tracked paths the verifier must reject because they are not plain source:

- `symaira-desktop`: `.build/.buildSystem_debug`, `.build/CACHEDIR.TAG`.
- `symaira-eraseme`: tracked symlinked skill directories
  (`.agents/skills/symaira-eraseme`,
  `examples/windsurf/.windsurf/skills/symaira-eraseme`) plus tracked
  `.claude/skills/*`, `examples/*/.cursor|.windsurf/skills/*` and
  `.omo/run-continuation/*.json`.
- `symaira-vault`: `.agentsroom/.gitignore`, `.agentsroom/project.json`.

Consumer-side work; filed as
[eraseme#993](https://github.com/danieljustus/symaira-eraseme/issues/993),
[desktop#984](https://github.com/danieljustus/symaira-desktop/issues/984) and
[vault#1080](https://github.com/danieljustus/symaira-vault/issues/1080).

## 4. The genuine released-consumer evidence — eraseme and vault

Both records carry `rust.evidence.standalone.status: "missing"` and
`rust.evidence.rollback.status: "missing"` with an empty `command`, and
`rust.registry.status: not_released`. This is the class the gate is really
about: a *released* consumer that runs standalone and can roll back, with the
verifier reading back the artifact hash. It needs those consumers' own release
runs; CoreKit cannot manufacture it.

`symaira-brain` additionally has a dirty checkout (`checkout.dirty`), which the
gate also rejects.

## Decision

- `RUST-015` stays `blocked`. The reason is no longer "no released consumers" but
  the four classes above; classes 1 and 2 are CoreKit bookkeeping, class 3 is
  consumer hygiene, class 4 is the real external gate.
- Classes 1–3 are tracked in
  [corekit#295](https://github.com/danieljustus/symaira-corekit/issues/295) and
  the consumer issues named above. Refreshing classes 1 and 2 alone does **not**
  make the gate pass — it only moves the finding to class 4.
- No CoreKit release, registry publication, Go removal or consumer rollout is
  authorised by this document. `RUST-014` remains `in_progress` for the same
  reason: `port/release/manifest.json` may not move off `not-run` before this
  gate is complete.
