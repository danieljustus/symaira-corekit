# Migration notes

What a consumer needs to check when moving its pinned `corekit` version
forward, one minor release at a time. Each entry summarizes the actual
release content (see the linked GitHub release for the full changelog) and
calls out anything a consumer should verify — not just what was added.

Strict SemVer within a major version means these are additive/non-breaking
by contract; "check" below means "new capability you may want to adopt or a
behavior change worth confirming," not "your build will fail."

## v0.16.1

- `configkit`: global configuration now honors `$XDG_CONFIG_HOME`; set
  `Options.UseLegacyConfigPath` while migrating from the former `~/.config`
  location.
- `updatecheck`: the once-per-24-hour timestamp and release result persist in
  the XDG cache directory; set `Checker.CachePath` for an application-specific
  location.
- `ollamakit`: remains available as a deprecated compatibility package, with
  HTTP transport delegated to `llmkit`; new code should use `llmkit` directly.
- `auditkit`: checkpointed logs include a size and content fingerprint. Recovery
  uses the fast path only when both match and otherwise validates the hash chain
  while replaying. Existing checkpoints safely fall back to replay.
- Consumer action: raise the exact `corekit` pin; no migration is required for
  consumers that do not adopt the new options.

## v0.16.0

- `llmkit`: `StreamChat` accepts `WithStreamFinished` to receive the provider's terminal finish/stop reason; `WithAPIKey` lets consumers supply a credential resolved by their own keychain or vault; `Embed` accepts `WithEmbedDimensions` for OpenAI-wire Matryoshka dimension pinning.
- Consumer action: raise the `corekit` pin and adopt these options where needed. Existing `llmkit` calls remain compatible, so no source migration is required for consumers that do not need them.

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.16.0)

## v0.15.0

- `llmkit`: `ChatOptions.ResponseFormat` carries an OpenAI-wire `response_format`; native `Generate` calls accept `WithGenerateSystem` and `WithGenerateFormat` for system prompts and JSON-schema-constrained output.
- Consumer action: raise the `corekit` pin and pass these options when structured output is needed. Existing calls remain compatible; no migration is required otherwise.

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.15.0)

## v0.14.0

- `llmkit`: new shared provider package with descriptor-driven OpenAI-compatible and Anthropic transports, streaming, tool use, embeddings, model discovery, credential references, and the documented provider error taxonomy.
- `ollamakit`: now a thin deprecated shim because Ollama support is represented by `llmkit` provider descriptors.
- Consumer action: raise the `corekit` pin. Existing `ollamakit` users can migrate incrementally; new provider integrations should use `llmkit` and plan to leave the deprecated shim before removal.

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.14.0)

## v0.13.0

- `configkit`, `exitcodes`, and `updatecheck`: cross-language contract fixtures and Go conformance tests now cover config paths, exit codes, update-check invariants, and JSON encoding/stdio rules.
- Consumer action: no Go API migration is required. Consumers maintaining Swift or Python ports should use `contracts/*.json` as the shared behavior reference and verify their implementations against it.

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.13.0)

## v0.12.1

- `sqlitekit`: the shared pure-Go SQLite dependency moved from `modernc.org/sqlite` 1.56.0 to 1.57.0.
- Documentation and repository hygiene changed the README structure and linked changelog; no runtime package API changed.
- Consumer action: raise the `corekit` pin and run SQLite-related tests. No source migration is required; documentation-only and CI-maintenance changes require no consumer action.

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.12.1)

## v0.9.1 → v0.9.2

- `updatecheck` exports the hardened HTTP client that was previously internal:
  `NewSecureClient()` (TLS 1.3 minimum, `DefaultAPITimeout`, redirects refused
  off GitHub hosts) and `NewSecureClientWithTimeout(d)` for downloads, plus the
  `DefaultAPITimeout` / `DefaultDownloadTimeout` constants. This is additive.
- `updateapply` and `updatecheck/cosign` now default to that hardened client
  instead of `http.DefaultClient`, so asset, checksum, signature and
  certificate downloads get a request timeout, a TLS floor and a redirect
  policy. Consumers that relied on the previous unbounded default — for
  example an internal mirror behind a redirect to a non-GitHub host — must set
  `Applier.HTTPClient` / `cosign.Config.HTTPClient` explicitly.
