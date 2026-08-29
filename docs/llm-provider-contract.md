# LLM Provider Contract

One shared LLM provider layer for the Symaira ecosystem. The Go half lives in
`corekit/llmkit` (issue #173), the Swift half in `symaira-appkit`
(`SymairaProviderKit`). Both read the same descriptor data from
[`contracts/llm_providers.json`](../contracts/llm_providers.json) and map
failures through the taxonomy in
[`contracts/llm_errors.json`](../contracts/llm_errors.json).

This document is the contract both implementations are built against. It was
reviewed against all six existing provider abstractions (see the audit table at
the end); each one's current provider set is expressible with this contract.

## Design decision: one transport, one dialect table

Almost every LLM vendor speaks OpenAI wire format today — OpenRouter, Groq,
DeepSeek, Mistral, xAI, Moonshot, Together, Fireworks, Azure OpenAI, Gemini's
OpenAI-compatibility endpoint, and any OpenAI-compatible local server
(llama.cpp, LM Studio, vLLM). EraseMe already proved this with its explicit
`openai_compatible_client.py`.

Therefore: **the shared layer is one HTTP transport plus a dialect table.**
Anthropic is the only genuine wire exception shipped at v1 (Gemini is served
through its OpenAI-compat endpoint, not a native dialect). Adding a new vendor
is a descriptor entry — no client code, no release of the package.

The direct consequences:

- "Custom endpoint" (`custom`) and "local model" (`ollama`, or any local server)
  are ordinary descriptors, not special code paths.
- `custom` exists as a first-class descriptor with a required base-URL override,
  a configurable auth scheme, and a configurable dialect — an unlisted vendor
  works without a release of this package.

## The provider descriptor

Declarative data, not a class hierarchy. Fields (see
`contracts/llm_providers.json` for the authoritative values):

| Field | Meaning |
|---|---|
| `id` | Stable identifier used by config files and CLIs (`"anthropic"`) |
| `display_name` | Human-readable name |
| `base_url` | Default endpoint; `null` means the user must provide one |
| `base_url_overridable` | Users may point the provider elsewhere |
| `auth.scheme` | `bearer`, `header` (+ `header` name), or `none`; `configurable_scheme: true` allows any scheme |
| `extra_headers` | Mandatory static headers (e.g. `anthropic-version`) |
| `dialect` | Wire format: `openai` or `anthropic`; `dialect_configurable: true` on `custom` |
| `capabilities` | Flags: `streaming`, `tool_use`, `embeddings`, `vision`, `system_prompt` |
| `models.mode` | `static`, `discovered` (+ `discovery_path`), `deployment` (Azure), or `configured` |
| `credential_ref_env_default` | Conventional env-var fallback for credential resolution; `null` for providers that need none |

### Capability rules

A capability flag is a **promise**: if `streaming` is true the shared client must
be able to stream that provider; if `tool_use` is true tool calls round-trip.
A consumer must not offer a feature the descriptor does not promise, and the
conformance suite (below) tests every promised capability per dialect.

### Base URL transport security

When a descriptor carries credentials, its effective base URL must use
`https`. The Go client rejects a non-HTTPS endpoint as `auth_failure` before
resolving or sending the credential. HTTP is allowed only for descriptors with
`auth.scheme: none` or for loopback hosts (`localhost`, `127.0.0.0/8`, and
`::1`), which covers local servers such as Ollama, llama.cpp, LM Studio, and
vLLM. This rule applies equally to descriptor defaults and
`base_url_overridable` overrides.

## Credential references

Credentials are never passed as raw key strings inside config files. A config
value may be:

1. A vault reference: `symvault://secrets/anthropic_key` — resolved via
   `symvault get -- secrets/anthropic_key --print` (the `vault://` alias is
   accepted but deprecated; see `ECOSYSTEM.md`).
2. An OS-keychain reference: `keychain://<service>/<account>` (Swift consumers
   via symaira-appkit's Keychain broker).
3. An environment-variable name reference: `env://ANTHROPIC_API_KEY`.

Resolution order for a provider without an explicit reference:
`env://<credential_ref_env_default>` → error `auth_failure` with a message
naming the missing reference. The shared package never logs resolved secrets.

## Error taxonomy

Six categories, mapped to corekit `exitcodes` values. Consumers must branch on
these codes, never on string-matched upstream text:

| Code | Meaning | Retryable |
|---|---|---|
| `auth_failure` | Missing/invalid/expired credential | no |
| `rate_limited` | HTTP 429; carries `retry_after` when reported | yes |
| `context_overflow` | Prompt exceeds context window | no |
| `model_not_found` | Unknown model/deployment for this credential | no |
| `transport_error` | Network-level failure (refused, DNS, TLS, timeout) | yes |
| `provider_error` | Anything else the provider reported (status + body excerpt carried) | no |

## Model discovery

Providers with `models.mode == "discovered"` expose a list endpoint:
OpenRouter `/models`, Ollama `/api/tags`. The Go and Swift clients normalize
both into `{id, context_window?}` entries. Static lists are compiled into the
descriptor data and refreshed by regenerating from vendor docs — the refresh
path is editing `contracts/llm_providers.json`, which both halves re-read.

## Non-goals (recorded boundary)

- **Usage/quota/billing** — belongs to the cockpit→brain AI-usage layer
  (symaira-brain #275–#277). Not here.
- **Agent/turn logic** — desktop's `agent_turn.go`, `citations.go`,
  `externalize.go` are Markdown-vault domain logic and stay in desktop.
- **Vector search** — embedding *calls* belong here; `corekit/vectorkit` is
  unchanged.

## Audit against existing implementations

Every current provider set must be expressible under this contract:

| Implementation | Providers today | Expressible? |
|---|---|---|
| terminal `ProviderKit` (Swift, 1,416 LoC) | anthropic, openai, openrouter, google/gemini, ollama, custom + OAuth | yes — OAuth remains terminal-side via its `OAuthAuthenticator` until appkit grows a shared flow; descriptors cover all six ids |
| eraseme `llm/` (Python, 1,093 LoC) | anthropic, openai, openai-compatible, ollama | yes — `openai-compatible` ≡ `custom`; the Python port reads the same JSON |
| corekit `ollamakit` (Go, 1,100 LoC) | ollama | yes — absorbed by llmkit (#173), thin deprecated shim kept one minor |
| brain `internal/memory/llm/` (Go, 247 LoC) | ollama, openai | yes |
| desktop `internal/ai/anthropic.go` (Go, 106 LoC) | anthropic | yes — incl. its `SYMDESK_ANTHROPIC_URL` override ≡ `base_url_overridable` |
| cockpit/terminal key-entry UI (Swift, 1,170 LoC) | — | yes — consumes the same descriptor list for provider pickers |

Recorded gap: **OAuth** exists only in terminal's ProviderKit. It stays there
until a shared flow lands in appkit; the descriptor schema reserves nothing for
it yet beyond `auth.scheme` extensibility.
