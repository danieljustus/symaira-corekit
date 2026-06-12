# symaira-corekit

Shared Go library for the Symaira public-core tools (`symvault`, `symmemory`, `symseek`, `symfetch`).

Bundles domain-free infrastructure that is otherwise duplicated across tools: MCP server scaffold, TOML config loading, exit codes, logging, path safety, SQLite setup, and update checking.

## Packages

| Package | Purpose |
|---------|---------|
| `exitcodes` | Typed exit codes (`ExitOK`, `ExitError`, `ExitUsage`, `ExitAuth`) and `CLIError` type |
| `logkit` | Structured logging (`log/slog`) to stderr, configurable via `SYM<APP>_LOG_LEVEL` |
| `envutil` | Safe environment variable access with alias support |
| `fsutil` | Atomic file writes, path traversal validation, temp-file safety |
| `configkit` | TOML config loader with XDG paths, project overrides, and env vars |
| `mcpserver` | Generic JSON-RPC 2.0 stdio server for MCP tool registration |
| `sqlitekit` | `modernc.org/sqlite` wrapper with WAL mode and embedded migrations |
| `updatecheck` | GitHub release checker (opt-in, max 1×/24h) |

## Usage

```go
import "github.com/danieljustus/symaira-corekit/logkit"

logger := logkit.Setup("myapp")
logger.Info("started", "version", "1.0.0")
```

## Versioning

Strict SemVer. Each tool pins its corekit version in `go.mod`.

## License

MIT — Daniel Justus
