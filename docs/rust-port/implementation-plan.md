# Symaira CoreKit Go→Rust implementation plan

> **Execution rule:** implement one work item per reviewed PR. Keep Go green and released. Rust crates remain Git-pinned and non-publishing until the full migration, consumer rollout, and external registry-evidence gates are complete. Begin only with the first `ready` item in [`work-items.json`](work-items.json); update statuses only after every acceptance command really passes.

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

## RUST-005: Foundation multi-consumer adoption and value gate — COMPLETE (live read-back 2026-09-08)

**Objective:** Prove the shared Rust foundation has real ecosystem value before expensive package ports.

**Steps:**

1. Select two active Rust consumers with overlapping needs; prefer already-implemented version/exit/config/log/fs/MCP slices.
2. Replace or avoid local duplicate code in small consumer PRs, each exact-pinned by CoreKit Git revision and `Cargo.lock`.
3. Run each consumer's full native test/release gates and verify standalone startup without other Symaira products.
4. Measure 50-run startup p95/RSS median/binary size canaries and 10-run clean/warm consumer build distributions.
5. Record deleted/avoided duplicate source and dependency-feature closure.
6. Stop, split or abandon crates that lack two adopters/two-language SSOT or exceed the 10% regression ceiling without an approved security exception.

**Acceptance evidence:** Live `python3 scripts/rust-port/adoption.py --check --min-consumers 2` on 2026-09-08 read back both adoption PRs as merged: danieljustus/symaira-vault PR #1000 (merge commit `b39d1c2de59d205a91c01e584776d568c3877d7e`) and danieljustus/symaira-eraseme PR #866 (merge commit `eb628050d136a2b2009250a8c6f21eb718d853fc`), both exact-pinned to CoreKit revision `27177f25f551cecefa7bd6c4524abf175b3a75c7` with matching `Cargo.lock` resolution. `bench.py --check` validates the tracked 50-run benchmark evidence (maximum regression ratio 0.4755 vault / 0.4430 eraseme, below the 1.1 ceiling), `make port-consumer-smoke` passes, and `value-gate.json` records `status: passed` / `decision: continue`. This is Git-pin adoption evidence, not a registry or release claim.

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

## RUST-013: Full dual-language hardening and native CI — COMPLETE (revalidated 2026-09-08)

**Objective:** Turn the foundation and every optional slice activated so far into a sustainable repository gate. Deferred, unbuilt crates do not block a foundation release.

**Steps:** Add native macOS/Linux/Windows Rust jobs, MSRV, feature isolation, coverage, audit, deny, Miri and fuzz schedules. Verify all Go tests/lint/build/apidiff remain required. Inventory every transitive unsafe source and ensure contract edits trigger both language suites.

**Miri gate:** `scripts/rust-port/miri_gate.py` derives the expected package set from Cargo metadata and rejects overlaps or omissions. It runs pure/core packages with Miri's default isolation, then runs filesystem/process/environment boundary packages in a separate invocation with `MIRIFLAGS=-Zmiri-disable-isolation`. The negative probe executes the real `CON-001` fixture under default isolation and must observe Miri's isolated `open` rejection; a successful probe is a gate failure, not a reason to silently broaden the non-isolated set. The deterministic 10,000-iteration MCP smoke test is explicitly skipped in both Miri invocations because it is covered by the dedicated fuzz gate and otherwise dominates runtime; all other selected tests and doctests still run. Native filesystem safety remains covered by the RUST-003 matrix; this split only makes the Miri trust boundary explicit and bounded.

**Hardening execution:** `make rust-hardening` is the executable RUST-013 aggregate. It runs pinned-toolchain format/check/Clippy, nextest, doctests, every-feature validation, LLVM coverage instrumentation, cargo-audit, cargo-deny, Rust-port metadata validation, and the complete Go build/test/lint gates. The `cargo hack --no-dev-deps` invocation deliberately omits `--locked` because cargo-hack temporarily rewrites manifests and must refresh its lock view; all other lock-sensitive commands remain locked. CI additionally runs full Rust workspace tests and doctests natively on Linux, macOS, and Windows.

