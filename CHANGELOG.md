# Changelog

The GitHub Releases page is the authoritative source for complete release notes.

## v0.16.3 — 2026-08-31

- `updatecheck/updateapply`: added the optional `Applier.ValidateBinary` hook
  for post-swap executable validation. A failed validation restores the previous
  binary, or removes the failed installation when no previous binary exists.
- Consumer action: configure `ValidateBinary` when the installed executable
  must pass a startup check such as `--version`; consumers that do not set it
  retain the existing behavior.

## v0.16.1 — 2026-08-29

- `configkit`: honors `XDG_CONFIG_HOME` by default, with an explicit legacy-path opt-out.
- `updatecheck`: persists its once-per-24-hour cache across checker instances.
- `ollamakit`: delegates Ollama transport to `llmkit` while preserving the compatibility API.
- `auditkit`: fingerprints checkpointed logs and validates the chain during recovery.
- Consumer action: update the exact `corekit` pin; existing APIs remain compatible.

## v0.16.2 — 2026-08-30

- `secretref`: added the shared Go resolver for `symvault://`, `keychain://`,
  `env://`, and bare environment-variable references, with a default
  subprocess timeout and documented fallback behavior. Existing
  `llmkit.ResolveCredential` callers remain compatible through its deprecated
  forwarder.
- `mcpserver`: published the cross-language MCP tool-annotation contract and
  conformance tests.
- Consumer action: update the exact `corekit` pin; consumers adopting
  `secretref` should use the package instead of maintaining a local resolver.

## v0.16.0 — 2026-08-26

- `llmkit`: added `WithStreamFinished` for provider terminal finish/stop reasons, `WithAPIKey` for consumers that resolve credentials in their own secret store, and `WithEmbedDimensions` for Matryoshka embedding dimension pinning (#187).
- Consumer action: update the `corekit` pin and adopt these options where needed; existing `llmkit` calls remain compatible and require no code change.

See the [v0.16.0 release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.16.0).

## v0.15.0 — 2026-08-26

- `llmkit`: added `ChatOptions.ResponseFormat` for OpenAI-wire structured output and the additive `WithGenerateSystem` / `WithGenerateFormat` options for native Ollama generation (#186).
- Consumer action: update the `corekit` pin and pass the new options when structured output is required; existing calls remain compatible and require no migration.

See the [v0.15.0 release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.15.0).

## v0.14.0 — 2026-08-26

- `llmkit`: added the shared provider layer with descriptor-driven OpenAI-compatible and Anthropic transports, streaming, tool use, embeddings, model discovery, credential references, and a contract error taxonomy (#179–#184).
- `ollamakit`: became a thin deprecated shim as Ollama support moved into the `llmkit` provider descriptors (#180).
- Consumer action: update the `corekit` pin; existing `ollamakit` consumers can migrate incrementally, while new provider integrations should use `llmkit` and plan to leave the deprecated shim before its removal.

See the [v0.14.0 release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.14.0).

## v0.13.0 — 2026-08-26

- `configkit`, `exitcodes`, and `updatecheck`: added cross-language contract fixtures and Go conformance tests for config paths, exit codes, update-check invariants, and JSON encoding/stdio rules (#170).
- Consumer action: no Go API migration is required; consumers maintaining Swift or Python ports should use `contracts/*.json` as the shared behavior reference and verify their implementations against it.

See the [v0.13.0 release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.13.0).

## v0.12.1 — 2026-08-25

- `sqlitekit`: updated the shared pure-Go SQLite dependency from `modernc.org/sqlite` 1.56.0 to 1.57.0 (#162).
- Documentation and repository hygiene were updated, including the shared README structure and linked changelog (#167, #169); no runtime package API changed.
- Consumer action: update the `corekit` pin and run SQLite-related tests; no source migration is required, and documentation-only and CI-maintenance changes require no consumer action.

See the [v0.12.1 release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.12.1).

## v0.12.0 — 2026-08-24

See the [v0.12.0 release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.12.0).

[View all releases](https://github.com/danieljustus/symaira-corekit/releases).
