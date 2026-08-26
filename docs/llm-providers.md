# LLM Providers: Ecosystem Wiring Guide

How Symaira tools consume the shared LLM provider layer. The contract lives in
[`llm-provider-contract.md`](llm-provider-contract.md); this document is the
consumer-side wiring guide and the credential/logging rulebook.

**Single source of truth:** `corekit/llmkit` (Go) and
`symaira-appkit/SymairaProviderKit` (Swift), both generated from the shared
descriptor data in `corekit/contracts/llm_providers.json`. New provider code in
a consumer repository is a convention violation — file an issue against corekit
instead.

## Go consumers: wiring llmkit

```go
import (
    "errors"

    "github.com/danieljustus/symaira-corekit/exitcodes"
    "github.com/danieljustus/symaira-corekit/llmkit"
)

func ask(ctx context.Context) error {
    desc, _ := llmkit.Lookup("anthropic")

    // Credentials come from a reference, never from a config literal.
    c, err := llmkit.NewClient(desc, "symvault://secrets/anthropic_key")
    if err != nil {
        return classify(err)
    }

    choice, err := c.Chat(ctx, "", // "" = descriptor default model
        []llmkit.Message{{Role: "user", Content: "hi"}}, nil)
    if err != nil {
        return classify(err)
    }
    _ = choice.Content
    return nil
}

func classify(err error) error {
    var le *llmkit.Error
    if !errors.As(err, &le) {
        return err
    }
    switch le.Code {
    case llmkit.ErrCodeAuth:
        return exitcodes.Wrap(err, exitcodes.ExitNoAuth, exitcodes.KindAuth,
            "provider credentials rejected")
    case llmkit.ErrCodeRateLimited:
        return exitcodes.Wrap(err, exitcodes.ExitConflict, exitcodes.KindConflict,
            "rate limited; retry after %s", le.RetryAfter)
    case llmkit.ErrCodeContextOverflow:
        return exitcodes.Wrap(err, exitcodes.ExitData, exitcodes.KindValidation,
            "prompt exceeds context window")
    case llmkit.ErrCodeModelNotFound:
        return exitcodes.Wrap(err, exitcodes.ExitNotFound, exitcodes.KindNotFound,
            "model not available for this credential")
    default:
        return err
    }
}
```

Config-file convention: store the **reference** (`symvault://…`, `env://…`) in
your tool's TOML config under e.g. `provider_credential`, never a key.

## Swift consumers: wiring SymairaProviderKit

`SymairaProviderKit` in symaira-appkit mirrors the same descriptor registry.
It vendors `contracts/llm_providers.json` at the pinned corekit revision (same
mechanism as the other cross-language fixtures, see
`contracts/README.md` § Compatibility policy). Provider pickers, defaults, and
capability gating in Swift clients read that vendored copy; credentials resolve
through the Keychain broker (`keychain://service/account`). On a corekit bump,
re-vendor the descriptor data deliberately and run appkit's fixture tests.

## Staying in sync

Both halves read one JSON source. The rules:

1. Edit `contracts/llm_providers.json` (the SSOT).
2. Regenerate: `go run ./llmkit/gen > llmkit/providers.json`.
3. Run `go test ./llmkit/ ./contracts/` — the conformance suite covers every
   new descriptor automatically.
4. Vendor the updated file into appkit at bump time.

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

   ```go
   custom, _ := llmkit.Lookup("custom")
   c, _ := llmkit.NewClient(custom, credRef, llmkit.WithBaseURL(baseURL))
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

```go
desc, _ := llmkit.Lookup("ollama")     // auth scheme "none"
c, _ := llmkit.NewClient(desc, "")      // no credential resolution happens
models, _ := c.ListModels(ctx)          // GET /api/tags
_ = c.Generate(ctx, "", "prompt", cb)   // native streaming surface
```

No environment variables, no vault entries, no network beyond localhost. This
path is pinned by `TestLocalOnlySetupWorks` and must never regress — it is why
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
   `ECOSYSTEM.md` § conventions).
5. **Fail closed.** A missing or failed credential resolution is an
   `auth_failure` (`ExitNoAuth`) — never an empty key sent upstream, and never
   a silent fallback to another provider.
