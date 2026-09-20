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
`symaira-brain`, `symbrowse`), on 2026-09-20. Paths are relative to
`/Volumes/1TB_NVMe_SN850X/Dev/Symaira_Dev/Repos`.

## RUST-007 — Update, archive, Cosign and atomic apply (`UPD-*`) — deferred

```sh
grep -rln --include=*.rs -iE "updatecheck|update_check|latest release|self_update|cosign|atomic apply" \
  symaira-desktop symaira-eraseme symaira-vault symbrowse | grep -v /target/
```

No Rust consumer implements an update-check, archive-verification, Cosign or
atomic-apply path. The single hit was a CoreKit checkout inside a consumer's
build cache, not consumer source. **Verdict: deferred — no Rust consumer needs
this slice; nothing to de-duplicate.**

## RUST-008 — Descriptor-driven LLM provider slice (`LLM-*`) — deferred

```sh
grep -rn --include=*.rs -iE "openai|anthropic|ollama|provider|llm" \
  symaira-desktop/crates symaira-eraseme/crates | head
```

Two consumers carry the *surface*: `symaira-desktop/crates/symdesk-core/src/config.rs`
has `llm_provider`/`llm_model`/`ollama_url` with the accepted provider set
(`ollama`, `anthropic`, `openai`, `hermes`, lines 36-103 and 244-251), and
`symaira-eraseme/crates/symeraseme-core/src/triage_prompts.rs` builds the triage
LLM prompts while `triage_contract.rs` states that LLM transport is explicitly
out of scope for that slice; the CLI exposes `--provider`/`--model` overrides
(`symeraseme-cli/src/command_surface.rs:186-192, 334-340`).

Both consumers have *config and prompt plumbing* only. Neither has a provider
client, so a shared descriptor-driven provider module would remove no
duplication yet. **Verdict: deferred — two surfaces, zero duplicated transport;
re-assess when the first consumer implements a provider client.**

## RUST-009 — Audit and grounded-evidence algorithm slices (`AUD-*`, `EVID-*`) — deferred

```sh
grep -rln --include=*.rs -iE "auditkit|evidencekit|evidence_bundle|audit_log" \
  symaira-desktop/crates symaira-eraseme/crates symaira-vault/crates symaira-brain | head
```

`symaira-vault` has a real Rust audit surface: `symvault-cli/src/agent_audit_commands.rs`
reads and writes per-agent `audit-<agent>.log` files, with `symvault-cli/tests/audit.rs`
and MCP-side audit tests. `symaira-brain` shows only unrelated matches
(`audit`/`evidence` inside policy and skills metadata), not an audit-log or
grounded-evidence algorithm. **Verdict: deferred — one consumer; the
two-consumer rule is not met.**

## RUST-010 — MCP configuration discovery slice (`MCFG-*`) — **ready**

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
grep -rln --include=*.rs -iE "domkit|dom_selector|dom_query|readability" \
  symaira-desktop/crates symaira-eraseme/crates symaira-vault/crates symbrowse/crates symaira-brain | head
```

No matches. `symaira-browse` — the only DOM consumer — is still Go, and its Rust
port has not reached the DOM slice. **Verdict: deferred — no Rust consumer.**

## RUST-012 — TurboQuant codec and performance slice (`VEC-*`, `PERF-003`) — deferred

```sh
grep -rln --include=*.rs -iE "turboquant|vector_quant|quantiz" \
  symaira-desktop/crates symaira-eraseme/crates symaira-vault/crates symbrowse/crates symaira-brain | head
```

`symaira-brain/rust/symbrain-memory` carries vector storage and retrieval with
quantization (`src/store.rs`, `src/retrieval.rs`, `src/search_rows.rs`,
`src/schema.rs`). `symaira-desktop` matches only on unrelated similarity and
retention code (`symdesk-core/src/simhash.rs` is text simhash, not a vector
codec). **Verdict: deferred — one consumer; re-assess when a second Rust
consumer needs the codec.**

## Re-assessment rule

Re-run the searches above (or their equivalents) before starting any of these
slices. A slice leaves `deferred` only when the search finds two Rust consumers
that need it and a duplication the shared module removes; record the hits here
and update `demand_evidence`/`status` in the same change.
