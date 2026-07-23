# Cross-Language Conventions for Symaira Free Tools

`symaira-corekit` is a Go library, but the conventions it encodes apply to all
free/public Symaira tools regardless of implementation language. This document
captures the shared contracts that keep the ecosystem consistent.

## Tool Inventory

| Tool | Language | Imports corekit | Notes |
|------|----------|-----------------|-------|
| `symvault` | Go | yes | Wraps some corekit packages in `internal/` adapters |
| `symmemory` | Go | yes | Direct consumer |
| `symseek` | Go | yes | Direct consumer |
| `symfetch` | Go | yes | Direct consumer |
| `symscope` | Go | yes | Direct consumer |
| `symoperate` | Swift | no | macOS GUI automation |
| `symtune` | Swift | no | macOS hardware tuning |
| `symterminal` | Swift | no | macOS terminal emulator |
| `symeraseme` | Python | no | Data-broker removal |

The Swift and Python tools cannot import the Go library directly. They follow
the conventions documented here so that behavior, diagnostics, and integrations
feel the same across the ecosystem.

## Exit Codes

The canonical CLI exit-code contract is:

| Code | Meaning | Used by |
|------|---------|---------|
| `0` | Success (`ExitOK`) | all |
| `1` | Generic error (`ExitError`) | all |
| `2` | Usage / invalid arguments (`ExitUsage`) | tune, eraseme |
| `3` | Permission / authorization (`ExitAuth`) | tune, operate |
| `4` | Unsupported / not available (`ExitUnsupported`) | tune |

