# Cross-Language Conventions for Symaira Free Tools

`symaira-corekit` is a Go library, but the conventions it encodes apply to all
free/public Symaira tools regardless of implementation language. This document
captures the shared contracts that keep the ecosystem consistent.

## Tool Inventory

| Tool | Language | Imports corekit | Notes |
|------|----------|-----------------|-------|
| `symvault` | Go + Rust migration | yes (Go) | Wraps some corekit packages in `internal/` adapters |
| `symbrain` | Go + Rust migration | yes (Go) | Direct consumer (also carries the absorbed memory, skills and guard packages) |
| `symdesk` | Go + Rust migration | yes (Go) | Direct consumer (also carries the absorbed ingest, print, relate, room and seek modules) |
| `symbrowse` | Go + Rust migration | yes (Go) | Direct consumer (also carries the absorbed static fetch engine) |
| `symeraseme` | Go + Rust migration | yes (Go) | Data-broker removal product |
| `symfritz` | Rust | no | Rust-only since v0.8.0; v0.7.0 is the immutable Go rollback release |
| `symcockpit` | Swift | no | macOS: thermals/power, GUI automation, port and MCP inventory |

The row per tool is one **repository**, not one binary: the 2026-08 repo
consolidation folded fourteen tools into four products, so a single consumer
here now covers what used to be several rows.

Tools that do not build Go cannot import the Go library directly. They follow
the conventions documented here so that behavior, diagnostics, and integrations
feel the same across the ecosystem.

## Exit Codes

The canonical CLI exit-code contract is:

| Code | Name | Meaning |
|------|------|---------|
| `0` | `ExitOK` | Success |
| `1` | `ExitGeneric` | Generic or unspecified error |
| `2` | `ExitNoInput` | Required input is missing |
| `3` | `ExitNoAuth` | Authentication failed |
| `4` | `ExitForbidden` | Authenticated but not permitted |
| `5` | `ExitNotFound` | Requested resource was not found |
| `6` | `ExitConflict` | Current state conflicts with the request |
| `7` | `ExitSoftware` | Internal software error |
| `8` | `ExitData` | Invalid data format or content |
| `9` | `ExitConfig` | Configuration error |
| `10` | `ExitInterrupted` | Operation was interrupted |

Go tools reuse the typed constants in `corekit/exitcodes`. Non-Go tools map
equivalent failures to this table. A product-specific numeric mapping is scoped
to that product's own protocol and must not be presented as a CoreKit code.

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

- The `tune` family follows this pattern with `~/.config/symtune/config.toml`
  (the per-family config paths and `SYMTUNE_*`/`SYMOPERATE_*`/`SYMSCOPE_*`
  env prefixes survived the merge into `symcockpit`).
- `symeraseme` follows it for config and data directories.
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
- `symeraseme` keeps diagnostics on stderr while its Go-to-Rust migration is in progress.
- Swift tools currently log warnings/errors ad-hoc to `stderr`. Adopting a
  structured log format (at least for the MCP/server surface) is recommended.

## MCP / JSON-RPC Transport

The canonical MCP server transport for Symaira tools is **stdio with
`Content-Length` framing** as defined by the MCP specification:

```text
Content-Length: <n>\r\n\r\n<json-rpc-body>
```

- The `operate` and `tune` families of `symcockpit` use this framing.
- `symeraseme` uses HTTP (`127.0.0.1:8000`) for its MCP server, which is a
  documented divergence.

### Zero Stdout Pollution

Any tool that exposes an MCP server over stdio must print **only structured
JSON-RPC frames to stdout**. Logs, diagnostics, warnings, and human-readable
output must go to `stderr`. This rule applies to Go, Swift, and Python tools
alike.

### JSON Key Encoding

Use `snake_case` for tool-defined JSON payloads and results. MCP envelope and
annotation fields keep the casing required by the protocol. Historical
product-specific divergences must be documented; new fields use `snake_case`.

### Tool Error Metadata

A tool call that fails is reported as an MCP tool result with `isError: true`,
not as a JSON-RPC error object — the JSON-RPC error is for protocol faults
(unparseable request, unknown method), and using it for a tool's own failure
hides the message from the model.

That result carries prose. A tool whose error knows more about itself — a
stable code, whether a retry can help, what the caller is allowed to do next —
publishes those as structured fields under the result's `_meta`, keyed
`symaira.dev/tool_error`, instead of rendering them into the sentence:

```json
{
  "content": [{"type": "text", "text": "peer_denied: robots.txt forbids this path"}],
  "isError": true,
  "_meta": {
    "symaira.dev/tool_error": {
      "code": "peer_denied",
      "message": "peer_denied: robots.txt forbids this path",
      "retryable": false,
      "requires_confirmation": false,
      "resume_hint": "pick a path robots.txt allows",
      "details": {"robots_rule": "Disallow: /private"}
    }
  }
}
```

The Go implementation (`corekit/mcpserver.ToolErrorData`) derives the object
from optional interfaces on the returned error, so a tool opts in by giving
its error type the methods it already has elsewhere; an error with nothing to
add produces no `_meta` at all. The field set, the method names behind each
field, and the omission rules are pinned in
[`../contracts/mcp_tool_errors.json`](../contracts/mcp_tool_errors.json).

## Update Checking

The recommended update-check contract is shared across Go and Swift tools to
ensure consistent behavior regardless of implementation language.

### Invariant Semantics

| Property | Contract |
|----------|----------|
| **Cache TTL** | 24 hours (`DefaultCacheTTL`). Results persist per repository in the platform cache directory and are reusable across processes. Go uses `$XDG_CACHE_HOME/symaira/updatecheck/<sha256(owner NUL repo)>.json`, falling back to `$HOME/.cache` when `XDG_CACHE_HOME` is not absolute. Setting `Checker.CachePath` to an empty string disables Go persistence; a forced check bypasses every cache layer. |
| **SemVer parsing** | Only strict `v?MAJOR.MINOR.PATCH` without pre-release or build-metadata suffixes. Versions containing `-` or `+` are silently ignored (treated as dev/unparseable). |
| **Dev / pre-release builds** | Skipped silently. `parseStableVersion` rejects anything non-stable; pre-release tags and dev version strings produce `nil` (no update offered). |
| **Invocation** | A check can wait until the API timeout (default 3s). Consumers must run background checks off startup and other critical paths; the library itself does not hide latency. |
| **Error behavior** | Check failures (HTTP error, timeout, TLS error, malformed/draft/prerelease response) are returned or thrown to the caller. A consumer may silently ignore them for an optional background check. Apply failures are likewise surfaced and should be shown to the user. |
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

- `symcockpit` (operate module) — `SymOperateCore.AutomationError`
- `symcockpit` (tune module) — `SymTuneCore.TuneError`
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

Both implement a `doctor` subcommand, reachable as `symcockpit operate doctor`
and `symcockpit tune doctor`.

## Candidates for Future Corekit Extraction

None currently tracked. The previous entry here (advisory file locking in
`symaira-scope/internal/cache/lock_unix.go`) is gone: `symaira-scope` was
archived and its functionality ported to Swift, so the Go implementation this
candidate pointed at no longer exists.

## References

- `../ECOSYSTEM.md` — product ecosystem overview
- `../symaira-corekit/README.md` — corekit package index
- `../symaira-corekit/AGENTS.md` — corekit implementation boundaries
