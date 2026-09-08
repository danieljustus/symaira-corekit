# Go→Rust migration handoff

Status: **RUST-001 through RUST-005 and RUST-013 complete; RUST-014 local release tooling is complete but its external publication gate is pending; Go remains the supported executable oracle and no broad cutover is implied**.

This directory freezes the starting point for a contract-first Rust implementation of `symaira-corekit`. The Go implementation remains supported, buildable and the executable oracle while Go consumers exist. Rust crates are added beside it and are adopted package by package; this is not a flag-day repository rewrite.

## Pinned oracle

- Commit: `f3d3eb79b9b1f31b4f973d2ed518a8292cedf588`
- Stable release: `v0.17.0`
- Go module: `github.com/danieljustus/symaira-corekit`
- Go toolchain: `go1.26.6`
- Oracle gate: `GOTOOLCHAIN=go1.26.6 make build test lint`
- Production/fixture digest: `ab38c1cc4d2f91026e1d6836e1138388fd683a789ab8f104269d019c3caff95c`

The oracle is five commits after `v0.17.0`. Every generated fixture must name the exact commit and verify the tracked Go/JSON/SQL input digest. Later Go changes require an explicit contract classification and regenerated fixture before the corresponding Rust parity status can remain green.

MCP provenance is layered: the repository-wide RUST-001 inventory remains pinned to `f3d3eb79b9b1f31b4f973d2ed518a8292cedf588`, while each MCP-001 through MCP-012 row and the executable MCP corpus pins the merged MCP slice oracle `ff0e10ede1071f0a3137fd2774bd89d53f60cc9d`. The MCP CI checkout uses full history so that per-slice commit can be archived and executed.

Cancellation is also an explicit safe-Rust boundary: Go receives `context.Context`, while Rust handlers receive a cooperative `CancellationToken`. The transport-level Rust test proves prompt return without joining an unclosable reader; normal EOF still joins in-flight handlers. Go's nil/duplicate/empty registration panics remain an accepted language difference, represented by Rust `RegistrationError` and executable rejection tests rather than fake panic parity.

## Resolved prerequisite defect

`DEFECT-001` recorded a real contract contradiction: the update-check fixture
and cross-language prose claimed an in-memory/no-disk cache, while the pinned Go
implementation persists a per-repository cache below the platform cache
directory. RUST-001 corrected the fixture, prose and Go tests to the pinned Go
behavior and updated the vendored Swift AppKit fixture plus a cross-instance
cache test. The row is now `fixture-ready`; Rust must preserve this corrected
behavior.

## Why now

`symaira-fritz` has completed its Rust migration, while Brain, Browse, Desktop, Vault and EraseMe already contain Rust workspaces. Waiting until they finish would force each repository to invent local versions of shared contracts. Starting with executable contracts now lets proven common code move into CoreKit without designing speculative abstractions.

## Goal and value gates

CoreKit is a library, so a single standalone binary-size target would be fake precision. A Rust crate proceeds beyond its representative slice only when all of these hold:

1. its observable Go↔Rust contracts pass on supported native platforms;
2. at least **two active Rust consumers** adopt it, or it owns a language-neutral ecosystem contract consumed by at least two languages;
3. adopted consumers delete or avoid an equivalent local implementation with no net duplicate increase;
4. representative consumer release binaries regress by no more than **10%** in startup p95, peak-RSS median, operation p95 or binary size unless a documented security gain justifies the cost;
5. algorithmic crates (`domkit`, `evidencekit`, `vectorkit`) stay within **10%** of Go p95/throughput and preserve exact persisted/wire bytes where specified;
6. build and test time is measured, reported and does not become an unbounded ecosystem tax.

Failure of the adoption gate means the crate stays demand-driven or is not built. Rust is not counted as a benefit by itself.

## Scope

Included:

- all public Go-package behavior and language-neutral JSON contracts;
- Rust equivalents for packages demanded by active Rust consumers;
- exact wire, file, SQLite, archive, logging and error contracts;
- dual-language CI, SemVer, publishing and consumer-pin policy;
- a neutral Go↔Rust fixture and differential harness.

Non-goals:

