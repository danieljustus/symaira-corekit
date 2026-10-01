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
- `chat_cancellable` and `stream_chat_cancellable` provide async cancellation
  through a `CancellationToken`. Cancelling drops the active async request or
  response read, closing the provider connection, and reports
  `transport_error`, matching Go `llmkit`'s `context.Context` cancellation path
  (`llmkit/client.go`: `do` passes the context to `http.NewRequestWithContext`
  and classifies `Do` errors with `errTransport`). Callers can supply a
  `reqwest::Client` through `ClientBuilder::async_client` for custom async
  transport settings. An injected blocking `ureq::Agent` without an async client
  remains an explicit error for cancellable calls. Synchronous calls continue
  to use the configured `ureq::Agent`.
- `embed_cancellable` uses the same request validation, request body, bounded
  response read, and decoder as synchronous `embed`. Cancellation drops the
  active request or response read, including while waiting for response headers
  or body bytes; an injected async client is honored.

## Differential evidence

`scripts/rust-port/llm-oracle` records requests and classifications from the
shipped Go implementation against local HTTP test servers. The committed
`testdata/rust-port/fixtures/llm/go-oracle.json` binds that observation to the
Go source, oracle, and runner hashes. Run `make rust-llm-contract` to execute
the focused Go package checks, compare the pinned oracle observation, run Rust
format/lint, and test the Rust crate. Refresh the observation deliberately with
`python3 scripts/rust-port/llm-differential.py --write` after a reviewed Go
contract change.
The `Rust foundation` CI matrix runs this gate on Linux, macOS, and Windows.

## Residual boundary

The existing `chat`, `stream_chat`, and `embed` methods remain synchronous and
are not cancellable. Model discovery and native Ollama endpoints also remain
synchronous. The async cancellation methods require an executor; a separate
async client is needed when custom transport settings are required, because
`ureq::Agent` settings cannot be transferred automatically. This slice does
not authorize a consumer cutover, release, tag, Go removal, or publication.
