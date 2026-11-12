# Intended differences from the retired Go library

The Go library was retired after `v0.18.3` ([ADR 0005](../adr/0005-go-library-retirement.md)).
The Rust crates keep the Go *contracts* that are frozen in `testdata/rust-port`
(exit codes, paths, framing, documented error classes), but they do not
reproduce every byte of Go's standard library behaviour. This page records the
per-crate decision for the gaps that symaira-desktop measured against its Go
recordings ([#480](https://github.com/danieljustus/symaira-corekit/issues/480)),
so consumers do not have to re-audit them.

**Decision:** CoreKit adds no Go-compatibility modes. The differences below are
intended. A consumer whose own frozen recordings need Go bytes keeps that
adapter in its own repository. A gap becomes CoreKit work only when it is a
defect (wrong or non-deterministic behaviour) or when two real consumers need
the same helper.

Error *messages* are diagnostics, not a contract, in every crate. Match on the
error enum variant or error code, never on the rendered text.

## symaira-core-mcp

| Difference | Status |
|---|---|
| Request parsing uses `serde_json`, not `encoding/json`: member names are case-sensitive, numeric ids are re-rendered (`1e3`, `-0`), invalid UTF-8 and lone surrogates are rejected, nesting stops at 128 levels, syntax error texts differ. | Intended. JSON-RPC 2.0 and RFC 8259 do not require Go's leniency, and the depth limit protects the stack. |
| Transport error texts (Content-Length, EOF) and the order of a parse error relative to in-flight tool results. | Intended. Responses are matched by id; ordering across ids is not guaranteed by JSON-RPC. |
| No context-cancelled tool result after a fatal read error. | Intended. A fatal transport error ends the session; there is no peer left to read the result. |
| Output key order depended on whether the consumer build enabled `serde_json/preserve_order`. | **Fixed:** every result object and input schema is written with sorted keys, as Go did for maps. CI runs the crate tests with that feature enabled. |
| At most 16 tool calls run at once, and the reader blocked behind them, so `ping` waited for tool calls to finish. | **Fixed:** queued calls wait in a FIFO (up to 1024) while the reader keeps answering `ping`, `tools/list` and protocol errors. The 16-call bound on running handlers stays. |

## symaira-core-fs

| Difference | Status |
|---|---|
| `write_file_atomic` temp names are `.<name>.tmp-<hex>-<n>` (hidden, collision-resistant); Go used `<name>.tmp<digits>`. | Intended. |
| Errors carry their own variants and texts instead of Go's `op path: errno`. | Intended (diagnostics, see above). |
| A world-writable (0777) parent or a symlinked parent is rejected, also by `safe_mkdir_all` and therefore by `symaira-core-sqlite::open`. | Intended. This is the hardened path contract in [fs-path-contract.md](fs-path-contract.md). |
| No streaming or keep-existing variant of the atomic copy. | Not planned until two consumers need it. |

## symaira-core-secretref

| Difference | Status |
|---|---|
| Error texts: no `(reference X)` suffix, no `resolve <ref>:` prefix, no `symvault binary not found on PATH` pre-check, helper stderr not echoed, different timeout wording. | Intended. Helper stderr can contain secret material, so it is suppressed rather than copied into errors. |
| `keychain://service/account/extra` and control characters are rejected. | Intended. A reference names exactly one service and one account. |

## symaira-core-log

| Difference | Status |
|---|---|
| Timestamps are always UTC with `Z`; Go's `slog` text handler used the host offset. | Intended. Log lines stay comparable across hosts and time zones. |
| Text quoting differs from `strconv.Quote` for C1 controls, U+200B and U+FEFF. | Intended for now. Values are still escaped so a line cannot be split; open an issue if a consumer parses these characters. |

## symaira-core-llm (embeddings)

| Difference | Status |
|---|---|
| `Client::embed` rejects `{"data":null}`, `{}` and `{"embedding":null}`; Go returned empty or zero vectors and failed later with a count error. | Intended. A malformed provider response fails at the point where it is detected. |
| Connection-refused and timeout texts differ from Go's `net/http` and `context` texts. | Intended. Use `ErrorCode`. |

## symaira-core-config

| Difference | Status |
|---|---|
| The legacy path (`$HOME/.config/<app>/config.toml`, XDG ignored, Go `UseLegacyConfigPath`) is only used inside `Loader` (`Options::use_legacy_config_path`) and has no public helper. | Not planned while only one consumer needs it (shared code needs two real consumers). The crate is also a bound FS/SEC frozen input, so a helper would ride with the next deliberate FS/SEC re-freeze. |
| `default_path_for_roots` does not apply `filepath.Clean`. | Intended. The path is built from the given roots without lexical rewriting; clean the inputs first if they can contain `.` or `..`. |
