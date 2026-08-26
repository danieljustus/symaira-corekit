# Cross-language contract fixtures

This directory holds the language-neutral fixtures for the contracts documented in
[`../docs/cross-language-conventions.md`](../docs/cross-language-conventions.md). They
turn prose claims into data that both this repo's Go tests and
`symaira-appkit`'s Swift tests can assert against, so a divergence between the two
implementations of the same contract fails a build instead of going unnoticed.

## Files

| File | Covers |
|---|---|
| `exit_codes.json` | The canonical CLI exit-code table (`corekit/exitcodes`) |
| `update_check_invariants.json` | The update-check contract (`corekit/updatecheck`), twinned by `SymairaUpdateCheck` in appkit |
| `config_paths.json` | XDG-style config/cache/data path conventions (`corekit/configkit`) |
| `json_encoding.json` | JSON key casing and stdio transport rules for MCP servers (`corekit/mcpserver`) |
| `llm_providers.json` | Shared LLM provider descriptor registry (`llm-provider-contract.md`, issue #172); consumed by Go `llmkit` and appkit `SymairaProviderKit` |
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
  `CHANGELOG.md` under its own heading so appkit's consumer can react
  deliberately rather than silently drifting.
- Consumers should pin to a corekit tag (per the exact-pin policy in the
  workspace `AGENTS.md`) and re-vendor these files deliberately on bump,
  not fetch them live from `main`.

## Who reads these

- `exitcodes/contract_test.go`, `updatecheck/contract_test.go`, and
  `configkit/contract_test.go` in this repo assert the Go implementation
  against these fixtures.
- `symaira-appkit`'s CI consumes a vendored copy at a pinned corekit revision
  (see danieljustus/symaira-appkit#105) and asserts the Swift implementation
  against the same data.
