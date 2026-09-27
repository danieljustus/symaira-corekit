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
  and classifies `Do` errors with `errTransport`). These methods use a separate
  async HTTP client and reject clients configured with an injected blocking
  `ureq::Agent`; existing synchronous calls and their injected-agent behavior
  are unchanged.

## Differential evidence

`scripts/rust-port/llm-oracle` records requests and classifications from the
shipped Go implementation against local HTTP test servers. The committed
`testdata/rust-port/fixtures/llm/go-oracle.json` binds that observation to the
Go source, oracle, and runner hashes. Run `make rust-llm-contract` to execute
the focused Go package checks, compare the pinned oracle observation, run Rust
format/lint, and test the Rust crate. Refresh the observation deliberately with
`python3 scripts/rust-port/llm-differential.py --write` after a reviewed Go
contract change.

## Residual boundary

The existing `chat` and `stream_chat` methods remain synchronous and are not
cancellable. The async cancellation methods require an executor and cannot
reuse caller-configured `ureq::Agent` settings; callers needing both custom
transport configuration and cancellation need a separately designed async
transport-injection API. This slice does not authorize a consumer cutover,
release, tag, Go removal, or publication.
