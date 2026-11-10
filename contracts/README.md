# Cross-language contract fixtures

This directory holds the language-neutral fixtures for the contracts documented in
[`../docs/cross-language-conventions.md`](../docs/cross-language-conventions.md). They
turn prose claims into data that both this repo's Rust tests and its Swift
package tests (`appkit/`) assert against, so a divergence between the two
implementations of the same contract fails a build instead of going unnoticed.

## Files

| File | Covers |
|---|---|
| `exit_codes.json` | The canonical CLI exit-code table (`corekit/exitcodes`) |
| `update_check_invariants.json` | The update-check contract (`corekit/updatecheck`), twinned by `SymairaUpdateCheck` in `appkit/` |
| `config_paths.json` | XDG-style config/cache/data path conventions (`corekit/configkit`) |
| `json_encoding.json` | JSON key casing and stdio transport rules for MCP servers (`corekit/mcpserver`) |
| `mcp_tool_errors.json` | Structured error metadata on a failed `tools/call` (`corekit/mcpserver.ToolErrorData`) |
| `mcp_tool_annotations.json` | MCP tool annotation fields and defaults (`corekit/mcpserver`) |
| `secret_refs.json` | Shared secret-reference schemes and resolver behavior (`corekit/secretref`) |
| `llm_providers.json` | Shared LLM provider descriptor registry (`llm-provider-contract.md`, issue #172); consumed by `symaira-core-llm` (via the generated `llmkit/providers.json`) and `SymairaProviderKit` in `appkit/` |
| `llm_errors.json` | Shared LLM provider error taxonomy mapped to exit codes (`llm-provider-contract.md`) |

## Schema

Each file is a single JSON object or array; there is no wrapper envelope. Field
names are `snake_case` and are considered part of the schema — renaming a field
is a breaking change to this schema, not just to the fixture content.

## Compatibility policy

- **Additive changes** (a new field, a new exit code, a new fixture file) may
  land in a corekit minor release.
- **A semantic change to an existing field's meaning, or a field removal,**
  is a breaking change to the fixture schema and must be called out in
  `CHANGELOG.md` under its own heading so Swift and Rust consumers can react
  deliberately rather than silently drifting.
- Consumers should pin to a corekit tag (per the exact-pin policy in the
  workspace `AGENTS.md`) and re-vendor these files deliberately on bump,
  not fetch them live from `main`.

## Who reads these

- The Rust crates assert against a byte-identical copy in
  `rust/test-support/symaira-contract-fixtures/fixtures/contracts/` (hash-anchored
  in `scripts/rust-port/frozen_core_anchors.py`; `make rust-fs-secret-frozen-contract`
  also compares `secret_refs.json` byte for byte). The retired Go packages
  asserted the same files up to v0.18.3.
- The Swift package tests (`appkit/Tests/*/ContractFixtureTests.swift`) read
  these files directly from this directory since the AppKit merge (ADR 0006);
  the former vendored copy (danieljustus/symaira-appkit#105) is gone.
  `SymairaProviderKit` keeps a bundled `llm_providers.json` resource whose test
  asserts equality with this file.
