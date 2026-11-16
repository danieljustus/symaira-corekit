# ADR 0002: Distribute CoreKit Rust crates through exact Git revisions

Status: accepted, 2026-10-03; amended 2026-11-16 (release-tag pins, see
below). The maintainer delegated the outstanding decisions and requested their
reasoning in repository docs. Resolves the distribution choice in CoreKit #371
and the conditional registry rollout in #372.

## Decision

The supported Rust distribution is an exact, full 40-character Git revision of
the public CoreKit repository, recorded in each consumer's Cargo dependency and
Cargo.lock. Keep Rust crates `publish = false`. A branch name, moving tag, local
checkout or successful build is insufficient release evidence.

Registry publication and registry-pinned rollout are not planned. RUST-014 and
RUST-015 become demand-driven and deferred, with this explicit disposition;
they are not marked complete. Existing release planning, packaging and SemVer
verification tools remain available and their historical evidence stays intact.
Their candidate order describes a possible future publication, not an active
release request. Repository `vX.Y.Z` tags retain their established Go meaning.

## Reasoning

The current demand comes from the four maintainer-owned consumers. Exact Git
pins already support their standalone Cargo builds and bind every release to
reviewable source, allowing an exact rollback. A registry would add crate
version/order coordination, ownership credentials, index/package readback and a
second consumer migration without solving a current distribution requirement.
Choosing Git also separates the Rust consumer cutover from optional publishing
work; the migration can finish without creating credentials or a registry tag.

Git availability and access to the pinned object remain dependencies. Consumer
release builds must retain lockfiles, source identity, downloadable artifacts
and checksums/signatures. Cache/download availability must be verified in a
standalone build; a developer's local cache is not distribution evidence.

Cargo's current `0.0.0` versions are not claimed as stable registry SemVer.
Exact pins do not excuse API review, explicit adapters, compatibility checks or
release notes. Registry SemVer compatibility stays unverified until a real
registry baseline exists.

## Gates that remain required

RUST-016 and #370 still require real public releases of every exact Git-pinned
consumer, source-bound standalone and Go-to-Rust-to-Go rollback reports, and
independent downloaded-artifact readback. Shared native/API/security gates
remain required. The former minimum seven-day observation was removed by the
maintainer on 2026-10-30; it is no longer a RUST-016 gate. On the same date the
Go-to-Rust-to-Go rollback requirement was replaced by Rust-only consumer
cutovers (`go_status: retired`) with backup and verified restore.

Do not remove the Go module while a released consumer still imports it. #373
needs successful consumer retirements and verified rollback; #368 still needs
every Go-free oracle family and a complete aggregate. This decision does not
claim those gates have passed or authorize fabricated release evidence.

## Reconsideration

Open a new distribution proposal when external adopters need crates.io, registry
distribution materially improves verified standalone availability, or Git
package retrieval demonstrably impedes supported consumers. That proposal must
provide demand, explicit versions/order and a registry baseline, and preserve
the released-consumer, source/artifact, ownership and rollback gates. Reopening
publication does not silently reopen or change existing exact consumer pins.

## Amendment 2026-11-16: release-tag pins

A consumer may write its CoreKit dependency as `tag = "vX.Y.Z"` instead of
`rev = "<40-hex>"`. `Cargo.lock` still records the full revision
(`?tag=vX.Y.Z#<40-hex>`) and builds stay `--locked`, so the resolved source and
rollback are unchanged. New and bumped pins should use the tag form; an
existing `rev` pin stays valid.

Reason: Dependabot never proposes an update for a Cargo Git dependency pinned
by `rev`. Its Cargo update checker only moves a pin whose ref looks like a
version (`dependabot-core` `cargo/update_checker.rb`,
`latest_git_version_sha`). Rev-pinned consumers therefore fell 5 to 13 releases
behind without any notice (#490).

Conditions:

- Only stable `vMAJOR.MINOR.PATCH` tags qualify. They are immutable: the
  repository ruleset "Immutable release tags" blocks deleting or moving
  `refs/tags/v*` (creation stays allowed). A tag pin is therefore not the
  "moving tag" rejected above.
- A `docs/consumers.json` record that pins by tag carries `rust.tag` next to
  `rust.revision`. `port/consumer/verify.py` requires the tag to peel to that
  revision, the manifest to name the tag (no `rev`/`branch`), and `Cargo.lock`
  to carry `?tag=<tag>#<revision>`.
- Group the CoreKit crates in the consumer's `dependabot.yml`
  (`patterns: ["symaira-core-*"]`) so one pull request moves them together.
  Excluding them from Dependabot's default 3-day cooldown reports a release at
  once; third-party crates keep the cooldown.
- For a pin declared under `[workspace.dependencies]`, Dependabot rewrites only
  `Cargo.lock` (its workspace manifest updater handles version requirements,
  not Git refs), so `cargo --locked` fails until `Cargo.toml` names the new tag.
  Observed on symaira-brain#1076 (v0.22.0 to v0.23.0); editing that one line
  made `cargo metadata --locked` pass without further lock changes. Consumers
  run `scripts/check-corekit-pins.sh` in CI to name the line to fix.
- A Dependabot pull request is a notice, not a verified bump: the consumer's
  own test suite still decides, as in the consumer bump ownership rules.
