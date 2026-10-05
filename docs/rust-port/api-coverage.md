# Consumer API coverage

This maps the immutable four-consumer source inventory, not mutable remote main. Mapping is distinct from native verification and consumer cutover. The machine-readable [inventory](api-coverage.json) retains every use-site and immutable source SHA.

## Inventory and scope

- `symaira-vault`: `08f2d63230050c36278a665c9fab7a7ff28b59a3`.
- `symaira-desktop`: `e817394e3b4df5e3320e85495dad0dea0e9938b4`.
- `symaira-brain`: `dfd55866a80e2c45509abf6f6bc17b897707d659`.
- `symaira-eraseme`: `adeb6b12341a38873a40fefec25621e845d7756a`.

The direct-selector inventory contains **104 distinct shared API symbols and 1088 references**. Each has a Rust mapping. This count excludes the explicitly consumer-local `auditkit`, `evidencekit`, `domkit` and `vectorkit/turboquant` slices. It does not claim that selector counting proves all receiver semantics.

## Per-symbol table

| Go package | Exported Go symbol | Rust crate | Exact API/adaptation | Uses |
| --- | --- | --- | --- | ---: |
| `configkit` | `DefaultPath` | `symaira-core-config` | `default_path` | 9 |
| `configkit` | `Loader` | `symaira-core-config` | `Loader` | 1 |
| `configkit` | `NewLoader` | `symaira-core-config` | `Loader::new` | 6 |
| `configkit` | `Options` | `symaira-core-config` | `Options` | 6 |
| `envutil` | `Getenv` | `symaira-core-env` | `getenv_lossy` | 2 |
| `exitcodes` | `CLIError` | `symaira-core-exit` | `CliError / CLIError` | 1 |
| `exitcodes` | `ErrorKind` | `symaira-core-exit` | `ErrorKind` | 1 |
| `exitcodes` | `ExitCode` | `symaira-core-exit` | `ExitCode` | 83 |
| `exitcodes` | `ExitCodeFromError` | `symaira-core-exit` | `exit_code_from_error` | 12 |
| `exitcodes` | `ExitConfig` | `symaira-core-exit` | `ExitCode::Config` | 8 |
| `exitcodes` | `ExitConflict` | `symaira-core-exit` | `ExitCode::Conflict` | 2 |
| `exitcodes` | `ExitData` | `symaira-core-exit` | `ExitCode::Data` | 25 |
| `exitcodes` | `ExitForbidden` | `symaira-core-exit` | `ExitCode::Forbidden` | 6 |
| `exitcodes` | `ExitGeneric` | `symaira-core-exit` | `ExitCode::Generic` | 147 |
| `exitcodes` | `ExitInterrupted` | `symaira-core-exit` | `ExitCode::Interrupted` | 3 |
| `exitcodes` | `ExitNoAuth` | `symaira-core-exit` | `ExitCode::NoAuth` | 1 |
| `exitcodes` | `ExitNoInput` | `symaira-core-exit` | `ExitCode::NoInput` | 214 |
| `exitcodes` | `ExitNotFound` | `symaira-core-exit` | `ExitCode::NotFound` | 9 |
| `exitcodes` | `ExitOK` | `symaira-core-exit` | `ExitCode::Ok` | 118 |
| `exitcodes` | `ExitSoftware` | `symaira-core-exit` | `ExitCode::Software` | 9 |
| `exitcodes` | `FormatCLIError` | `symaira-core-exit` | `format_cli_error` | 11 |
| `exitcodes` | `KindAuth` | `symaira-core-exit` | `ErrorKind::Auth` | 1 |
| `exitcodes` | `KindConfig` | `symaira-core-exit` | `ErrorKind::Config` | 16 |
| `exitcodes` | `KindConflict` | `symaira-core-exit` | `ErrorKind::Conflict` | 2 |
| `exitcodes` | `KindInternal` | `symaira-core-exit` | `ErrorKind::Internal` | 11 |
| `exitcodes` | `KindNotFound` | `symaira-core-exit` | `ErrorKind::NotFound` | 2 |
| `exitcodes` | `KindPermission` | `symaira-core-exit` | `ErrorKind::Permission` | 1 |
| `exitcodes` | `KindUnavailable` | `symaira-core-exit` | `ErrorKind::Unavailable` | 1 |
| `exitcodes` | `KindValidation` | `symaira-core-exit` | `ErrorKind::Validation` | 26 |
| `exitcodes` | `Wrap` | `symaira-core-exit` | `wrap` | 51 |
| `exitcodes` | `Wrapf` | `symaira-core-exit` | `wrapf with format!(...)` | 1 |
| `fsutil` | `AtomicWriteFile` | `symaira-core-fs` | `write_file_atomic` | 18 |
| `fsutil` | `ErrInvalidPath` | `symaira-core-fs` | `FsError::InvalidPath (typed variant adaptation)` | 1 |
| `fsutil` | `HasTraversal` | `symaira-core-fs` | `has_traversal / HasTraversal` | 2 |
| `fsutil` | `SafeMkdirAll` | `symaira-core-fs` | `safe_mkdir_all / SafeMkdirAll` | 4 |
| `fsutil` | `SafeRemove` | `symaira-core-fs` | `safe_remove / SafeRemove` | 2 |
| `fsutil` | `SafeWriteFile` | `symaira-core-fs` | `safe_write_file / SafeWriteFile` | 3 |
| `fsutil` | `ValidatePath` | `symaira-core-fs` | `validate_path / ValidatePath; FS-001-RUST-STRICT-v1` | 1 |
| `llmkit` | `AsError` | `symaira-core-llm` | `std::error::Error::downcast_ref::<Error> along source() chain (LLM-API-v1)` | 1 |
| `llmkit` | `ChatOptions` | `symaira-core-llm` | `ChatOptions` | 3 |
| `llmkit` | `Client` | `symaira-core-llm` | `Client` | 8 |
| `llmkit` | `Descriptor` | `symaira-core-llm` | `Descriptor` | 1 |
| `llmkit` | `EmbedOption` | `symaira-core-llm` | `Client::embed dimensions argument (LLM-API-v1)` | 1 |
| `llmkit` | `Embedding` | `symaira-core-llm` | `Embedding` | 1 |
| `llmkit` | `ErrCodeRateLimited` | `symaira-core-llm` | `ErrorCode::RateLimited` | 1 |
| `llmkit` | `ErrCodeTransport` | `symaira-core-llm` | `ErrorCode::TransportError` | 1 |
| `llmkit` | `Error` | `symaira-core-llm` | `Error` | 1 |
| `llmkit` | `GenerateOption` | `symaira-core-llm` | `GenerateOption` | 2 |
| `llmkit` | `GenerateResponse` | `symaira-core-llm` | `GenerateResponse` | 5 |
| `llmkit` | `Lookup` | `symaira-core-llm` | `lookup` | 10 |
| `llmkit` | `Message` | `symaira-core-llm` | `Message` | 3 |
| `llmkit` | `NewClient` | `symaira-core-llm` | `ClientBuilder::new(...).build()` | 9 |
| `llmkit` | `Option` | `symaira-core-llm` | `ClientBuilder fields/setters (LLM-API-v1)` | 3 |
| `llmkit` | `WithAPIKey` | `symaira-core-llm` | `ClientBuilder::api_key` | 2 |
| `llmkit` | `WithBaseURL` | `symaira-core-llm` | `ClientBuilder::base_url` | 9 |
| `llmkit` | `WithEmbedDimensions` | `symaira-core-llm` | `Client::embed(..., dimensions)` | 2 |
| `llmkit` | `WithGenerateFormat` | `symaira-core-llm` | `GenerateOption::format field` | 1 |
| `llmkit` | `WithGenerateImages` | `symaira-core-llm` | `GenerateOption::images field` | 1 |
| `llmkit` | `WithGenerateSystem` | `symaira-core-llm` | `GenerateOption::system field` | 1 |
| `llmkit` | `WithStreamFinished` | `symaira-core-llm` | `Client::stream_chat finish callback` | 1 |
| `llmkit` | `WithTimeout` | `symaira-core-llm` | `ClientBuilder::timeout` | 7 |
| `logkit` | `Default` | `symaira-core-log` | `default_logger` | 4 |
| `logkit` | `InitDefault` | `symaira-core-log` | `init_default` | 3 |
| `logkit` | `New` | `symaira-core-log` | `Logger::new` | 2 |
| `logkit` | `NewFromEnv` | `symaira-core-log` | `new_from_env` | 1 |
| `mcpcfgkit` | `Client` | `symaira-core-mcpcfg` | `Client` | 3 |
| `mcpcfgkit` | `DefaultSources` | `symaira-core-mcpcfg` | `default_sources` | 2 |
| `mcpcfgkit` | `DefaultSourcesForPlatform` | `symaira-core-mcpcfg` | `default_sources_for_platform` | 1 |
| `mcpcfgkit` | `ScanAllWithFS` | `symaira-core-mcpcfg` | `scan_all_with_fs` | 4 |
| `mcpcfgkit` | `ScanSource` | `symaira-core-mcpcfg` | `ScanSource` | 5 |
| `mcpcfgkit` | `Server` | `symaira-core-mcpcfg` | `Server` | 1 |
| `mcpcfgkit` | `StatusUnsupported` | `symaira-core-mcpcfg` | `Status::Unsupported` | 1 |
| `mcpserver` | `CodeParseError` | `symaira-core-mcp` | `CODE_PARSE_ERROR` | 1 |
| `mcpserver` | `New` | `symaira-core-mcp` | `Server::new` | 7 |
| `mcpserver` | `Server` | `symaira-core-mcp` | `Server` | 10 |
| `mcpserver` | `Tool` | `symaira-core-mcp` | `Tool` | 56 |
| `mcpserver` | `ToolAnnotations` | `symaira-core-mcp` | `ToolAnnotations` | 32 |
| `secretref` | `DefaultTimeout` | `symaira-core-secretref` | `DEFAULT_TIMEOUT` | 4 |
| `secretref` | `Resolve` | `symaira-core-secretref` | `resolve / Resolver::resolve` | 3 |
| `sqlitekit` | `Migrate` | `symaira-core-sqlite` | `migrate` | 4 |
| `sqlitekit` | `Open` | `symaira-core-sqlite` | `open (SQL-ADAPTER-v1)` | 10 |
| `updatecheck` | `Checker` | `symaira-core-update` | `Checker` | 1 |
| `updatecheck` | `DefaultCachePath` | `symaira-core-update` | `default_cache_path` | 1 |
| `updatecheck` | `DefaultCacheTTL` | `symaira-core-update` | `cache::DEFAULT_CACHE_TTL` | 1 |
| `updatecheck` | `NewChecker` | `symaira-core-update` | `Checker::new` | 4 |
| `updatecheck` | `NewSecureClient` | `symaira-core-update` | `request::secure_client_builder(timeout).build()` | 1 |
| `updatecheck` | `Release` | `symaira-core-update` | `Release` | 4 |
| `updatecheck/cosign` | `Config` | `symaira-core-update` | `cosign::Config` | 2 |
| `updatecheck/cosign` | `OIDCIssuer` | `symaira-core-update` | `cosign::OIDC_ISSUER` | 1 |
| `updatecheck/installmethod` | `BuildFromSource` | `symaira-core-update` | `install_method::InstallMethod::BuildFromSource` | 1 |
| `updatecheck/installmethod` | `Detect` | `symaira-core-update` | `install_method::detect / detect_typed` | 2 |
| `updatecheck/installmethod` | `DirectDownload` | `symaira-core-update` | `install_method::InstallMethod::DirectDownload` | 1 |
| `updatecheck/installmethod` | `ErrEmptyBinaryPath` | `symaira-core-update` | `install_method::ERR_EMPTY_BINARY_PATH / EmptyBinaryPath` | 1 |
| `updatecheck/installmethod` | `GoInstall` | `symaira-core-update` | `install_method::InstallMethod::GoInstall` | 1 |
| `updatecheck/installmethod` | `Guidance` | `symaira-core-update` | `InstallMethod::guidance` | 1 |
| `updatecheck/installmethod` | `Homebrew` | `symaira-core-update` | `install_method::InstallMethod::Homebrew` | 2 |
| `updatecheck/installmethod` | `InstallMethod` | `symaira-core-update` | `install_method::InstallMethod` | 1 |
| `updatecheck/installmethod` | `IsSelfUpdateSupported` | `symaira-core-update` | `InstallMethod::self_update_supported` | 1 |
| `updatecheck/installmethod` | `PackageManager` | `symaira-core-update` | `install_method::InstallMethod::PackageManager` | 1 |
| `updatecheck/installmethod` | `Unknown` | `symaira-core-update` | `install_method::InstallMethod::Unknown` | 1 |
| `updatecheck/updateapply` | `Applier` | `symaira-core-update` | `applier::Applier` | 1 |
| `updatecheck/updateapply` | `NewApplier` | `symaira-core-update` | `Applier::default` | 2 |
| `versionkit` | `Info` | `symaira-core-version` | `Info` | 4 |
| `versionkit` | `New` | `symaira-core-version` | `new` | 8 |

