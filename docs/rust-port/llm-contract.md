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
- Synchronous and cancellable non-streaming OpenAI chat share a Go-compatible
  decoder. The pinned oracle exercises null/missing fields, case-folded names,
  duplicate keys and nested objects, reused array slots, explicit resets, typed
  field rejection, and tool calls. The Rust API still normalizes valid tool
  arguments to JSON values and preserves invalid raw argument text as a string.
- Secret references use `symaira-core-secretref`; errors preserve the Go
  `llmkit` categories, HTTP status/body/retry-after fields, retry classification,
  and shared exit-code mapping. Credential values are not included in diagnostic
  formatting or the oracle fixture.
- HTTPS is required for non-loopback remote endpoints. The default HTTP agent
  disables redirects and uses a two-minute request timeout. Callers can inject
  a configured `ureq::Agent` with `ClientBuilder::agent`; its transport settings
  are caller-controlled. `ClientBuilder::http_client` accepts one configured
  `reqwest::Client` for both synchronous and cancellable calls, matching Go's
  `WithHTTPClient`. The synchronous adapter streams response chunks through a
  bounded reader and joins its worker before returning; it does not detach a
  request or buffer streaming responses wholesale. The existing `agent` and
  `async_client` methods remain available for separate legacy configurations;
  combining either with `http_client` is rejected.
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
  one non-empty record. Callers can supply a shared `reqwest::Client` through
  `ClientBuilder::http_client` so both request modes use the same transport
  configuration. An injected blocking `ureq::Agent` without an async client
  remains an explicit error for cancellable calls. Synchronous calls without a
  shared client continue to use the configured `ureq::Agent`.

## Response limits

Go reads response bodies through `io.LimitReader`, returning bytes up to the
existing cap and then EOF. Both synchronous Rust transports now use
`Read::take` with the same caps; cancellable reads already truncate at that
boundary. This fixes the legacy agent's over-cap transport error and preserves
the error-response prefix instead of silently discarding it. Bounds are not
raised or removed.

The Go oracle records an over-cap valid chat response and an over-cap typed
HTTP error without storing multi-megabyte padding in JSON. Two interrupted-body
cases additionally prove that a known HTTP failure keeps its classified prefix,
while an interrupted successful response still returns `transport_error`.
`response_limit_observations_match_go_across_transports` compares complete
content/error observations for the default agent, default cancellable client,
and a shared injected client in blocking and cancellable modes. The new test
failed before the repair and passed afterward.

## Differential evidence

`scripts/rust-port/llm-oracle` records requests, cancellation classifications,
and responses from the shipped Go implementation against local HTTP test
servers. The committed
`testdata/rust-port/fixtures/llm/go-oracle.json` binds that observation to the
Go source, oracle, and runner hashes. Its injected-client case sends regular
chat, incremental SSE, and canceled embedding through one Go `http.Client`;
the Rust replay checks the same paths through `ClientBuilder::http_client` and
verifies that cancellation closes the response while synchronous streaming
remains incremental. Run `make rust-llm-contract` to execute
the focused Go package checks, compare the pinned oracle observation, run Rust
format/lint, and test the Rust crate. Refresh the observation deliberately with
`python3 scripts/rust-port/llm-differential.py --write` after a reviewed Go
contract change.
The `Rust foundation` CI matrix runs this gate on Linux, macOS, and Windows.
`tests/openai_success_parity.rs` replays the 29 pinned success-response cases
through both synchronous and cancellable clients, comparing the returned
choice or provider-error category. Parser diagnostic wording is not compared
byte-for-byte.

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
| LLM-010 | `taxonomy_maps_status_retry_and_exit_codes`, `malformed_openai_error_envelopes_keep_go_http_classification`, `structured_error_fields_follow_go_json_casefolding`, `cancellable_chat_preserves_go_rate_limit_and_header_classification`, `cancellable_context_methods_match_go_and_do_not_send_requests`, `cancellable_guards_keep_local_errors_ahead_of_cancellation`, `cancellation_drops_embedding_discovery_and_ollama_stream_reads`, `provider_error_truncates_raw_bytes_before_utf8_decode`, `response_limit_observations_match_go_across_transports` |
| LLM-011 | `registry_and_go_generated_snapshot_are_available` plus `go test ./llmkit/gen` in the gate |
| LLM-012 | `go test ./ollamakit` in the gate plus `assert_no_rust_ollamakit()` in `scripts/rust-port/llm-differential.py` (workspace member scan, negative control: injected `symaira-core-ollamakit` member is rejected) |

## Current consumer operation inventory

The following direct Go callers were checked at immutable remote-main snapshots
on 2026-10-02. Constructor/type/option imports were audited alongside the request
methods, not counted as separate transports.

| Consumer | Snapshot | Representative production paths |
| --- | --- | --- |
| Brain | `5294aece81d3c76aa7f96bb5479369c53707443c` | `internal/memory/llm/client.go`, `internal/memory/extractor/embeddings.go` |
| Desktop | `e817394e3b4df5e3320e85495dad0dea0e9938b4` | `internal/ai/{ai,anthropic}.go`, `internal/ingest/internal/ocr/vlm.go`, `internal/retrieval/internal/engine/embeddings.go`, `cmd/symdesk/ai_config.go` |
| EraseMe | `28e32a1c7c8732921007e9124d14f5bbabd60397` | `internal/llm/llmkit.go` |

| Go request operation | Current consumers | Rust shared operation / cancellable partner | Rows |
| --- | --- | --- | --- |
| `Chat` | Brain, EraseMe | `chat` / `chat_cancellable` | LLM-004, LLM-005 |
| `StreamChat`, finish callback | Desktop | `stream_chat` / `stream_chat_cancellable` | LLM-006, LLM-007 |
| `Embed`, optional dimensions | Brain, Desktop | `embed` / `embed_cancellable`, dimensions argument | LLM-008 |
| `Generate`, system/format/images/temperature | Brain, Desktop | `generate` / `generate_cancellable`, `GenerateOption` | LLM-009 |
| `ListModels` | Desktop | `list_models` / `list_models_cancellable` | LLM-008 |
| `Ping` | Desktop | `ping` / `ping_cancellable` | LLM-009 |

The public native `EmbedNative`, `ListOllamaModels` and `ChatStream` paths are
also implemented and recorded/replayed, even though the direct importer scan
above does not identify another current caller. They are not separate local
provider transports.

Legacy `New`/`NewConfig`, provider constants and registry-driven `NewClient`
resolve to `lookup` plus `ClientBuilder`; consumer configuration policy stays
with the consumer. `WithBaseURL`, `WithAPIKey`, `WithTimeout` and
`WithHTTPClient` map to the corresponding builder methods. Shared `Message`,
`ChatOptions`, `Embedding`, model and generate response types are exported.
Generate system/format/image/temperature options map to `GenerateOption`,
embedding dimensions to the embed argument, and stream-finished behavior to the
finish callback. Existing wire/callback tests exercise these settings.

All consumers should invoke this shared client for provider HTTP behavior;
consumer rollout is separately gated by their own migration issues and CoreKit
#370. A source inventory or local transport pass does not claim their release
cutover, live paid-provider acceptance, or rollback completion.

## Residual boundary

The existing synchronous methods remain synchronous and are not cancellable.
The async cancellation methods require an executor and a separate async client
when custom transport settings are needed; `ureq::Agent` settings cannot be
transferred automatically. Go-context cancellation is proven by local Go and
Rust fixtures; remote-provider behavior and consumer cutover remain outside
this contract slice.
