# Rust LLM transport contract

`rust/symaira-core-llm` ports the shared HTTP transport boundary represented by
Go `llmkit`. The Rust crate is a library only; it does not add consumer-specific
provider code, a Rust `ollamakit` clone, or a process/release surface.

## Implemented contract

- Provider descriptors are loaded from the same generated `llmkit/providers.json`
  data that Go embeds. The fixture compares the serialized descriptor registry.
- The client supports descriptor-selected OpenAI-compatible and Anthropic
  chat dialects, OpenAI-compatible embeddings, model discovery, and the native
  Ollama embed, model-list, generate, chat, and ping endpoints.
- Chat supports tool definitions, response-format options, and streaming. OpenAI
  and Anthropic server-sent event framing is bounded to 1 MiB per line. Ollama
  streaming consumes newline-delimited JSON records.
- Secret references use `symaira-core-secretref`; errors preserve the Go
  `llmkit` categories, HTTP status/body/retry-after fields, retry classification,
  and shared exit-code mapping. Credential values are not included in diagnostic
  formatting or the oracle fixture.
- HTTPS is required for non-loopback remote endpoints. The default HTTP agent
  disables redirects and uses a two-minute request timeout. Callers can inject
  a configured `ureq::Agent` with `ClientBuilder::agent`; its transport settings
  are caller-controlled.
- `chat_cancellable`, `stream_chat_cancellable`, `embed_cancellable`,
  `list_models_cancellable`, `embed_native_cancellable`,
  `list_ollama_models_cancellable`, `generate_cancellable`,
  `chat_stream_cancellable`, and `ping_cancellable` provide async cancellation
  through a `CancellationToken`. Cancelling drops the active async request or
  response read, closing the provider connection, and reports
  `transport_error`, matching Go `llmkit`'s `context.Context` path
  (`llmkit/client.go`: `do` passes the context to `http.NewRequestWithContext`
  and classifies `Do` errors with `errTransport`). Static model listing stays
  local and succeeds even when the token is already canceled. Cancellable
  Ollama NDJSON calls preserve Go's `stream interrupted` prefix after at least
  one non-empty record. Callers can supply a `reqwest::Client` through
  `ClientBuilder::async_client` for custom async transport settings. An
  injected blocking `ureq::Agent` without an async client remains an explicit
  error for cancellable calls. Synchronous calls continue to use the configured
  `ureq::Agent`.

## Differential evidence

`scripts/rust-port/llm-oracle` records requests, cancellation classifications,
and responses from the shipped Go implementation against local HTTP test
servers. The committed
`testdata/rust-port/fixtures/llm/go-oracle.json` binds that observation to the
Go source, oracle, and runner hashes. Run `make rust-llm-contract` to execute
the focused Go package checks, compare the pinned oracle observation, run Rust
format/lint, and test the Rust crate. Refresh the observation deliberately with
`python3 scripts/rust-port/llm-differential.py --write` after a reviewed Go
contract change.
The `Rust foundation` CI matrix runs this gate on Linux, macOS, and Windows.

## Streaming parity (LLM-006, LLM-007)

`scripts/rust-port/llm-oracle/main.go` additionally records six SSE observations
through the public `llmkit.Client.StreamChat`: the OpenAI and Anthropic happy
paths (request bytes, callback order, finish reason) and four malformed OpenAI
streams (comment-only body, undecodable chunk, oversized line before and after
the first data line). Bodies over four KiB are stored by kind, length and
SHA-256 so the multi-megabyte scanner fixtures stay out of the committed JSON.

`rust/symaira-core-llm/tests/stream_contract.rs` rebuilds every recorded body,
verifies its digest, replays it through **both** transports — the blocking
`stream_chat` and the cancellable `stream_chat_cancellable` — and compares the
wire request, the event order, and the exact `llmkit` error code and message.
The replay exposed two real drifts that are fixed here: Rust's `serde_json`
text replaced Go's `encoding/json` text in `decode stream chunk`, and the
cancellable transport reported `stream line exceeds 1 MiB` where Go reports
`bufio.Scanner: token too long`.

## Row evidence

Every row below executes inside `make rust-llm-contract`, which CI runs on
`ubuntu-latest`, `macos-26` and `windows-latest` (`Rust foundation` matrix):

| Row | Rust evidence (executed) |
| --- | --- |
| LLM-001 | `registry_and_go_generated_snapshot_are_available` |
| LLM-002 | `empty_api_key_uses_credential_resolution`, `base_query_stays_after_the_joined_chat_path`, `dialect_override_follows_go_builder_behavior`, `zero_timeout_keeps_go_unbounded_request_behavior`, `caller_agent_routes_requests_through_its_proxy` |
| LLM-003 | `credentials_fail_closed_and_redirects_are_not_followed`, `openai_and_anthropic_dialects_emit_their_go_wire_shapes` (auth header) |
| LLM-004 | `openai_and_anthropic_dialects_emit_their_go_wire_shapes`, `cancellable_chat_preserves_go_openai_wire_contract`, `openai_null_choice_matches_go_zero_value_choice` |
| LLM-005 | `openai_and_anthropic_dialects_emit_their_go_wire_shapes`, `anthropic_content_includes_text_from_every_block_like_go` |
| LLM-006 | `go_recorded_stream_wire_and_callback_order_match`, `go_recorded_malformed_stream_errors_match`, `streaming_and_embedding_calls_preserve_openai_wire_options` |
| LLM-007 | `go_recorded_stream_wire_and_callback_order_match`, `go_recorded_malformed_stream_errors_match`, `anthropic_stream_and_openrouter_model_discovery_are_normalized` |
| LLM-008 | `streaming_and_embedding_calls_preserve_openai_wire_options`, `embedding_response_fields_match_go_case_insensitive_json`, `openrouter_model_discovery_uses_go_casefold_alias_order`, `generic_ollama_discovery_uses_go_casefold_alias_order`, `native_ollama_calls_match_go_recordings`, `cancellable_embedding_discovery_and_ollama_calls_match_go_recordings` |
| LLM-009 | `native_ollama_calls_match_go_recordings`, `cancellable_ollama_streams_match_go_recordings`, `native_ollama_generate_accepts_go_scanner_large_chunks`, `native_ollama_generate_scanner_errors_match_go_before_and_after_data`, `native_ollama_generate_json_errors_match_go` |
| LLM-010 | `taxonomy_maps_status_retry_and_exit_codes`, `malformed_openai_error_envelopes_keep_go_http_classification`, `structured_error_fields_follow_go_json_casefolding`, `cancellable_chat_preserves_go_rate_limit_and_header_classification`, `cancellable_context_methods_match_go_and_do_not_send_requests`, `cancellable_guards_keep_local_errors_ahead_of_cancellation`, `cancellation_drops_embedding_discovery_and_ollama_stream_reads`, `provider_error_truncates_raw_bytes_before_utf8_decode` |
| LLM-011 | `registry_and_go_generated_snapshot_are_available` plus `go test ./llmkit/gen` in the gate |
| LLM-012 | `go test ./ollamakit` in the gate plus `assert_no_rust_ollamakit()` in `scripts/rust-port/llm-differential.py` (workspace member scan, negative control: injected `symaira-core-ollamakit` member is rejected) |

## Residual boundary

The existing synchronous methods remain synchronous and are not cancellable.
The async cancellation methods require an executor and a separate async client
when custom transport settings are needed; `ureq::Agent` settings cannot be
transferred automatically. Go-context cancellation is proven by local Go and
Rust fixtures; remote-provider behavior and consumer cutover remain outside
this contract slice.
