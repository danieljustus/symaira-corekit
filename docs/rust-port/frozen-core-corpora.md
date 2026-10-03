# Frozen Foundation, LLM and SQLite replay

Default `make rust-foundation-contract rust-llm-contract` runs the real Rust
contracts from unchanged, fixed-hash Go recordings without invoking Go or Git.
Live regeneration is additive verification behind explicit `GO_ORACLE=1`:

```sh
cargo fetch --locked
make rust-foundation-contract rust-llm-contract
GO_ORACLE=1 make rust-foundation-contract rust-llm-contract
```

Registration source: `bd265269a674f6a758037e8f77293e08308464d9`, Go 1.26.6.
Before registration, the real LLM differential and Foundation generator `--check`
both passed against the unchanged committed bytes. Foundation regenerates from
oracle `f3d3eb79b9b1f31b4f973d2ed518a8292cedf588`; its index records generator
inputs and source digest. LLM retains its original production/oracle/runner
SHA-256 provenance in `fixtures/llm/go-oracle.json`. No observation or historical
provenance field was edited to make the new runner pass.

`scripts/rust-port/frozen_core_anchors.py` registers exact bytes independently of
the editable fixture metadata. The runner checks all recorded files and complete
JSON directory inventories, rejects a valid-JSON LF mutation before Cargo,
runs actual Rust tests offline, rejects missing/zero-case/skipped test runs,
and rechecks the inputs after execution. Raw Rust output is retained under
`target/frozen-core-replay/`. The new native CI runs the default Make targets
behind actual Go/Git executables that exit 97 and leave an invocation sentinel;
positive controls prove both denials work before the gate.

| Family | Frozen inputs | Contract groups | Actual local Rust tests |
| --- | ---: | ---: | ---: |
| Foundation and wire contracts | 56 (19 groups + 9 wire contracts, original and Rust snapshots) | 19 | 21 |
| LLM and provider/error wire contracts | 5 | 12 | 48 |

Two cumulative guard tests exercise an actual registered fixture's clean,
mutated, restored and extra-file states; the corrupted state cannot start Cargo.
Both default Make targets passed locally with executable Go/Git denials.
Exact committed native Linux/macOS/Windows CI remains required before merge.

## Native SQLite replay

Default `make rust-sqlite-contract` now runs the current Rust SQLite observer
against unchanged original six-case native Go captures from CI run `37110559130`
at `c3f026dcf7f1c7164f3f709677cdf5b438cba1cc`. The artifacts are registered under
`testdata/rust-port/sqlite/frozen-v1/`; each original report and source manifest
has a fixed independent digest and immutable artifact ID. Before registration,
all three captures passed current Go source/helper provenance reconstruction,
source-manifest verification and recomputation of their original typed verdicts.
The original report/manifest bytes are retained rather than reserialized.

The Go-free runner uses the unchanged accepted candidate source manifest,
builds and runs the real Rust observer in private HOME/XDG/temp roots with no Go
lookup, measures actual SQLite lock contention, and uses the same typed-error
and consuming-close contract. It requires all six cases and rejects a real
ping observation mutation against the executed Rust. An executable CLI guard
proves unchanged, LF-mutated and restored original bytes. Git is retained for
source/ancestry verification; only Go is denied in the SQLite native gate.
Historical live differential is opt-in via `GO_ORACLE=1`. Existing unit and
provenance controls remain part of the default Make gate.

Local Linux default SQLite Make gate passed with Go denied: six cases, 42
checked fields and semantic mutation rejection. Original Darwin and Windows
Go captures and verdicts are verified; new native Go-free Rust execution there
remains required. Raw new Rust observations and the source-bound replay report
are retained alongside native CI's full default-Make output.

This is a slice of #368, not aggregate completion. FS/SEC, MCP/MCP-config and
static-update frozen families retain their own gates. Request/TLS/cancellation
and signed-update helpers, Apply/Cosign platform corpora and cache-persistence
observations still require Go-free replacements and complete native accounting
before `make rust-contracts` can be introduced.
No Go removal, consumer release or crates.io publication is claimed.