Go tools reuse the typed constants in `corekit/exitcodes`. Non-Go tools should
map their domain errors to the same numeric values where applicable. Tools with
additional domain-specific codes (e.g. `symoperate`'s `staleReference=6` or
`symeraseme`'s `EXIT_NETWORK=3`) should document them alongside the canonical
subset.

`symterminal` currently uses only `0`/`1`; introducing typed codes aligned with
the table above is recommended.

## Environment Variables

Use the prefix `SYM<NAME>_` for tool-specific environment variables:

- `SYMVAULT_*` (reserved for vault)
- `SYMMEMORY_*` (reserved for memory)
- `SYMSEEK_*` (reserved for seek)
- `SYMFETCH_*` (reserved for fetch)
- `SYMSCOPE_*` (reserved for scope)
- `SYMOPERATE_*` (reserved for operate)
- `SYMTUNE_*` (e.g. `SYMTUNE_EXTBRIGHT_MIN`)
- `SYMERASEME_*` (e.g. `SYMERASEME_DATA_DIR`)

The Go helper `corekit/envutil.Get(name, aliases...)` supports reading a
variable under multiple aliases, which is useful during migration or for
supporting `XDG_*` overrides.

## Configuration Paths

Cross-platform tools should prefer XDG-style directories:

| Purpose | Default path |
|---------|--------------|
| Config | `~/.config/sym<name>/` |
| Cache | `~/.cache/sym<name>/` |
| Data | `~/.local/share/sym<name>/` |

Honor `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, and `XDG_DATA_HOME` when set.

- `symtune` follows this pattern with `~/.config/symtune/config.toml`.
- `symeraseme` follows it for config and data directories.
- `symterminal` uses `~/Library/Application Support/Symaira Terminal/` on macOS,
  which is acceptable for a macOS-native app, plus per-workspace
  `.symaira/config.json`.
- `symoperate` has no persistent config file by design.

### Config File Format

**TOML** is the canonical format for user-facing configuration files. Tools may
use JSON for machine-generated workspace-local state.

## Logging

- **Default level**: `warn`.
- **Destination**: `stderr`.
- **Configuration env var**: `SYM<NAME>_LOG_LEVEL` with values `debug`, `info`,
  `warn`, `error`.
- Go tools use `corekit/logkit`, which reads `SYM<NAME>_LOG_LEVEL` and
  `SYM<NAME>_LOG_FORMAT` (`text` or `json`).
- `symeraseme` uses Python's standard `logging` module configured via `-v`/`-vv`
  CLI flags.
- Swift tools currently log warnings/errors ad-hoc to `stderr`. Adopting a
  structured log format (at least for the MCP/server surface) is recommended.

## MCP / JSON-RPC Transport

The canonical MCP server transport for Symaira tools is **stdio with
`Content-Length` framing** as defined by the MCP specification:

```text
Content-Length: <n>\r\n\r\n<json-rpc-body>
```

- `symoperate` and `symtune` use this framing.
- `symterminal` additionally supports a Unix-domain-socket transport and a
  newline-delimited stdio transport for specific integration surfaces.
- `symeraseme` uses HTTP (`127.0.0.1:8000`) for its MCP server, which is a
  documented divergence.

### Zero Stdout Pollution

Any tool that exposes an MCP server over stdio must print **only structured
JSON-RPC frames to stdout**. Logs, diagnostics, warnings, and human-readable
output must go to `stderr`. This rule applies to Go, Swift, and Python tools
alike.

### JSON Key Encoding

Use `snake_case` for JSON keys in JSON-RPC payloads and tool results. `symtune`
already follows this convention. `symoperate` and `symterminal` use `camelCase`
for historical reasons; new tools should prefer `snake_case`.

## Update Checking

The recommended update-check contract is shared across Go and Swift tools to
ensure consistent behavior regardless of implementation language.

### Invariant Semantics

| Property | Contract |
|----------|----------|
| **Cache TTL** | 24 hours (`DefaultCacheTTL`). In-memory per-process cache; no disk cache. |
| **SemVer parsing** | Only strict `v?MAJOR.MINOR.PATCH` without pre-release or build-metadata suffixes. Versions containing `-` or `+` are silently ignored (treated as dev/unparseable). |
| **Dev / pre-release builds** | Skipped silently. `parseStableVersion` rejects anything non-stable; pre-release tags and dev version strings produce `nil` (no update offered). |
| **Non-blocking guarantee** | The *check* phase must never block startup or critical paths. A network timeout (default 3s) or failure produces a silent skip — the user never sees an error from the check itself. |
| **Error behavior** | Check failures (HTTP error, timeout, TLS error) are silently swallowed. The apply phase (download+verify+replace) returns all errors to the caller — here the user must be informed. |
| **V0-major gap** | When `current.major == 0` and `latest.major > 0`, the update is suppressed. This prevents a pre-v1.0 tool from suddenly advertising a v1.0+ release before the ecosystem is ready. |
| **Opt-out** | `SYM<NAME>_CHECK_UPDATES=false` environment variable or `[general] check_updates = false` config key. |
| **Apply hardening** | The apply phase (download, verify, swap) is composable: SHA-256 checksum verification (always), optional Cosign keyless signature verification (via `updatecheck/cosign`), optional archive extraction (via `updatecheck/extract`), and optional install-method detection that rejects Homebrew in-place replacement (via `updatecheck/installmethod`). |

### Reference Implementations

- **Go** — `corekit/updatecheck` (`Checker.Check`, `Applier.Apply`)
  Repository: `danieljustus/symaira-corekit`, package `updatecheck/`
  See also: `updatecheck/updateapply/`, `updatecheck/cosign/`, `updatecheck/extract/`, `updatecheck/installmethod/`

- **Swift** — `symaira-appkit/SymairaUpdateCheck/UpdateChecker.swift`
  Repository: `danieljustus/symaira-appkit`, target `SymairaUpdateCheck`
  Documents itself as a Swift port of `corekit/updatecheck`.

## Version Source

Compiled tools should expose a static version constant in source (e.g.
`TuneVersion.current` or `SymairaVersion.current`). Python tools should read the
version from package metadata (e.g. `importlib.metadata.version("symeraseme")`).

## Error Types

Prefer typed domain errors that map to exit codes. Examples:

- `symoperate.AutomationError`
- `symtune.TuneError`
- `symeraseme.SymerasemeError`

`corekit/exitcodes.CLIError` provides the Go equivalent: a typed error that
carries an exit code and a user-facing message.

## `doctor` Command

Tools that expose a `doctor` command should output a JSON document with at
least these fields:

```json
{
  "ok": true,
  "version": "0.1.0",
  "capabilities": [...],
  "recommendations": []
}
```

`symoperate` and `symtune` both implement a `doctor` subcommand.

## Candidates for Future Corekit Extraction

The following generic patterns are currently implemented inside individual tools
and could be candidates for moving into `corekit` if another Go tool needs them:

- **Advisory file locking** (`flock` / `funlock`) in
  `symaira-scope/internal/cache/lock_unix.go` and `lock_windows.go`.

These are intentionally left in their current homes until a second consumer
justifies the extraction.

## References

- `../ECOSYSTEM.md` — product ecosystem overview
- `../symaira-corekit/README.md` — corekit package index
- `../symaira-corekit/AGENTS.md` — corekit implementation boundaries