## Receivers, fields and intentional adapter contracts

| Consumer-owned seam | Rust mapping and boundary | Evidence |
| --- | --- | --- |
| Config `Loader.Load/Reload/ResetCache`, options fields | `load/reload/reset_cache`; `Options` fields `app_name/env_prefix/config_name/use_legacy_config_path`. Reload bypasses rather than replaces the Load cache. | CFG-001..007; foundation configuration tests; Desktop room/pdf and Brain memory config sources |
| Version `Info.String/Write` | `Display`/`to_string` and `Info::write`; exact `tool/version/schema_version` wire fields | VER-001..002; Vault `internal/cli/version.go` |
| MCP `RegisterTool/SetInstructions/ServeIO/ServeStdio` | `register_tool/set_instructions/serve_io/serve_stdio`; cancellable IO is explicit | MCP-001..012, CON-003/006/007; Brain gateway and Desktop MCP adapters |
| MCP `Tool` fields and handler error interfaces | `Tool` and `ToolAnnotations` fields; `ToolOutput/ToolError` carry result/error metadata. Go custom error interfaces become explicit typed Rust values. | Existing annotation and tool-error contract tests |
| MCP config source/server fields | `ScanSource.client/path/key`, `Server.name/client/command/args/transport/env/env_keys/env_values/config_path`; public status is `Status`, not an invented `ScanStatus` | MCFG-001..005; Brain guard discovery |
| LLM methods `Chat/StreamChat/Embed/Generate/ListModels/Ping` | `chat/stream_chat/embed/generate/list_models/ping`, with cancellable partners. `LLM-API-v1`: functional options become builder setters, typed option fields or callback/dimension arguments. | LLM-001..012; [LLM contract](llm-contract.md); native wire/cancellation tests |
| LLM `Error` and `AsError` | `Error.code/status_code/body/retry_after/detail`. `LLM-API-v1`: inspect the typed error or traverse `source()` and downcast; no message parsing or fake same-named helper. | Existing taxonomy/provider tests; EraseMe and Brain LLM sources |
| Logger receiver and `slog.SetDefault` integration | `LOG-ADAPTER-v1`: use `Logger::debug/info/warn/error` and `log_attrs` with typed `LogAttr`/`LogValue`. Replace Go's process-global slog registry with CoreKit's `init_default/default_logger` registry and adapt the consumer gateway logger type. This is not an ABI-compatible `*slog.Logger`. | LOG-001..004; Desktop `cmd/symdesk/main.go:119`, Brain Browse logging and `cmd/symbrain/cmd_serve.go:66` |
| SQL return type and pool methods | `SQL-ADAPTER-v1`: `open` returns `rusqlite::Connection`, not a `database/sql.DB` pool. The inspected `SetMaxOpenConns(1)`, `SetMaxIdleConns(1)` and unlimited connection lifetime become explicit single-connection ownership. Every separately created connection must go through CoreKit `open`. Do not emulate a Go pool inside CoreKit. | SQL-001..006; Brain `internal/memory/db/db.go:56-63`; Desktop ingest store |
| SQL `QueryContext/QueryRowContext/ExecContext/BeginTx` | `SQL-ADAPTER-v1`: port consumer queries to `query/query_row/execute/transaction`, preserve SQL and transaction ownership, and wire real interrupt handles for cancellation. These are upstream database APIs and consumer-owned control flow, not additional shared helper exports. This table does not authorize ignoring cancellation or a consumer cutover without its own evidence. | Native SQLite differential/transaction tests; Desktop ingest `store.go:119,136,230,380` |
| Update checker fields/methods | `latest_release_url/cache_path/cache_ttl/transport`; `check/check_with_force` and cancellable partners. Blocking HTTP injection is a `Transport`; async HTTP injection is an explicit `reqwest::Client` argument. Current-version validation, cache eligibility and memory/disk behavior are composed, not inferred from helper tests. | UPD-013; 21 freshly executed Go checker observations and mutation rejection |
| Cosign Config fields and HTTP client | `repo/binary_name/download_base_url/identity_regexp`; `fetch_signature_with_client/fetch_certificate_with_client` and cancellable partners. `OIDC_ISSUER` is public. Client injection is per-call rather than an incompatible new struct field. | UPD-009/014; transport and cancellation tests; real signed-release gate remains required |
| Applier options, context, extraction and validation callbacks | `check_install_method/goos/goarch/binary_name/cosign/extract_binary`; validator/progress are call arguments. `apply_cancellable` owns transport/child cleanup and has an explicit local commit point: cancellation before install leaves the old binary; cancellation after install rolls back before returning. | UPD-010..014; native real signed disposable Apply and process/rollback tests |
| Install-method empty-path sentinel | `detect_typed` returns public `EmptyBinaryPath` / `ERR_EMPTY_BINARY_PATH`; existing `detect` string API remains available. Consumers classify the typed value. | Existing install-method tests plus typed API regression |
| Filesystem invalid-path sentinel and control boundary | Typed `FsError::InvalidPath`. [FS-001-RUST-STRICT-v1](fs-path-contract.md) preserves stricter DEL/C1 rejection. The old ad-hoc C1 capture is not accepted evidence; fresh ASCII-keyed native Go replay is required. | FS-001; nine live Go control cases and actual mutation rejection |
| Secret-ref runtime resolution | `resolve/Resolver::resolve/resolve_with_deadline` and `DEFAULT_TIMEOUT`. The existing `rust-fs-secret` probe plus `diff_fs_secret.py` really execute all thirteen FS/SEC rows, including all six SEC rows; merely checking fixture IDs is not that proof. | SEC-001..006, CON-004; native RUST-003 jobs |

## Contracts package disposition

The supplied consumers import no production `contracts` API. Keep Go conformance tests while Go remains the executable oracle; retire that Go test package **with Go**, not before. Preserve the language-neutral `contracts/*.json` schemas, Rust embedded copies and drift checks, including Swift vendoring. Do not delete fixture corpora or require another Symaira executable to use a crate.

## Acceptance boundary

RUST-017 is complete and UPD-013/014 are parity at integrated main `1f3a7276500042121fe2d79a545462a15675aadc`, backed by [the digest-checked native evidence index](evidence/status-reconciliation-20261005.json). All three native targets executed the 21-observation checker and its mutation, the 16-case cancellation/rollback corpus, and FS-001's thirteen FS/SEC rows plus nine path controls and mutations. Ordinary CI separately passed native workspace tests, strict Clippy and fmt; Linux hardening passed workspace nextest. Skipped opt-in oracle/signed tests are covered by their separate executable native gates, not inferred from the workspace summary. Later heads require fresh CI. Consumer-specific logger/SQL adapters still need their consumer's own cutover evidence before deleting Go; RUST-016 and #370/#373 remain blocked by actual releases, standalone/rollback records and observations.
