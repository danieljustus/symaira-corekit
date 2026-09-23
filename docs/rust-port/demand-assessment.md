# Demand assessment for the demand-driven slices

`RUST-007` through `RUST-012` are classified `demand_driven` in
[`work-items.json`](work-items.json), which means they stay `deferred` until two
real Rust consumers need the same shared module (the standing rule in
`AGENTS.md`/PB-2026-09-09) **and** a duplication exists that the shared module
would remove (the value bar recorded by `RUST-005`). This document records the
actual search evidence behind each verdict so `deferred` is an assessed state
rather than an unexamined default.

Method: read-only searches over the Rust sources of every current Rust consumer
in the workspace (`symaira-desktop`, `symaira-eraseme`, `symaira-vault`,
`symaira-brain`, including its `browse/` module), rechecked 2026-09-23. Paths are relative to
`/Volumes/1TB_NVMe_SN850X/Dev/Symaira_Dev/Repos`.

## RUST-007 — Update, archive, Cosign and atomic apply (`UPD-*`) — deferred

```sh
rg -l -i -g '*.rs' "updatecheck|update_check|latest release|self_update|cosign|atomic.apply" \
  symaira-brain/rust symaira-brain/browse/crates symaira-desktop/crates symaira-eraseme/crates symaira-vault/crates
```

Brain's `rust/symbrain-managed/src/install.rs` implements release download,
publisher verification, extraction and atomic installation. Vault's
`crates/symvault-cli/src/update_commands.rs` explicitly keeps `update check`
and `update apply` unavailable; its `update info` reports the installation
method, not the same pipeline. **Verdict: deferred — one Rust consumer needs
the full pipeline; nothing to de-duplicate yet.**

## RUST-008 — Descriptor-driven LLM provider slice (`LLM-*`) — deferred

```sh
rg -l -i -g '*.rs' "openai|anthropic|ollama|provider|llm" \
  symaira-brain/rust symaira-brain/browse/crates symaira-desktop/crates symaira-eraseme/crates
```

Two consumers carry the *surface*: `symaira-desktop/crates/symdesk-core/src/config.rs`
has `llm_provider`/`llm_model`/`ollama_url` with the accepted provider set
(`ollama`, `anthropic`, `openai`, `hermes`, lines 36-103 and 244-251), and
`symaira-eraseme/crates/symeraseme-core/src/triage_prompts.rs` builds the triage
LLM prompts while `triage_contract.rs` states that LLM transport is explicitly
out of scope for that slice; the CLI exposes `--provider`/`--model` overrides
(`symeraseme-cli/src/command_surface.rs:186-192, 334-340`).

EraseMe now has a Rust LLM error/retry/provider-resolution surface in
`crates/symeraseme-core/src/llm/mod.rs`, but it explicitly leaves provider
transport unported. Brain's `rust/symbrain-usage/src/provider_requests.rs`
builds account/quota usage requests, not generation requests. Brain memory's
`rust/symbrain-memory/src/embedding.rs` does make Ollama embedding requests;
no second Rust consumer duplicates that embedding transport. **Verdict:
deferred — no shared generation or embedding transport to de-duplicate yet.**

## RUST-009 — Audit and grounded-evidence algorithm slices (`AUD-*`, `EVID-*`) — deferred

```sh
rg -l -i -g '*.rs' "auditkit|evidencekit|evidence_bundle|grounded.evidence|audit_log|hash.chained" \
  symaira-brain/rust symaira-brain/browse/crates symaira-desktop/crates symaira-eraseme/crates symaira-vault/crates
```

`symaira-brain/rust/symbrain-audit/src/sink.rs` implements a CoreKit-compatible
SHA-256 hash-chained JSONL sink. Vault's
`crates/symvault-store/src/audit.rs` implements a keyed HMAC-SHA256 chain with
Vault key lifecycle; its format and trust boundary differ. Brain's other audit
crates are part of the same product, not a second consumer. No second Rust
consumer needs the same generic audit algorithm, and no second grounded-evidence
algorithm was found. **Verdict: deferred — no shared semantics to extract.**

## RUST-010 — MCP configuration discovery slice (`MCFG-*`) — **implemented**

Implemented as `rust/symaira-core-mcpcfg` and proven against the pinned Go
oracle commit `f3d3eb79…` by `scripts/rust-port/mcpcfg-differential.py` over the
24-case corpus in `testdata/rust-port/mcpcfg-cases.json`; see
`resume-checkpoint.md` for the observation boundary and the negative controls.

```sh
grep -rn --include=*.rs -iE "mcp_config|claude_desktop_config|mcpServers" \
  symaira-vault/crates symaira-brain/rust | grep -v /target/
```

Two Rust consumers independently implement agent/MCP configuration discovery:

- `symaira-brain/rust/symbrain-harness/src/registry.rs` maps agent targets to
  their config files and server keys — `HOME_CODEX = [".codex", "config.toml"]`,
  `HOME_ANTIGRAVITY = [".gemini", "config", "mcp_config.json"]`,
  `servers_key: Some("mcpServers")` (lines 265-285) — and `symbrain-cli` drives
  it from `doctor_core.rs`/`guard_scan.rs`, with `harness_list_tests.rs`
  asserting against a real `claude_desktop_config.json` layout.
- `symaira-vault/crates/symvault-cli/src/doctor_commands.rs` runs its own
  `mcp.agents` and `mcp.dynamic.engines` checks (lines 266-278) against its own
  agent list (`claude-code`, `codex`, `opencode`, `hermes`, `openclaw`,
  line 2088), with a differential test
  (`tests/doctor_differential.rs`, `differential_doctor_mcp_config_checks`).

The two differ in depth — brain parses the per-agent config files directly,
vault discovers the configured agents and MCP engines from its own config — but
both maintain an agent/target registry that answers "where is MCP configured for
this agent", which is the `mcpcfgkit` concern. **Verdict: demand met → the item
moves from `deferred` to `ready`.** Its acceptance commands
(`make rust-mcpcfg-contract`, `python3 scripts/rust-port/diff.py --suite mcpcfg`,
`cargo nextest run -p symaira-core-mcpcfg`) do not exist yet; building them is
part of the slice, exactly as the SQLite suite was built with `RUST-006`.

## RUST-011 — DOM selection and rendering feasibility (`DOM-*`) — deferred

```sh
rg -l -i -g '*.rs' "domkit|dom_selector|dom_query|readability|html5ever" \
  symaira-brain/browse/crates symaira-desktop/crates symaira-eraseme/crates symaira-vault/crates
```

Brain's `browse/crates/symbrowse-fetch/src/dom.rs` implements HTML5 parsing,
cleanup, selection and serialization in Rust. Browse is a module of Brain, so
this is one Rust product consumer, not a second independent one. **Verdict:
deferred — one Rust consumer.**

## RUST-012 — TurboQuant codec and performance slice (`VEC-*`, `PERF-003`) — deferred

```sh
rg -l -i -g '*.rs' "turboquant|vector_quant|quantiz" \
  symaira-brain/rust symaira-brain/browse/crates symaira-desktop/crates symaira-eraseme/crates symaira-vault/crates
```

`symaira-brain/rust/symbrain-memory` carries vector storage and quantization
metadata, but no TurboQuant codec. `symaira-desktop` matches only on unrelated
text simhash. **Verdict: deferred — no demonstrated shared codec; re-assess
when two Rust consumers need it.**

## Re-assessment rule

Re-run the searches above (or their equivalents) before starting any of these
slices. A slice leaves `deferred` only when the search finds two Rust consumers
that need it and a duplication the shared module removes; record the hits here
and update `demand_evidence`/`status` in the same change.
