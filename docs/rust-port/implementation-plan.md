# Symaira CoreKit Go→Rust implementation plan

> **Execution rule:** implement one work item per reviewed PR. Keep Go green and released. Begin only with the first `ready` item in [`work-items.json`](work-items.json); update statuses only after every acceptance command really passes.

**Goal:** Add adopted, idiomatic Rust CoreKit crates beside the stable Go module, preserving all observable contracts and removing duplicate foundations from active Rust consumers without a flag-day rewrite.

**Architecture:** Language-neutral fixtures point inward. Small synchronous foundation crates sit below isolated filesystem, process, MCP, SQLite, HTTP and algorithm adapters. No umbrella crate, cross-repository workspace or sibling product import.

**Initial stack:** Rust 1.98 candidate (repin at RUST-002), Serde, thiserror, tracing, TOML parser, official `rmcp` behind an adapter, rusqlite feasibility spike, reqwest/Rustls, focused archive crates, RustCrypto hashes, nextest, Miri, proptest/fuzz, audit/deny/semver gates.

---

## RUST-001: Neutral Go oracle, API inventory and fixture harness — COMPLETE

**Objective:** Turn the in-process Go library into deterministic, language-neutral executable evidence before Rust production code exists.

**Create:**

- `scripts/rust-port/generate.py` — source digest, fixture generation and `--check` mode.
- `scripts/rust-port/diff.py` — neutral runner/comparator.
- `scripts/rust-port/go-oracle/` — tiny Go helper commands per package family.
- `testdata/rust-port/cases/` and `testdata/rust-port/fixtures/`.
- Make targets: `port-fixture-source-check`, `port-oracle-selftest`, `port-contract`.

**Steps:**

1. Use `go/packages`/`go/types` to record all public non-internal packages, exported declarations and signatures at the pinned commit.
2. Bind generation to the exact tracked Go/JSON/SQL source digest; reject dirty or mismatched oracle inputs.
3. Define case data for typed input, env allowlist, isolated HOME/XDG/temp roots, returned JSON/error, stdout/stderr, file manifest, SQLite snapshots, HTTP transcript and process argv.
4. Generate fixtures through production functions or minimal Go wrappers—not by hand.
5. Prove Go↔Go self-equality; mutate one known output and prove the comparator fails; restore and re-run.
6. Document isolation limits and inject fake HTTP/process/keychain adapters. A temp HOME is not a sandbox.
7. Capture paired-consumer canary definitions and repeatable benchmark commands; do not invent Rust numbers yet.

**Evidence:** `testdata/rust-port/fixtures/public-api.json` freezes 23 public
packages, 293 exported top-level declarations and 320 exported methods/fields.
The generator reproduces all six supported OS/architecture targets and rejects
target-specific API drift before emitting this deduplicated canonical fixture;
`make port-contract` checks source provenance and regenerated fixtures, runs a
Go↔Go production probe twice in isolated roots, proves a deliberate mismatch is
rejected, rejects reserved environment overrides, and verifies native
parent-plus-descendant timeout cleanup. `DEFECT-001` is corrected in CoreKit and
the vendored AppKit fixture/test. No Rust production crate was created.

## RUST-002: Pinned Rust workspace and contracts/foundation slice — COMPLETE

**Objective:** Establish the dual-language build and implement the smallest highly reused deterministic surface.

**Create:** `rust-toolchain.toml`, workspace `Cargo.toml`, `Cargo.lock`, `deny.toml`, private `rust/test-support/{symaira-contract-fixtures,symaira-core-foundation}`, plus independent `rust/symaira-core-{exit,version,env,log,config}` crates. The foundation package is test-only and never a consumer dependency.

**Steps:**

1. Repin reviewed stable Rust; install toolchain/rustfmt/Clippy serially before parallel writes.
2. Add explicit `rust-version`, Apache-2.0 metadata and `#![deny(unsafe_code)]`.
3. Embed and type the contract JSON without changing its bytes or ownership.
4. Port version, exit/error, env, log and config behavior as independent modules.
5. Preserve exact version/error/log bytes and config precedence/type behavior through generated fixtures.
6. Add fmt, check, Clippy, nextest, doctest, feature and coverage gates while every Go gate remains mandatory.

**Evidence:** Rust 1.98 is pinned with five independent, non-publishable
foundation crates plus private fixture/support crates. Nineteen contracts use
production-Go-generated fixtures and pass byte/semantic parity tests. Format,
Clippy, nextest, doctests, each-feature checks, Miri for the unsafe environment
seam, audit, deny, Windows cross-check, complete Go gates, spec review and code
quality review passed.

