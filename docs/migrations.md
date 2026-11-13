# Migration notes

What a consumer needs to check when moving its pinned `corekit` version
forward, one minor release at a time. Each entry summarizes the actual
release content (see the linked GitHub release for the full changelog) and
calls out anything a consumer should verify — not just what was added.

The current API contract is strict SemVer within a major version. Entries
also preserve historical removals, including `embedkit` in v0.12.0; those
require migration. Otherwise "check" means a new capability to adopt or a
behavior change worth confirming.

## v0.22.2

- **Swift consumers:** move the pin to `exact: "0.22.2"` (XcodeGen
  `exactVersion: 0.22.2`). No API change on macOS and iOS. On tvOS every
  `SymairaSpacing`, `SymairaRadius`, `SymairaMetrics` and bundled font size
  doubles (`SymairaMetrics.platformScale`); check fixed frames in tvOS views
  that were sized by hand against the old scale.
- **Rust consumers:** no change; moving the revision is optional.

## v0.22.1

- **Swift consumers:** move the pin to `exact: "0.22.1"` (XcodeGen
  `exactVersion: 0.22.1`). No API change. Check:
  - The topography looks as before; it now costs about a seventh of the GPU
    time per frame, and ripples run at the display rate. Not measured on a
    physical iPhone.
  - On iOS `SymairaSettingsButton` shows the gear instead of the word
    "Settings". Product toolbar buttons with a `SymairaIcon` need
    `Label { Text(title) } icon: { Image(symairaIcon:) }` on iOS (IOS-6).
- **Rust consumers:** no API change. Consumers of `symaira-core-llm` or
  `symaira-core-update` resolve `quinn-proto` and `quinn-udp` in their own
  lockfile; update them to 0.11.19 and 0.5.16 (RUSTSEC-2026-0523, -0524,
  -0538), for example with `cargo update -p quinn-proto -p quinn-udp`.

## v0.22.0

- **Swift consumers:** move the pin to `exact: "0.22.0"` (XcodeGen
  `exactVersion: 0.22.0`). Check:
  - New `SymairaStatTile` for dashboard summary values; replace local stat
    tiles with it.
  - The empty `SymairaProgressStyle` track is now `raised` with a 1 pt `line`
    outline instead of `ink3`. Review meters at 0 % in light and dark; pass
    `track:` to `SymairaProgressStyle.init` only for a deliberate exception.
  - On iOS and tvOS `SymairaTopoView` renders through `CAMetalLayer` with a
    `CADisplayLink` instead of a SwiftUI `TimelineView`. Confirm the
    background still pauses with Reduce Motion, Low Power Mode and a
    backgrounded scene in the app. Not measured on a physical iPhone.
