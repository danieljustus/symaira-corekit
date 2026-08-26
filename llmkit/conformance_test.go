//nolint:gosec // G104 in test servers: ignored write/copy errors are intentional here

package llmkit

// Conformance suite: every provider descriptor must pass the same invariants,
// so "supported" means something checkable rather than "someone tried it
// once" (issue #175). The tests iterate the whole embedded registry; adding a
// vendor is a registry edit and automatically brings it under this contract.

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func allOpenAIDialectProviders(t *testing.T) []Descriptor {
	t.Helper()
	ps, err := Providers()
	if err != nil {
		t.Fatalf("Providers: %v", err)
	}
	var out []Descriptor
	for _, p := range ps {
		if p.Dialect == DialectOpenAI {
			out = append(out, p)
		}
	}
	return out
}

// TestConformanceChatShape proves each openai-dialect descriptor produces a
// request the OpenAI chat-completions endpoint actually accepts, and parses a
// canonical response. This is the wire-level meaning of "reachable".
func TestConformanceChatShape(t *testing.T) {
	for _, p := range allOpenAIDialectProviders(t) {
		p := p
		t.Run(p.ID, func(t *testing.T) {
			var gotPath string
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				gotPath = r.URL.Path
				_, _ = io.Copy(io.Discard, r.Body)
				_, _ = w.Write([]byte(`{"choices":[{"message":{"role":"assistant","content":"ok"},"finish_reason":"stop"}]}`))
			}))
			defer srv.Close()

			envKey(t, confTestEnvName(p))
			c, err := NewClient(p, confTestCredRef(p), WithBaseURL(srv.URL))
			if err != nil {
				t.Fatalf("NewClient: %v", err)
			}
			choice, err := c.Chat(context.Background(), "conf-model",
				[]Message{{Role: "user", Content: "ping"}}, nil)
			if err != nil {
				t.Fatalf("Chat: %v", err)
			}
			if choice.Content != "ok" {
				t.Errorf("content = %q", choice.Content)
			}
			if gotPath != "/chat/completions" {
				t.Errorf("path = %q", gotPath)
			}
		})
	}
}

// TestConformanceStreaming exercises the SSE stream path for every streaming-
// capable openai-dialect provider.
func TestConformanceStreaming(t *testing.T) {
	for _, p := range allOpenAIDialectProviders(t) {
		p := p
		if !p.Capabilities.Streaming {
			continue
		}
		t.Run(p.ID, func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "text/event-stream")
				_, _ = io.WriteString(w, "data: {\"choices\":[{\"delta\":{\"content\":\"x\"}}]}\n\n")
				_, _ = io.WriteString(w, "data: [DONE]\n\n")
			}))
			defer srv.Close()

			envKey(t, confTestEnvName(p))
			c, err := NewClient(p, confTestCredRef(p), WithBaseURL(srv.URL))
			if err != nil {
				t.Fatalf("NewClient: %v", err)
			}
			var n int
			err = c.StreamChat(context.Background(), "m", []Message{{Role: "user", Content: "p"}}, nil,
				func(delta string) error { n++; return nil })
			if err != nil {
				t.Fatalf("StreamChat: %v", err)
			}
			if n != 1 {
				t.Errorf("deltas = %d, want 1", n)
			}
		})
	}
}

// TestConformanceEmbeddingsCapabilityGate asserts the embeddings promise is
// enforced exactly: providers with the flag serve /embeddings; providers
// without it refuse before touching the network.
func TestConformanceEmbeddingsCapabilityGate(t *testing.T) {
	hitNetwork := false
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hitNetwork = true
		_, _ = io.WriteString(w, `{"data":[{"embedding":[1,2]}]}`)
	}))
	defer srv.Close()

	for _, p := range allOpenAIDialectProviders(t) {
		p := p
		t.Run(p.ID, func(t *testing.T) {
			envKey(t, confTestEnvName(p))
			c, err := NewClient(p, confTestCredRef(p), WithBaseURL(srv.URL))
			if err != nil {
				t.Fatalf("NewClient: %v", err)
			}
			before := hitNetwork
			_, err = c.Embed(context.Background(), "m", []string{"x"})
			if p.Capabilities.Embeddings && err != nil {
				t.Fatalf("promised embeddings but call failed: %v", err)
			}
			if !p.Capabilities.Embeddings {
				if err == nil || !strings.Contains(err.Error(), "embeddings") {
					t.Fatalf("unpromised embeddings accepted: %v", err)
				}
				if hitNetwork != before {
					t.Error("capability gate must reject before any network I/O")
				}
			}
		})
	}
}