## RUST-003: Filesystem and secret-reference safety slice

**Objective:** Provide the first security-sensitive reusable substrate without weaker race, symlink or redaction behavior.

**Create:** `rust/symaira-core-fs` and `rust/symaira-core-secretref` plus focused native fixtures.

**Steps:**

1. Freeze path validation for Unix and Windows separators/control characters.
2. Exercise atomic create/overwrite, descriptor validation, mode behavior, rename failure and cleanup.
3. Spike capability-based filesystem APIs; use owned safe code if their semantics drift.
4. Port `env://`, bare env, `symvault://` and Darwin `keychain://` parsing.
5. Inject process execution; freeze argv, deadline precedence, missing-binary and redacted error behavior.
6. Run native macOS/Linux/Windows cases, symlink/race tests, Miri and dependency review.

**Evidence:** The two independent `publish = false` crates implement the FS-001..007 and SEC-001..006 seams with `#![deny(unsafe_code)]`. The fixture corpus is generated from the pinned production Go oracle and covers six native targets, accepted OS differences, symlink/permission/rollback/contention cases, subprocess argv/deadline injection, contract byte identity and redaction. The focused Rust/Go differential gate, Clippy, fmt, audit, deny and native Linux/macOS/Windows CI job are wired through `make rust-fs-secret-contract`; the executable Miri command is `MIRIFLAGS=-Zmiri-disable-isolation cargo +nightly miri test -p symaira-core-secretref --all-features`.

## RUST-004: MCP stdio and typed-tool feasibility slice

**Objective:** Preserve CoreKit's stricter MCP wire behavior before consumers depend on a shared Rust server.

**Create:** `rust/symaira-core-mcp`, raw-frame fixtures and an isolated fuzz package.

**Steps:**

1. Freeze initialize, notifications, ping, tools/list and tools/call in Content-Length and newline modes.
2. Freeze typed schema derivation, strict unknown-field rejection, annotations and structured tool-error `_meta`.
3. Spike exact-pinned official `rmcp` behind an owned adapter.
4. Keep or build the narrow raw framing path wherever SDK bytes/lifecycle differ.
5. Test 1 MiB boundaries, malformed headers/JSON, panic isolation, EOF, cancellation and multiple frames.
6. Enable tracing and prove stdout remains protocol-only.
7. Fuzz copied seed corpora; never let libFuzzer mutate tracked seeds.

## RUST-005: Foundation multi-consumer adoption and value gate

**Objective:** Prove the shared Rust foundation has real ecosystem value before expensive package ports.

**Steps:**

1. Select two active Rust consumers with overlapping needs; prefer already-implemented version/exit/config/log/fs/MCP slices.
2. Replace or avoid local duplicate code in small consumer PRs, each exact-pinned by CoreKit Git revision and `Cargo.lock`.
3. Run each consumer's full native test/release gates and verify standalone startup without other Symaira products.
4. Measure 50-run startup p95/RSS median/binary size canaries and 10-run clean/warm consumer build distributions.
5. Record deleted/avoided duplicate source and dependency-feature closure.
6. Stop, split or abandon crates that lack two adopters/two-language SSOT or exceed the 10% regression ceiling without an approved security exception.

All RUST-006+ work depends transitively on this graph barrier.

## RUST-006: SQLite open, pragma, migration and locking slice

**Demand gate:** start only when two Rust consumers require the same SQLite open/migration policy.

**Objective:** Match modernc SQLite observable state with a safe Rust backend.

**Create:** `rust/symaira-core-sqlite`, production-generated databases and native lock/crash fixtures.

**Steps:**

1. Spike exact-pinned rusqlite with bundled SQLite and record SQLite-version differences.
2. Compare schema, `schema_migrations`, ordered rows, pragmas on every connection and file companions.
3. Test NULL/time encoding, busy timeout, WAL, foreign keys, readers/writers and pool behavior.
4. Interrupt each migration boundary and prove rollback/idempotent recovery.
5. Measure binary/build cost in both adopting consumers before acceptance.

## RUST-007: Update, archive, Cosign and atomic apply slice

**Demand gate:** start only when two Rust consumers require the same complete update pipeline.

**Objective:** Port the full update safety chain, not merely GitHub release parsing.

**Create:** `rust/symaira-core-update` with separate checker, archive, install-method, signature and apply modules.

**Steps:**

