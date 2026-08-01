# Migration notes

What a consumer needs to check when moving its pinned `corekit` version
forward, one minor release at a time. Each entry summarizes the actual
release content (see the linked GitHub release for the full changelog) and
calls out anything a consumer should verify — not just what was added.

Strict SemVer within a major version means these are additive/non-breaking
by contract; "check" below means "new capability you may want to adopt or a
behavior change worth confirming," not "your build will fail."

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