- deleting or breaking Go packages while released Go consumers remain;
- mirroring every Go package or API mechanically in Rust;
- forcing one umbrella Rust crate on consumers;
- creating a cross-repository Cargo workspace;
- moving product-specific policy into CoreKit;
- redesigning schemas or fixing Go behavior silently during parity work;
- porting deprecated `ollamakit` as a new first-class Rust crate.

## Migration and rollback rule

The repository remains dual-language. Go tags and APIs continue under existing SemVer. Rust crates begin at `0.x`, use exact internal versions, and are consumed first by exact Git revision plus `Cargo.lock`. crates.io publishing is allowed only after the public API and multi-consumer adoption gate pass. A Rust crate may be removed before 1.0 if it fails adoption; a Go package may be removed only in a separate major-version decision after repository-wide released-consumer evidence says it is unused.

## Stop rules

Stop and reassess when any of these holds:

- a Rust abstraction has fewer than two real consumers and owns no cross-language SSOT;
- exact MCP framing, SQLite state, archive safety, audit-chain bytes, vector sidecars or LLM wire behavior cannot be preserved;
- an upstream crate requires a broad permanent fork, unacceptable native runtime dependency, or unbounded unsafe surface;
- dependency features make small consumers pull unrelated HTTP, SQLite, DOM or async stacks;
- dual-language tags cannot express compatible Go and Rust releases without consumer ambiguity;
- Go is no longer independently testable before its released consumers have migrated;
- the representative value gate fails.

## Prepared artifacts

- [`baseline.json`](baseline.json) — measured Go starting point and real consumer demand.
- [`value-gate.json`](value-gate.json) — machine-readable RUST-005 adoption, duplication and regression evidence.
- [`architecture.md`](architecture.md) — target crates, dependency direction and publishing model.
- [`upstream-evaluation.md`](upstream-evaluation.md) — reuse/build decisions and mandatory spikes.
- [`contract-matrix.json`](contract-matrix.json) — stable observable-contract IDs.
- [`implementation-plan.md`](implementation-plan.md) — ordered vertical slices.
- [`release-manifest.md`](release-manifest.md) — RUST-014 tag, package, provenance and publication contract.
- [`work-items.json`](work-items.json) — machine-readable acyclic work graph.
- [`validate.py`](validate.py) — validates schemas, IDs, links, coverage and graph barriers.
- [`../../testdata/rust-port/`](../../testdata/rust-port/) — generated public API, contract fixtures, neutral cases, isolation limits, paired-consumer canaries, and RUST-005 adoption evidence/reports.
- [`../../scripts/rust-port/`](../../scripts/rust-port/) — exact-oracle generator, Go↔Go differential self-test, adoption validator, and real paired value benchmark.

Run `make port-contract`, `make rust-foundation-contract`, `make rust-lint`,
`make rust-test` and `make rust-release-contract`. The required foundation,
filesystem/secret, MCP, multi-consumer value and release-manifest slices are
complete; later package ports remain demand-driven.

RUST-014's local release gate is intentionally non-publishing:
`cargo semver-checks check-release --package symaira-core-version --baseline-rev HEAD^`
plus `python3 port/release/verify.py --dry-run` and
`cargo publish --dry-run --locked -p symaira-core-version` validate the adopted
crate's `0.1.0` public metadata, package archive, provenance inputs and
Cargo-metadata SBOM evidence. The crates.io ownership/public-byte read-back gate
remains open until a separately approved release performs publication. Go tags
remain unambiguous module releases and Go consumers remain supported.

RUST-005 evidence is intentionally live and fail-closed:

- `python3 scripts/rust-port/adoption.py --check --min-consumers 2` checks the
  two exact consumer revisions, Cargo pins/lock resolution, feature closure,
  duplicate removal, standalone command shape, and live merged-PR state.
- `make port-consumer-smoke` builds each adoption revision in a benchmark-owned
  checkout and runs version commands through absolute artifact paths.
- `python3 scripts/rust-port/bench.py --suite foundation --runs 50 --build-runs 10` measures
  real paired startup p95, RSS median, binary size, and 10-run clean/warm build
  distributions. It records summary/provenance only and deletes all temporary
  checkouts, caches and targets.
- `make rust-port-validate` verifies the document, merged-adoption, and tracked
  real benchmark evidence without rerunning the hour-long measurement.