1. Freeze stable-version parsing, v0 gap, cache and request behavior against hermetic servers/clocks.
2. Enforce TLS floor, redirect host/cap, body bounds and exact headers.
3. Port tar/zip extraction with pre-write path validation, symlink policy and mode fixtures.
4. Preserve checksum bytes, artifact names, identity regex and Cosign subprocess argv.
5. Port staging, validation, swap, backup restoration and failure cleanup.
6. Test native replacement behavior without touching the running test binary or real installations.

## RUST-008: Descriptor-driven LLM provider slice

**Demand gate:** start only when two Rust consumers require the descriptor-driven provider layer.

**Objective:** Make the shared provider SSOT available to Rust consumers without new per-consumer clients.

**Create:** `rust/symaira-core-llm`; do not create a Rust `ollamakit` crate.

**Steps:**

1. Generate typed descriptors and error taxonomy from `contracts/` and verify drift.
2. Port credential/base-URL/auth/redirect rules behind injected transport and secret resolvers.
3. Freeze OpenAI and Anthropic chat/tool/request/response bytes.
4. Freeze SSE/NDJSON streaming, callback ordering, malformed input and finish reasons.
5. Port embeddings, model discovery and native Ollama compatibility where demanded.
6. Preserve stable error codes, retryability, retry-after, exit mapping and redacted body truncation.

## RUST-009: Audit and grounded-evidence algorithm slices

**Demand gate:** start only after a second adopter or explicit two-language SSOT need is recorded.

**Create:** `rust/symaira-core-audit`, `rust/symaira-core-evidence`.

**Steps:** Freeze and port audit hash input/JSONL/checkpoint/rotation/tamper behavior; then exact/normalized/fuzzy evidence alignment, Unicode byte offsets, tie-breaking, validation sentinels and JSONL. Run properties, Miri and mutation tests on scoring/validation decisions.

## RUST-010: MCP configuration discovery slice

**Demand gate:** start only after a second consumer needs shared JSON/JSONC/YAML discovery.

**Create:** `rust/symaira-core-mcpcfg`.

**Steps:** Freeze default source tables per platform, JSONC string/comment edge cases, YAML/JSON normalization, glob expansion, transport/env merging and stable findings for missing/invalid/approximate entries. Keep platform and client-specific policy data-driven.

## RUST-011: DOM selection and rendering feasibility slice

**Demand gate:** start only after a second adopter or a confirmed extraction from two consumers.

**Create:** `rust/symaira-core-dom` only after the parser spike.

**Steps:** Export the full Go HTML corpus; compare html5ever/scraper/htmd candidates; port selector grammar, filter/subtree behavior, JSON-LD, images, frontmatter and Unicode truncation. Select no renderer until required Markdown/document bytes pass.

## RUST-012: TurboQuant codec and performance slice

**Demand gate:** start only after adoption need is recorded.

**Create:** `rust/symaira-core-vector`.

**Steps:** Generate deterministic rotation/2–4-bit/metadata/sidecar/ranking fixtures through Go; implement safe scalar Rust first; require exact packed/persisted bytes; then benchmark ten paired runs. Add SIMD only as a separate reviewed optimization after parity.

## RUST-013: Full dual-language hardening and native CI

**Objective:** Turn the foundation and every optional slice activated so far into a sustainable repository gate. Deferred, unbuilt crates do not block a foundation release.

**Steps:** Add native macOS/Linux/Windows Rust jobs, MSRV, feature isolation, coverage, audit, deny, Miri and fuzz schedules. Verify all Go tests/lint/build/apidiff remain required. Inventory every transitive unsafe source and ensure contract edits trigger both language suites.

## RUST-014: SemVer, publishing manifest and release verification

**Objective:** Publish only adopted crates without confusing Go module tags.

**Steps:** Add `cargo semver-checks`; define a repository release manifest mapping tag to changed crate versions and publish order; dry-run packaging/provenance/SBOM; verify crates.io ownership and public bytes after publication. Keep exact Git-revision consumption until this gate passes.

## RUST-015: Consumer rollout and Go-retention review

**Objective:** Finish adoption without pretending Rust crate availability removes the Go API.

**Steps:** Track every released Go and Rust consumer, exact pin and package use; migrate consumer by consumer with its own suite; retain Go releases while any released consumer imports a package. Any Go removal is a later, separate major-version proposal with rollback evidence.

## Final handoff verification

```text
python3 docs/rust-port/validate.py
GOTOOLCHAIN=go1.26.6 make build
GOTOOLCHAIN=go1.26.6 make test
GOTOOLCHAIN=go1.26.6 make lint
```

After RUST-002 exists, the final gate additionally includes fmt, check, Clippy, nextest, doctests, feature checks, coverage, Miri, audit, deny and the complete Go↔Rust differential corpus.