# Agent Instructions — symaira-corekit

This repository is the public Apache-2.0 licensed shared library for Symaira public-core tools.

## Ecosystem Guidance

- Before changing cross-tool integrations, shared conventions, or product
  boundaries, read `../docs/00-MASTERPLAN.md` and `../ECOSYSTEM.md`.
- Keep the standalone-first contract: this library must not make any consumer
  require another Symaira tool at build time or startup.

## Repository Role

- Provide domain-free infrastructure packages that are shared across `symvault`, `symmemory`, `symseek`, `symfetch`, and `symscope`.
- Every package must be independently usable and testable.
- This library is the public counterpart to private `symaira-prokit` (which contains SaaS/cloud primitives).
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

## Key Dependencies

- `github.com/BurntSushi/toml` — TOML config parsing
- `github.com/spf13/cobra` — not used here (tool-specific)
- `modernc.org/sqlite` — pure-Go SQLite (CGO-free)
- `log/slog` — structured logging (stdlib)