- **Rust consumers:** after moving the CoreKit revision:
  - The workspace requires `serde_json = "1.0.151"` as a caret range, so a
    consumer workspace may resolve newer 1.0.x releases (#475).
  - `symaira-core-mcp` keeps answering `ping`, `tools/list` and protocol
    errors while 16 tool calls run; further calls queue in arrival order (up
    to 1024). Result objects and input schemas are always written with sorted
    keys, also when the consumer build enables `serde_json/preserve_order`.
    Recorded MCP transcripts from such a build change key order (#480).
  - [`docs/rust-port/go-compatibility.md`](rust-port/go-compatibility.md)
    lists the differences from the retired Go library that are intended; no
    Go-compatibility modes are planned.

## v0.21.0

- **Swift consumers:** move the pin to `exact: "0.21.0"` (XcodeGen
  `exactVersion: 0.21.0`). Check:
  - New `SymairaIcon` cases `operate`, `restart`, `memory`, `battery`,
    `keepAwake`, `expired` and `externalDrive` replace local SF Symbol
    stand-ins (Brain: `hand.tap`, `restart.circle`; Cockpit: memory, battery,
    keep-awake, expired-credential and external-drive rows). Battery level and
    charging variants are not available yet.
  - `SymairaSwitchToggleStyle` now honors `.labelsHidden()`. Remove
    `Toggle(isOn:) { EmptyView() }` workarounds inside `SymairaFormRow`. On
    macOS 14, iOS 17 and tvOS 17 the style falls back to the native toggle.
  - Use `Image(symairaIcon:)` for `Menu` labels (rule ICON-4); `gui-review.py`
    now warns on `SymairaIconView` inside a `Menu` label.
  - The package declares tvOS 17; `SymairaTheme` and `SymairaKeychain` build
    for tvOS. Process-execution modules stay macOS-only.
- **Rust consumers:** `symaira-core-fs` and `symaira-core-secretref` require
  `rustix = "1.1.6"` as a caret range instead of `=1.1.4`. After moving the
  CoreKit revision, a consumer workspace may select any rustix 1.x ≥ 1.1.6.
  `symaira-core-version` still pins `serde_json = "=1.0.151"` (#475).

## v0.20.0

- **Swift consumers of the former `symaira-appkit`:** the package now lives in
  CoreKit (ADR 0006). In one change per consumer:
  - `Package.swift`: `.package(url: "https://github.com/danieljustus/symaira-corekit.git", exact: "0.20.0")`
    and `.product(name: "<Product>", package: "symaira-corekit")`.
  - XcodeGen `project.yml`: package key `symaira-corekit`,
    `url: https://github.com/danieljustus/symaira-corekit.git`,
    `exactVersion: 0.20.0`, and `package: symaira-corekit` in every dependency.
  - Packaging scripts: copy `symaira-corekit_SymairaTheme.bundle` instead of
    `symaira-appkit_SymairaTheme.bundle`.
  - Review `appkit/CHANGELOG.md` for every AppKit release between the old pin
    and 0.18.1; 0.20.0 has no Swift source change beyond the bundle name.
  - Pins at the time of the merge: Brain, Learning, EraseMe 0.18.1; HQ 0.18.0;
    Cockpit 0.17.1 (tuning XcodeGen 0.15.1); Brain scope/operate 0.15.1;
    Watch 0.14.2; Desktop and its room/meet packages 0.14.0 (meet XcodeGen
    0.7.0, ingest client 0.2.0); Vault client 0.10.0.
- Rust consumers: no API change. `symaira-core-sqlite` uses `rusqlite` 0.41.1
  (RUSTSEC-2026-0459). Cargo now also fetches the `appkit/` sources with the
  Git dependency; nothing else changes.

## v0.19.0

- The Go module is no longer developed on `main`. Go consumers: stay on
  `v0.18.x`; do **not** move to a later tag, which contains no Go packages.
  Go fixes arrive as `v0.18.N` tags from `release/v0.18`.
- Rust consumers: pin an exact CoreKit Git revision plus `Cargo.lock`
  (ADR 0002). The removed Go-only packages (`auditkit`, `evidencekit`,
  `domkit`, `vectorkit/turboquant`, `ollamakit`) have no shared Rust crate;
  keep a consumer-local implementation.

## v0.18.3

- `mcpserver`: a Unix stdout write failure no longer leaves `ServeIO` blocked
  on an inherited stdin. No API change.
- Security updates for `golang.org/x/net` (v0.62.0; `domkit` HTML parsing and
  rendering) and `golang.org/x/sys` (v0.49.0), plus a `toolchain go1.26.9`
  line in `go.mod`; the `go 1.26.4` minimum is unchanged. Build consumers with
  Go 1.26.10 or newer to pick up the GO-2026-6809 standard-library fix.

## v0.18.2

- `mcpserver`: restores the v0.17 `ServeIO` result when the caller cancels
  while in-flight tool calls drain after input EOF (`context.Canceled` instead
  of `nil`). No API change; consumers on v0.18.0 or v0.18.1 should take this
  patch.

## v0.18.1

- `mcpserver`: fixes a v0.18.0 regression where `ServeIO` stopped reading after
  the first malformed or invalid JSON-RPC request. No API change; consumers on
  v0.18.0 should take this patch.

## v0.18.0

- `configkit`: explicitly present TOML `false`, `0` and `""` values now
  override earlier sources and defaults, and an explicitly set empty string
  environment variable clears a string field. An unset variable still leaves
  the field alone.
- `mcpserver`: stricter stdio transport. Oversized frames and malformed
  JSON-RPC envelopes, IDs, params or framing headers are rejected; write
  failures are propagated.
- `updatecheck`: redirects to non-HTTPS URLs are refused, and
  `CheckWithForce(true)` also bypasses the persistent cache.
- Consumer action: before raising the exact `corekit` pin, review configuration
  that relied on zero values being skipped (Symaira Desktop's
  `TestTOMLFalseValueIgnored` asserts the old behavior and must change with
  the pin). Confirm MCP clients send well-formed JSON-RPC frames.

## v0.17.0

- `mcpserver`: a failed `tools/call` publishes its structured error under the
  tool result's `_meta` key `symaira.dev/tool_error` — `code`, `message`,
  `retryable`, `requires_confirmation`, `resume_hint`, `hint`, `details` —
  derived from optional interfaces on the returned error (`ErrorCode`,
  `RetryableError`, `RequiresConfirmation`, `ResumeGuidance`, `ErrorHint` or
  `Hint`, `ErrorDetails`), resolved through `errors.As`. A tool failure remains
  an `isError` result rather than a JSON-RPC error object. Pinned as
  `contracts/mcp_tool_errors.json`.
- Consumer action: raise the exact `corekit` pin. Nothing to migrate — an error
  implementing none of the interfaces produces no `_meta` and its result stays
  byte-identical. A consumer whose errors already carry this metadata gets the
  fields on the wire by adding the matching methods, and can stop rendering
  them into the message text.

## v0.16.3

- `updatecheck/updateapply`: `Applier.ValidateBinary` optionally validates the
  installed executable after the swap and before the rollback backup is
  removed. Returning an error restores the previous binary; when no previous
  binary exists, the failed installation is removed.
- Consumer action: set `ValidateBinary` when the installed executable must pass
  a startup check such as `--version`. Consumers that do not set the hook need
  no migration.

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

## v0.16.2

- `secretref`: adds the shared Go resolver for `symvault://`, `keychain://`,
  `env://`, and bare environment-variable references, including a default
  subprocess timeout and the documented fallback behavior. Existing
  `llmkit.ResolveCredential` callers remain compatible through its deprecated
  forwarder.
- `mcpserver`: publishes the cross-language MCP tool-annotation contract and
  conformance tests.
- Consumer action: raise the exact `corekit` pin. Consumers adopting
  `secretref` should use its package path rather than copying resolver logic;
  no migration is required for consumers that do not adopt it.

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

## v0.12.0

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

The former `embedkit` package was removed in this release. Consumers still
importing it must remove or migrate those imports before raising their pin.

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.12.0)

## v0.11.0

- New `auditkit` package provides shared tamper-evident SHA-256-chain audit
  logging, checkpoints and verification.
- Consumer action: existing imports remain unchanged; adopt `auditkit` only
  where a shared audit sink is needed.

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.11.0)

## v0.10.0

- New `mcpcfgkit` package discovers MCP server configuration across local AI
  clients and resolves configured commands.
- Consumer action: existing imports remain unchanged; consumers can replace
  duplicated MCP configuration discovery with this package.

[Release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.10.0)

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
