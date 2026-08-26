# llmkit

The shared Go LLM provider layer, implementing
[`docs/llm-provider-contract.md`](../docs/llm-provider-contract.md). One HTTP
transport plus a dialect table: most vendors speak the OpenAI wire format, so
adding one is an entry in `contracts/llm_providers.json`, not client code.

## Quick start

```go
import "github.com/danieljustus/symaira-corekit/llmkit"

// Look up a provider from the embedded registry.
desc, _ := llmkit.Lookup("openrouter")

// Credentials resolve through the shared reference format — never raw keys.
c, err := llmkit.NewClient(desc, "symvault://secrets/openrouter_key")
if err != nil {
    var le *llmkit.Error
    if errors.As(err, &le) && le.Code == llmkit.ErrCodeAuth {
        // exitcodes.ExitNoAuth — report and stop.
    }
}

choice, err := c.Chat(ctx, "", // empty = descriptor default model
    []llmkit.Message{{Role: "user", Content: "Summarize this document."}}, nil)
```

Streaming:

```go
err := c.StreamChat(ctx, "anthropic/claude-sonnet-5", msgs, nil,
    func(delta string) error {
        fmt.Print(delta)
        return nil
    })
```

Embeddings and model discovery (Ollama, OpenRouter):

```go
embs, err := c.Embed(ctx, "nomic-embed-text", []string{"doc one", "doc two"})
models, err := c.ListModels(ctx)
```

## Credential references

| Form | Resolution |
|---|---|
| `symvault://secrets/anthropic_key` | `symvault get secrets/anthropic_key --print` |
| `env://ANTHROPIC_API_KEY` | environment variable |
| `ANTHROPIC_API_KEY` (bare name) | environment variable shorthand |
| `""` | falls back to the descriptor's `credential_env_default` |

Errors name only the reference, never a resolved value.

## Error handling

Branch on the contract taxonomy (`contracts/llm_errors.json`), never on
upstream text. Every failure surfaces as `*llmkit.Error` with a `Code`, a
mapping onto `exitcodes` values (`ExitCode()`), and `Retryable()`:

```go
e := llmkit.AsError(err)
switch e.Code {
case llmkit.ErrCodeRateLimited:
    // e.Retryable() == true, honor e.RetryAfter
case llmkit.ErrCodeContextOverflow:
    // trim the prompt; retrying unchanged cannot succeed
}
```

## Adding a vendor without code

An unlisted or self-hosted vendor works through the `custom` descriptor — no
code change, no release of this package:

```go
custom, _ := llmkit.Lookup("custom")
c, _ := llmkit.NewClient(custom, "env://VLLM_TOKEN",
    llmkit.WithBaseURL("http://localhost:8000/v1"))
choice, _ := c.Chat(ctx, "meta-llama/Llama-3.1-8B-Instruct", msgs, nil)
```

Any OpenAI-compatible server (vLLM, llama.cpp, LM Studio) is exactly this.

## Registry maintenance

The registry lives in `contracts/llm_providers.json` (shared with appkit's
Swift half). After editing it, regenerate the embedded copy:

```sh
go run ./llmkit/gen > llmkit/providers.json
go test ./llmkit/ ./contracts/
```

The conformance suite in `conformance_test.go` runs every descriptor against
the same chat/streaming/embeddings/error-mapping invariants automatically, so
a new vendor is under contract from the moment it enters the registry.

## Relationship to ollamakit

`ollamakit` is deprecated and forwards conceptually to this package's ollama
descriptor; it will be removed after one minor release. New consumers should
use `llmkit` directly.