- `updatecheck/cosign`: the default certificate identity regexp was
  double-escaped and could never match a real Sigstore identity, so cosign
  verification always failed for consumers that did not set `IdentityRegexp`
  themselves. It now matches, is anchored, and escapes the repo slug.
  Consumers that worked around this with a hand-written `IdentityRegexp` can
  drop the override; verify once before removing it.
- `updatecheck/cosign`: signature and certificate responses are size-capped.

## v0.8.0 → v0.9.0

- `embedkit` gained provider abstractions, a deterministic hash fallback,
  configurable result caching, and dimension pinning. Consumers adopting
  these features should persist the provider/model, dimension, and
  quantization metadata together so `SameSpace` continues to reject
  incompatible vectors.
- New `domkit` package provides a shared semantic DOM pipeline for schema,
  selector, image, truncation, and markdown extraction. Consumers that had
  local extraction helpers can migrate incrementally; the exported
  string-based helpers remain available for direct callers.
- `ollamakit` continues to support streamed generation/chat and model
  discovery while exposing the embedding dimension option used by
  `embedkit` providers. Existing calls with a zero dimension are unchanged.

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.9.0)

## v0.9.0 → v0.9.1

- `configkit`: fixed a data race in the `Loader` cache when `Reload` /
  `ResetCache` run concurrently with reads. Consumers that periodically
  reload configuration should update; behavior is otherwise unchanged.
- `updateapply`: the cosign signature is now verified over the exact
  checksum bytes that are installed (previously the signature could be
  checked against a differently-ordered byte slice). Consumers with
  `CosignConfig` enabled should re-verify their own signatures against
  the exact bytes.
- `mcpserver`: JSON-RPC notifications are honored (no responses emitted,
  `ping` supported) and typed tool results with request metadata are
  preserved. Consumers relying on prior (malformed) notification
  handling can drop workarounds.

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.9.1)

## v0.7.0 → v0.8.0

- `mcpserver`: `ToolAnnotations` for MCP tool-behaviour hints; fixed
  structured tool results that violated the MCP `TextContent` schema — if a
  consumer works around malformed tool results today, that workaround can be
  dropped.
- Community health files and Dependabot config added; no API impact.

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.8.0)

## v0.6.0 → v0.7.0

- `evidencekit`: fuzzy-alignment fallback and sentinel errors — consumers
  doing exact-only span alignment may want the fallback path.
- `mcpserver`: `RegisterTyped` generic helper deriving `InputSchema` from Go
  types — optional adoption, no forced migration.
- CI: `apidiff` API-compatibility check added to this repo's own pipeline
  (does not affect consumers directly).

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.7.0)

## v0.5.0 → v0.6.0

- `updatecheck/updateapply` gained optional hardening: `CosignConfig`
  (keyless signature verification), `ExtractBinary` (tar.gz/zip extraction),
  `CheckInstallMethod` (Homebrew / `go install` / package-manager detection).
  All additive — a consumer not opting into these fields keeps prior
  behavior unchanged.
- `updatecheck` semantics documented as a cross-language (Go ↔ Swift)
  convention: cache TTL, SemVer handling, dev/prerelease skip, non-blocking
  guarantee, error behavior. Worth a read if a non-Go tool reimplements
  update checking against this contract.

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.6.0)

## v0.4.4 → v0.5.0

- New `updatecheck/updateapply` package: self-update apply step (download,
  checksum verification, atomic swap with rollback, re-exec). New package —
  no migration needed unless adopting self-update.

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.5.0)

## v0.3.0 → v0.4.0

- New `evidencekit` package: grounded extraction contract (`SourceRef`,
  `Span`, `Extraction`, `AlignmentStatus`), JSONL sidecar encode/decode,
  exact/normalized text-span alignment, grounded-only validation. New
  package — no migration needed unless adopting it.

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.4.0)

## Before v0.3.0

`versionkit` (the `{tool, version, schema_version}` handshake payload
consumed by `symaira-appkit`'s `SymairaToolKit`) shipped in v0.3.0 itself —
see the [v0.3.0 release](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.3.0).
Everything at v0.1.0–v0.2.1 predates the package-introduction tracking in
the [README package table](../README.md#packages); consult
`git log --follow` on the package in question if older history is needed.
