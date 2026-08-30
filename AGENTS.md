# Agent Instructions — symaira-corekit

This repository is the public Apache-2.0 licensed shared library for Symaira public-core tools.

## Ecosystem Guidance

- Before changing cross-tool integrations, shared conventions, or product
  boundaries, read `../docs/00-MASTERPLAN.md` and `../ECOSYSTEM.md`.
- Keep the standalone-first contract: this library must not make any consumer
  require another Symaira tool at build time or startup.

## Repository Role

- Provide domain-free infrastructure packages shared across the Symaira Go products: `symvault`, `symdesk` (incl. its nested `ingest`/`print`/`seek`/`relate`/`room` modules), `symbrain` (incl. its nested `guard` module and the absorbed memory/skills packages), `symbrowse`, `symfritz`, and `symvibe`.
- Packages: `mcpserver`, `configkit`, `logkit`, `exitcodes`, `fsutil`, `envutil`, `sqlitekit`, `updatecheck`, `ollamakit`, `domkit`, `embedkit`, `evidencekit`, `vectorkit`, `versionkit`, `llmkit` (incl. its nested `gen` generator), `secretref`.
- Every package must be independently usable and testable.
- Preserve standalone-first behavior for every consumer. Corekit may provide reusable helpers and conventions, but it must never make any public tool require another Symaira tool at build time or startup.

## Build & Test

```bash
make build              # go build ./...
make test               # go test -race ./...
make lint               # gofmt -l + go vet
```

## Architecture & Constraints

- **100% CGO-free**: `CGO_ENABLED=0` must work for linux/darwin/windows (amd64+arm64).
- **Zero Stdio Pollution**: MCP server transport runs over stdio. Never print to `os.Stdout` except structured JSON-RPC 2.0 messages.
- **No Cloud/SaaS concepts**: No Firebase, Stripe, GCP SDK, or billing code. This is a public Apache-2.0 library.
- **No tool-specific business logic**: No vault crypto, no memory PII rules, no seek ranking, no fetch fingerprinting, no scope port scanning.
- **No cross-tool coupling**: Do not import `symaira-vault`, `symaira-memory`, `symaira-seek`, `symaira-fetch`, `symaira-scope`, or any of their `internal/` packages. Optional integrations must remain runtime contracts implemented by consumers.
- **Cross-language conventions**: `corekit` is Go, but its conventions (exit codes, XDG paths, env var naming, MCP stdio framing, zero stdout pollution) also guide the Swift and Python free tools. See `docs/cross-language-conventions.md`.
- **Strict SemVer**: API stability guaranteed within major versions. Consumers pin versions in `go.mod`.
- **GUI handshake contract (`versionkit`)**: every core's `version --json` subcommand must emit the `versionkit.Info` payload (`{tool, version, schema_version}`). symaira-appkit's `SymairaToolKit` performs its schema handshake against exactly these field names — never rename them. Bump the tool's `schema_version` whenever its machine-readable JSON output changes incompatibly. The plain `version` output should match `Info.String()` ("tool vX.Y.Z") so appkit's fallback parser keeps working.

## Consumer Bump Ownership

The exact-pin policy (each consumer pins an exact corekit version in its
`go.mod`, per the workspace `AGENTS.md`) is deliberate and stays. What
previously went missing is *raising* those pins after a release — nobody
owned it, so shipped work sat unused in consumers for multiple minor
versions. `danieljustus/symaira-corekit#157` found four consumers three-plus
releases behind.

- **Who bumps:** the corekit maintainer (@danieljustus) bumps every listed
  consumer's pinned version, one PR per consumer, verified by that
  consumer's own test suite.
- **Trigger:** within two weeks of a corekit minor/patch release, or
  immediately before cutting a consumer's own release — whichever comes
  first.
- **Follow-up mechanism:** `.github/workflows/consumer-pin-drift.yml` checks
  every consumer in `docs/consumers.json` against the latest corekit release
  (on every corekit release, and monthly on a schedule) and opens or updates
  a single tracking issue titled `Consumer pin drift: vX.Y.Z` when any of
  them lag. See that workflow's header comment for the required
  `CONSUMER_READ_TOKEN` secret setup — it degrades to a logged warning
  rather than failing CI when the secret is absent.
- Add new consumers to `docs/consumers.json` when they start depending on
  corekit; remove or update entries when a consumer is archived, renamed, or
  its `go.mod` moves.

## Key Dependencies

- `github.com/BurntSushi/toml` — TOML config parsing
- `github.com/spf13/cobra` — not used here (tool-specific)
- `modernc.org/sqlite` — pure-Go SQLite (CGO-free)
- `log/slog` — structured logging (stdlib)
