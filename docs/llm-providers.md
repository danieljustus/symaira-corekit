# LLM Providers: Ecosystem Wiring Guide

How Symaira tools consume the shared LLM provider layer. The contract lives in
[`llm-provider-contract.md`](llm-provider-contract.md); this document is the
consumer-side wiring guide and the credential/logging rulebook.

**Single source of truth:** the shared descriptor data in
`corekit/contracts/llm_providers.json`. It is consumed by the Rust crate
`symaira-core-llm` (through the generated `llmkit/providers.json`) and by
`SymairaProviderKit` (Swift, `appkit/` in this repository). The Go `llmkit` package was
retired from `main` after v0.18.3 and stays available to Go consumers at
`v0.18.x`. New provider code in a consumer repository is a convention
violation — file an issue against corekit instead.

## Rust consumers: wiring symaira-core-llm

Pin `symaira-core-llm` to an exact CoreKit Git revision (ADR 0002). Look up a
descriptor with `symaira_core_llm::lookup`, build a client with
`ClientBuilder` from a credential **reference** (`symvault://…`, `env://…`),
and map `ErrorCode` to `symaira_core_exit::ExitCode` as pinned in
`contracts/llm_errors.json`. `rust/symaira-core-llm/tests/con_008.rs` is the
executable reference for both the registry and the error mapping.

Config-file convention: store the **reference** (`symvault://…`, `env://…`) in
your tool's TOML config under e.g. `provider_credential`, never a key.

## Swift consumers: wiring SymairaProviderKit

`SymairaProviderKit` (`appkit/Sources/SymairaProviderKit`) mirrors the same
descriptor registry. It bundles a copy of `contracts/llm_providers.json` as a
resource, and its contract test asserts that copy equals the canonical file in
this repository. Provider pickers, defaults, and capability gating in Swift
clients read the bundled copy; credentials resolve through the Keychain broker
(`keychain://service/account`). Swift clients receive descriptor changes by
raising their exact CoreKit pin.

## Staying in sync

Both halves read one JSON source. The rules:

1. Edit `contracts/llm_providers.json` (the SSOT) and copy it to
   `rust/test-support/symaira-contract-fixtures/fixtures/contracts/`.
2. Regenerate: `python3 scripts/rust-port/llm_providers_gen.py`.
3. Run `make rust-llm-contract` — the drift gate and `con_008` cover every
   new descriptor automatically.
4. Copy it to `appkit/Sources/SymairaProviderKit/Resources/` and run
   `make swift-test`; the Swift contract test fails on any drift.

Field renames are breaking changes to the fixture schema (see
`contracts/README.md`); additive fields are minor.

## Worked example: adding a self-hosted provider end to end

Scenario: a team wants to use a self-hosted vLLM server. No code, no release:

1. Deploy vLLM with an OpenAI-compatible endpoint, e.g.
   `http://llm.internal:8000/v1`.
2. Store its token in the vault: `symvault set secrets/vllm_token`.
3. In your tool's config:

   ```toml
   [ai]
   provider = "custom"
   base_url = "http://llm.internal:8000/v1"
   model = "meta-llama/Llama-3.1-8B-Instruct"
   credential = "symvault://secrets/vllm_token"
   ```

4. Wire it once in code (identical for every custom endpoint):

   ```rust
   let custom = symaira_core_llm::lookup("custom").unwrap().clone();
   let client = symaira_core_llm::ClientBuilder::new(custom, cred_ref).base_url(base_url).build()?;
   ```

That is the whole integration. A genuinely new cloud vendor is the same flow
with its production base URL — plus, ideally, a descriptor PR so every tool
gets it out of the box.

## Local-first setup (Ollama, no cloud keys)

The configuration that must always work, offline:

```toml
[ai]
provider = "ollama"
model = "llama3.1"
```

```rust
let desc = symaira_core_llm::lookup("ollama").unwrap().clone(); // auth scheme "none"
let client = symaira_core_llm::ClientBuilder::new(desc, "").build()?; // no credential resolution
let models = client.list_models()?;          // model discovery
client.generate("", "prompt", &options, callback)?; // native streaming surface
```

No environment variables, no vault entries, no network beyond localhost. This
path must never regress — it is why
several tools are usable for privacy-sensitive work at all. If Ollama is down,
the failure is `transport_error` / `ExitGeneric` with a retryable verdict.

## Credential handling rules

What may be logged, what must be redacted, where keys live:

1. **Keys live in exactly one place per platform**: the vault
   (`symvault://`) on servers/CLIs, the OS keychain via appkit's broker
   (`keychain://`) in GUI apps, or an environment variable in ephemeral
   environments (`env://NAME`). Config files hold references only.
2. **Never log resolved values.** llmkit errors name only the reference string
   (`symvault://secrets/anthropic_key`) and the failure class. Consumers must
   apply the same rule: no `printf("%v", client)` style debugging of client or
   config structs, no request dumps with headers intact.
3. **Redact before persisting.** Any structured log line that could carry a
   config object goes through redaction first: values matching a resolved
   credential are replaced by `[REDACTED:<reference>]`. The reference itself is
   safe to log.
4. **`symvault://` vs. `vault://`** (decided 2026-08-24): `symvault://` is the
   canonical URI scheme because `vault` is double-booked in the ecosystem
   (credential vault vs. document vault in symdesk). Consumers may *accept*
   `vault://` as an alias but must emit and document only `symvault://`;
   `vault://` carries a deprecation notice wherever it is still accepted (see
   [`llm-provider-contract.md`](llm-provider-contract.md#credential-references)).
5. **Fail closed.** A missing or failed credential resolution is an
   `auth_failure` (`ExitNoAuth`) — never an empty key sent upstream, and never
   a silent fallback to another provider.
