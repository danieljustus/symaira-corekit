# symaira-corekit

Shared Go library for the Symaira public-core tools (`symvault`, `symmemory`, `symseek`, `symfetch`, `symscope`).

Bundles domain-free infrastructure that is otherwise duplicated across tools: MCP server scaffold, TOML config loading, exit codes, logging, path safety, SQLite setup, and update checking.

Although `corekit` is a Go library, its conventions also guide the non-Go free tools (`symoperate`, `symtune`, `symterminal`, `symeraseme`). See [`docs/cross-language-conventions.md`](docs/cross-language-conventions.md) for the shared contracts that apply across languages.

## Standalone-First Contract

Corekit is a shared foundation, not a runtime dependency graph between products.
Consumers must keep working when every other Symaira tool is absent. Optional
cross-tool behavior belongs behind runtime detection and fallback in the
consumer, not as imports from sibling tool repositories.

Corekit must stay free of Vault crypto, Memory PII policy, Seek ranking, Fetch
fingerprinting, Scope port scanning, Pro billing, Firebase, Stripe, GCP SDKs,
and other product- or cloud-specific behavior.

## Packages

| Package | Purpose |
|---------|---------|
| `exitcodes` | Typed exit codes (`ExitOK`, `ExitError`, `ExitUsage`, `ExitAuth`) and `CLIError` type |
| `logkit` | Structured logging (`log/slog`) to stderr, configurable via `SYM<APP>_LOG_LEVEL` |
| `envutil` | Safe environment variable access with alias support |
| `fsutil` | Atomic file writes, path traversal validation, temp-file safety |
| `configkit` | TOML config loader with XDG paths, project overrides, and env vars |
| `evidencekit` | Grounded extraction contract (`SourceRef`, `Span`, `Extraction`, `AlignmentStatus`), JSONL sidecar encode/decode, exact/normalized text-span alignment, and grounded-only validation |
| `mcpserver` | Generic JSON-RPC 2.0 stdio server for MCP tool registration |
| `sqlitekit` | `modernc.org/sqlite` wrapper with WAL mode and embedded migrations |
| `updatecheck` | GitHub release checker (opt-in, max 1×/24h) |
| `vectorkit/turboquant` | CGO-free TurboQuant scalar vector quantization: deterministic rotation, packed encode/decode, inner-product/cosine scoring, sidecar metadata, benchmarks |
| `versionkit` | Standardized handshake payload (`{tool, version, schema_version}`) for CLI tools |

## Usage

```go
import "github.com/danieljustus/symaira-corekit/logkit"

// Reads MYAPP_LOG_LEVEL (debug|info|warn|error, default warn) and
// MYAPP_LOG_FORMAT (text|json, default text) from the environment.
logger := logkit.NewFromEnv("myapp")
logger.Info("started", "version", "1.0.0")
```

## Versioning

Strict SemVer. Each tool pins its corekit version in `go.mod`.

## License

Apache-2.0 — Daniel Justus