**Acceptance evidence:** The historical hardening gate was merged through PR #246 at exact head `b3f189f6ac4c78986c48be510805663906cce876`; GitHub reports the `Rust RUST-013 hardening` job successful in run `34193678917` (job `101956734067`). Its log contains successful `cargo audit` and `cargo deny check` commands, which is the bound evidence for `REL-004` parity. Revalidation on 2026-09-08 at `d382b8615ce879bac6f23c7250e13667934e8f93`: the local gate set (`cargo fmt --all --check`, `cargo check/clippy/nextest/doctest --locked`, `cargo hack --each-feature`, `cargo audit`, `cargo deny check`, `miri_gate.py --self-test`) passed on macOS, and native CI run `34231886903` (push to main) for that commit is green on ubuntu-latest, macos-latest and windows-latest including the RUST-013 native, Miri gate and hardening jobs. RUST-013 is complete; no crate publication, Go cutover or Go-oracle removal occurred.

## RUST-014: SemVer, publishing manifest and release verification — IN PROGRESS (non-publishing local gate)

**Objective:** Keep the release contract executable without publishing. No crates.io publication is permitted until the full migration and consumer rollout are complete, followed by separately approved external registry evidence.

**Create:** `port/release/manifest.json`, `port/release/verify.py`, and focused
stdlib-only verifier tests. The manifest classifies every workspace package,
records the two RUST-005 adopters of `symaira-core-version`, freezes the only
permitted publication order, and keeps all crates non-publishable until a
separate external release approval.

**Steps completed:**

1. Added `cargo semver-checks` as a pinned CI tool/bootstrap gate, independent
   of the existing Go `apidiff` gate. It does not establish public Rust SemVer
   compatibility until a publishable crate has an immutable registry baseline.
2. Added a checked-in release plan mapping the stable Go `v0.17.0` namespace to
   explicit Rust package paths/versions. Rust-specific repository tags are
   rejected; the Go `vMAJOR.MINOR.PATCH` tag remains the only release namespace.
3. Added a fail-closed dry-run verifier that checks locked Cargo metadata,
   workspace coverage, adoption evidence, package order and temporary `.crate`
   archives, and emits source/input digest plus Cargo-metadata SBOM evidence.
4. Wired the verifier and SemVer tool into `ci.yml` and the
   `rust-release-contract` Make target. The Go-only tag workflow deliberately
   does not run a Rust publication plan; no publish or tag command exists in
   the verifier.

**Evidence:** `cargo semver-checks check-release`,
`python3 port/release/verify.py --dry-run`, and the focused Python tests pass on
macOS. `REL-002` is locally verified by the existing Go `apidiff` gate.
`REL-003` and `REL-005` are `fixture-ready`: no public Rust API baseline,
crates.io ownership, public-byte readback, or external OIDC/publishing evidence
exists while every crate stays `publish = false`. Go build/test/lint and exact
Git-revision consumer support remain unchanged.

## RUST-015: Consumer rollout and Go-retention review — BLOCKED (verifier implemented)

**Objective:** Finish adoption without pretending Rust crate availability removes the Go API.

**Executable gate:** `python3 port/consumer/verify.py --released-consumers` checks every `docs/consumers.json` record. It distinguishes released Git revisions from registry pins, exact Cargo.toml versions, Cargo.lock source/checksum, release-tag ancestry, Go imports, and explicit standalone/rollback evidence. The current run is expected to exit 1 with blockers; `make consumer-drift` runs the same verifier from the canonical checkout even when invoked from a registered worktree.

**Steps:** Track every released Go and Rust consumer, exact pin and package use; migrate consumer by consumer with its own suite; retain Go releases while any released consumer imports a package. Any Go removal is a later, separate major-version proposal with rollback evidence.

## Final handoff verification

```text
python3 docs/rust-port/validate.py
GOTOOLCHAIN=go1.26.6 make build
GOTOOLCHAIN=go1.26.6 make test
GOTOOLCHAIN=go1.26.6 make lint
```

After RUST-002 exists, the final gate additionally includes fmt, check, Clippy, nextest, doctests, feature checks, coverage, Miri, audit, deny and the complete Go↔Rust differential corpus.