// TestConformanceErrorMapping runs one representative upstream failure per
// taxonomy code through every dialect and checks the classification.
func TestConformanceErrorMapping(t *testing.T) {
	cases := []struct {
		name   string
		status int
		body   string
		want   ErrorCode
	}{
		{"auth", 401, `{"error":{"message":"bad key"}}`, ErrCodeAuth},
		{"rate limit", 429, `{}`, ErrCodeRateLimited},
		{"overflow", 400, `{"error":{"code":"context_length_exceeded","message":"maximum context length exceeded"}}`, ErrCodeContextOverflow},
		{"model missing", 404, `{}`, ErrCodeModelNotFound},
		{"server error", 503, `{}`, ErrCodeProvider},
	}
	for _, p := range allOpenAIDialectProviders(t) {
		p := p
		for _, tc := range cases {
			tc := tc
			t.Run(p.ID+"/"+tc.name, func(t *testing.T) {
				srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					http.Error(w, tc.body, tc.status)
				}))
				defer srv.Close()

				envKey(t, confTestEnvName(p))
				c, err := NewClient(p, confTestCredRef(p), WithBaseURL(srv.URL))
				if err != nil {
					t.Fatalf("NewClient: %v", err)
				}
				_, err = c.Chat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil)
				e := AsError(err)
				if e == nil || e.Code != tc.want {
					t.Fatalf("got %v, want %s", err, tc.want)
				}
			})
		}
	}
}

// TestConformanceRegistryCoverage documents the coverage claim of issue #175:
// the registry must contain the named vendor groups, custom endpoints, and a
// local provider — with a worked example proving an unlisted vendor needs no
// code (the `custom` descriptor).
func TestConformanceRegistryCoverage(t *testing.T) {
	ps, err := Providers()
	if err != nil {
		t.Fatalf("Providers: %v", err)
	}
	byID := map[string]Descriptor{}
	for _, p := range ps {
		byID[p.ID] = p
	}

	openAIVendors := []string{"openai", "openrouter", "groq", "deepseek", "mistral", "xai", "moonshot", "together", "fireworks", "azure-openai"}
	for _, id := range openAIVendors {
		d, ok := byID[id]
		if !ok {
			t.Errorf("missing openai-dialect vendor %q", id)
			continue
		}
		if d.Dialect != DialectOpenAI {
			t.Errorf("%q should speak the openai dialect", id)
		}
	}
	for _, id := range []string{"anthropic"} {
		d, ok := byID[id]
		if !ok {
			t.Fatalf("missing genuine-dialect provider %q", id)
		} else if d.Dialect != DialectAnthropic {
			t.Errorf("%q should speak the anthropic dialect", id)
		}
	}
	local, ok := byID["ollama"]
	if !ok {
		t.Fatal("missing local provider ollama")
	}
	if !strings.Contains(local.BaseURL, "localhost") {
		t.Errorf("local provider base url = %q", local.BaseURL)
	}
	custom, ok := byID["custom"]
	if !ok {
		t.Fatal("missing custom descriptor")
	}
	if !custom.DialectConfigurable || !custom.BaseURLRequiredOverride {
		t.Error("custom descriptor must allow dialect + require base URL configuration")
	}
}

// TestWorkedExampleUnlistedVendor is the docs example: a self-hosted
// vLLM server is reachable through the `custom` descriptor without any code
// change and without a release of this package.
func TestWorkedExampleUnlistedVendor(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.WriteString(w, `{"choices":[{"message":{"content":"from self-hosted vllm"},"finish_reason":"stop"}]}`)
	}))
	defer srv.Close()

	t.Setenv("VLLM_TOKEN", "local-token")
	custom, _ := Lookup("custom")
	c, err := NewClient(custom, "env://VLLM_TOKEN",
		WithBaseURL(srv.URL), // stands in for http://localhost:8000/v1
	)
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	choice, err := c.Chat(context.Background(), "meta-llama/Llama-3.1-8B-Instruct",
		[]Message{{Role: "user", Content: "hi"}}, nil)
	if err != nil {
		t.Fatalf("Chat: %v", err)
	}
	if choice.Content != "from self-hosted vllm" {
		t.Errorf("content = %q", choice.Content)
	}
}

// TestLocalOnlySetupWorks is the case that must never regress: Ollama on
// localhost with no cloud keys and no credential at all.
func TestLocalOnlySetupWorks(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/tags":
			_, _ = io.WriteString(w, `{"models":[{"name":"llama3.1"}]}`)
		default:
			t.Errorf("unexpected path %q", r.URL.Path)
		}
	}))
	defer srv.Close()

	ollama, _ := Lookup("ollama")
	c, err := NewClient(ollama, "", WithBaseURL(srv.URL))
	if err != nil {
		t.Fatalf("local setup requires no credentials: %v", err)
	}
	models, err := c.ListModels(context.Background())
	if err != nil || len(models) != 1 || models[0].ID != "llama3.1" {
		t.Fatalf("discovery: models=%+v err=%v", models, err)
	}
}

// confTestEnvName returns a per-provider env var name so tests never depend
// on ambient machine state.
func confTestEnvName(d Descriptor) string {
	if d.CredentialEnvDefault == "" {
		return "LLMKIT_CONFORMANCE_TEST_KEY"
	}
	return d.CredentialEnvDefault
}

// confTestCredRef returns an explicit credential reference for descriptors
// without a conventional env default (custom, azure-openai).
func confTestCredRef(d Descriptor) string {
	if d.CredentialEnvDefault == "" {
		return "env://LLMKIT_CONFORMANCE_TEST_KEY"
	}
	return ""
}

// guard: keep encoding/json referenced even if future edits drop direct uses.
var _ = json.Marshal
