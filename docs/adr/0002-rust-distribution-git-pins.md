# ADR 0002: Distribute CoreKit Rust crates through exact Git revisions

Status: accepted, 2026-10-03. The maintainer delegated the outstanding decisions
and requested their reasoning in repository docs. Resolves the distribution
choice in CoreKit #371 and the conditional registry rollout in #372.

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
independent downloaded-artifact readback. Shared native/API/security gates and
the consumer issues' minimum seven-day observation remain required.

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
