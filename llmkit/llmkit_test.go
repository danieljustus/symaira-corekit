package llmkit

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/danieljustus/symaira-corekit/exitcodes"
)

func mustDescriptor(t *testing.T, id string) Descriptor {
	t.Helper()
	d, ok := Lookup(id)
	if !ok {
		t.Fatalf("descriptor %q not found in embedded registry", id)
	}
	return d
}

func envKey(t *testing.T, name string) {
	t.Helper()
	t.Setenv(name, "test-key-123")
}

func TestLookupRegistry(t *testing.T) {
	ps, err := Providers()
	if err != nil {
		t.Fatalf("Providers: %v", err)
	}
	if len(ps) < 10 {
		t.Fatalf("expected >=10 providers, got %d", len(ps))
	}
	for _, want := range []string{"anthropic", "openai", "ollama", "custom", "groq", "deepseek"} {
		if _, ok := Lookup(want); !ok {
			t.Errorf("registry missing %q", want)
		}
	}
	if _, ok := Lookup("does-not-exist"); ok {
		t.Error("Lookup should miss for unknown ids")
	}
}

func TestNewClientRequiresCredential(t *testing.T) {
	desc := mustDescriptor(t, "openai")
	t.Setenv("OPENAI_API_KEY", "")
	if _, err := NewClient(desc, ""); err == nil {
		t.Fatal("expected auth error without credential")
	} else if e := AsError(err); e == nil || e.Code != ErrCodeAuth || e.ExitCode() != exitcodes.ExitNoAuth {
		t.Fatalf("want classified auth failure with ExitNoAuth, got %v", err)
	}

	envKey(t, "OPENAI_API_KEY")
	c, err := NewClient(desc, "")
	if err != nil {
		t.Fatalf("NewClient with default env: %v", err)
	}
	_ = c
}

func TestNewClientBaseURLRules(t *testing.T) {
	envKey(t, "OPENAI_API_KEY")
	openai := mustDescriptor(t, "openai")

	// openai allows overrides.
	if _, err := NewClient(openai, "", WithBaseURL("https://proxy.example.com/v1")); err != nil {
		t.Errorf("override on overridable provider failed: %v", err)
	}
	// anthropic's descriptor also allows overrides; azure requires one.
	envKey(t, "AZURE_OPENAI_API_KEY")
	azure := mustDescriptor(t, "azure-openai")
	if _, err := NewClient(azure, ""); err == nil {
		t.Error("azure-openai must require a base URL override")
	}
	if _, err := NewClient(azure, "", WithBaseURL("https://myres.openai.azure.com/openai/deployments/d1")); err != nil {
		t.Errorf("azure with override: %v", err)
	}

	// ollama needs no credential at all.
	ollama := mustDescriptor(t, "ollama")
	c, err := NewClient(ollama, "")
	if err != nil {
		t.Errorf("ollama without credential: %v", err)
	} else if c.BaseURL() != "http://localhost:11434/v1" {
		t.Errorf("ollama base url = %q", c.BaseURL())
	}
}

func TestChatOpenAIWire(t *testing.T) {
	var gotReq openaiChatRequest
	var gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		if r.URL.Path != "/chat/completions" {
			t.Errorf("path = %q", r.URL.Path)
		}
		json.NewDecoder(r.Body).Decode(&gotReq)
		w.Header().Set("Content-Type", "application/json")
		io.WriteString(w, `{"choices":[{"message":{"role":"assistant","content":"hello there"},"finish_reason":"stop"}]}`)
	}))
	defer srv.Close()

	envKey(t, "GROQ_API_KEY")
	desc := mustDescriptor(t, "groq")
	c, err := NewClient(desc, "", WithBaseURL(srv.URL))
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	choice, err := c.Chat(context.Background(), "llama-3", []Message{{Role: "user", Content: "hi"}},
		&ChatOptions{System: "be brief"})
	if err != nil {
		t.Fatalf("Chat: %v", err)
	}
	if choice.Content != "hello there" || choice.FinishReason != "stop" {
		t.Errorf("unexpected choice: %+v", choice)
	}
	if gotAuth != "Bearer test-key-123" {
		t.Errorf("auth header = %q", gotAuth)
	}
	if len(gotReq.Messages) != 2 || gotReq.Messages[0].Role != "system" {
		t.Errorf("system prompt not merged: %+v", gotReq.Messages)
	}
	if gotReq.Model != "llama-3" {
		t.Errorf("model = %q", gotReq.Model)
	}
}

func TestChatOpenAIToolUse(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		respBody, _ := json.Marshal(map[string]any{
			"choices": []map[string]any{{
				"message": map[string]any{
					"role":    "assistant",
					"content": "",
					"tool_calls": []map[string]any{{
						"id":       "call_1",
						"type":     "function",
						"function": map[string]any{"name": "get_weather", "arguments": `{"city":"Bonn"}`},
					}},
				},
			}},
			"finish_reason": "tool_calls",
		})
		w.Write(respBody)
	}))
	defer srv.Close()

	envKey(t, "OPENAI_API_KEY")
	c, _ := NewClient(mustDescriptor(t, "openai"), "", WithBaseURL(srv.URL))
	choice, err := c.Chat(context.Background(), "gpt-5", []Message{{Role: "user", Content: "weather?"}},
		&ChatOptions{Tools: []Tool{{Name: "get_weather", Description: "Get weather", InputSchema: json.RawMessage(`{"type":"object"}`)}}})
	if err != nil {
		t.Fatalf("Chat: %v", err)
	}
	if len(choice.ToolCalls) != 1 || choice.ToolCalls[0].Name != "get_weather" {
		t.Fatalf("tool calls = %+v", choice.ToolCalls)
	}
	var args struct{ City string }
	if err := json.Unmarshal(choice.ToolCalls[0].Arguments, &args); err != nil || args.City != "Bonn" {
		t.Errorf("arguments parse: %v %+v", err, args)
	}
}

func TestToolUseRejectedWithoutCapability(t *testing.T) {
	envKey(t, "DEEPSEEK_API_KEY")
	c, _ := NewClient(mustDescriptor(t, "deepseek"), "")
	_, err := c.Chat(context.Background(), "m", []Message{{Role: "user", Content: "x"}},
		&ChatOptions{Tools: []Tool{{Name: "t"}}})
	if err == nil || !strings.Contains(err.Error(), "tool_use") {
		t.Fatalf("want capability error, got %v", err)
	}
}

func TestStreamOpenAI(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(w, "data: {\"choices\":[{\"delta\":{\"content\":\"Hel\"}}]}\n\n")
		io.WriteString(w, "data: {\"choices\":[{\"delta\":{\"content\":\"lo\"}}]}\n\n")
		io.WriteString(w, "data: [DONE]\n\n")
	}))
	defer srv.Close()

	envKey(t, "TOGETHER_API_KEY")
	c, _ := NewClient(mustDescriptor(t, "together"), "", WithBaseURL(srv.URL))
	var sb strings.Builder
	err := c.StreamChat(context.Background(), "m", []Message{{Role: "user", Content: "hi"}}, nil, func(d string) error {
		sb.WriteString(d)
		return nil
	})
	if err != nil {
		t.Fatalf("StreamChat: %v", err)
	}
	if sb.String() != "Hello" {
		t.Errorf("streamed = %q", sb.String())
	}
}

func TestChatAnthropicDialect(t *testing.T) {
	var gotReq anthropicRequest
	gotHeaders := map[string]string{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotHeaders["x-api-key"] = r.Header.Get("x-api-key")
		gotHeaders["anthropic-version"] = r.Header.Get("anthropic-version")
		if !strings.HasSuffix(r.URL.Path, "/messages") {
			t.Errorf("path = %q", r.URL.Path)
		}
		json.NewDecoder(r.Body).Decode(&gotReq)
		io.WriteString(w, `{"content":[{"type":"text","text":"bonjour"}],"stop_reason":"end_turn"}`)
	}))
	defer srv.Close()

	envKey(t, "ANTHROPIC_API_KEY")
	c, err := NewClient(mustDescriptor(t, "anthropic"), "", WithBaseURL(srv.URL))
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	choice, err := c.Chat(context.Background(), "claude-sonnet-5-20250915",
		[]Message{{Role: "system", Content: "sys"}, {Role: "user", Content: "hi"}}, nil)
	if err != nil {
		t.Fatalf("Chat: %v", err)
	}
	if choice.Content != "bonjour" {
		t.Errorf("content = %q", choice.Content)
	}
	if gotHeaders["x-api-key"] != "test-key-123" || gotHeaders["anthropic-version"] != "2023-06-01" {
		t.Errorf("headers = %v", gotHeaders)
	}
	if gotReq.System != "sys" {
		t.Errorf("system field = %q", gotReq.System)
	}
	if len(gotReq.Messages) != 1 || gotReq.Messages[0].Role != "user" {
		t.Errorf("messages = %+v", gotReq.Messages)
	}
	if gotReq.MaxTokens != anthropicDefaultMaxTokens {
		t.Errorf("max_tokens default = %d", gotReq.MaxTokens)
	}
}

func TestErrorClassification(t *testing.T) {
	cases := []struct {
		status int
		body   string
		want   ErrorCode
	}{
		{401, `{"error":{"message":"bad key"}}`, ErrCodeAuth},
		{429, `{}`, ErrCodeRateLimited},
		{400, `{"error":{"code":"context_length_exceeded"}}`, ErrCodeContextOverflow},
		{404, `{}`, ErrCodeModelNotFound},
		{500, `{}`, ErrCodeProvider},
	}
	for _, tc := range cases {
		e := classify(tc.status, tc.body)
		if e.Code != tc.want {
			t.Errorf("status %d body %q: code=%s want=%s", tc.status, tc.body, e.Code, tc.want)
		}
	}
	if e := classify(429, "{}"); !e.Retryable() || e.ExitCode() != exitcodes.ExitConflict {
		t.Errorf("rate limited retryable/exit wrong: %+v", e)
	}
	if e := classify(401, ""); e.Retryable() || e.ExitCode() != exitcodes.ExitNoAuth {
		t.Errorf("auth retryable/exit wrong: %+v", e)
	}
}

func TestTransportErrorClassification(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	url := srv.URL
	srv.Close() // nothing listens anymore

	envKey(t, "OLLAMA_API_KEY")
	ollama := mustDescriptor(t, "ollama")
	c, err := NewClient(ollama, "", WithBaseURL(url))
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	_, err = c.Chat(context.Background(), "llama3.1", []Message{{Role: "user", Content: "hi"}}, nil)
	if err == nil {
		t.Fatal("expected transport failure")
	}
	e := AsError(err)
	if e == nil || e.Code != ErrCodeTransport || !e.Retryable() {
		t.Fatalf("want retryable transport_error, got %v", err)
	}
}

func TestEmbeddings(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"data":[{"embedding":[0.1,0.2]},{"embedding":[0.3,0.4]}]}`)
	}))
	defer srv.Close()

	envKey(t, "MISTRAL_API_KEY")
	c, _ := NewClient(mustDescriptor(t, "mistral"), "", WithBaseURL(srv.URL))
	embs, err := c.Embed(context.Background(), "mistral-embed", []string{"a", "b"})
	if err != nil {
		t.Fatalf("Embed: %v", err)
	}
	if len(embs) != 2 || embs[0].Vector[0] != 0.1 {
		t.Fatalf("embeddings = %+v", embs)
	}

	// deepseek does not promise embeddings.
	envKey(t, "DEEPSEEK_API_KEY")
	c2, _ := NewClient(mustDescriptor(t, "deepseek"), "")
	if _, err := c2.Embed(context.Background(), "m", []string{"a"}); err == nil ||
		!strings.Contains(err.Error(), "embeddings") {
		t.Fatalf("want capability rejection, got %v", err)
	}
}

func TestListModelsDiscovery(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/models":
			io.WriteString(w, `{"data":[{"id":"vendor/big-model"},{"id":"vendor/small"}]}`)
		case "/api/tags":
			io.WriteString(w, `{"models":[{"name":"llama3.1"},{"name":"qwen3"}]}`)
		default:
			t.Errorf("unexpected path %q", r.URL.Path)
		}
	}))
	defer srv.Close()

	envKey(t, "OPENROUTER_API_KEY")
	or, _ := NewClient(mustDescriptor(t, "openrouter"), "", WithBaseURL(srv.URL))
	models, err := or.ListModels(context.Background())
	if err != nil {
		t.Fatalf("ListModels openrouter: %v", err)
	}
	if len(models) != 2 || models[0].ID != "vendor/big-model" {
		t.Fatalf("openrouter models = %+v", models)
	}

	ollama, _ := NewClient(mustDescriptor(t, "ollama"), "", WithBaseURL(srv.URL))
	models, err = ollama.ListModels(context.Background())
	if err != nil {
		t.Fatalf("ListModels ollama: %v", err)
	}
	if len(models) != 2 || models[1].ID != "qwen3" {
		t.Fatalf("ollama models = %+v", models)
	}
}

func TestNativeOllamaSurface(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/generate":
			io.WriteString(w, "{\"model\":\"llama3.1\",\"response\":\"He\",\"done\":false}\n")
			io.WriteString(w, "{\"model\":\"llama3.1\",\"response\":\"llo\",\"done\":true}\n")
		case "/api/chat":
			io.WriteString(w, "{\"model\":\"llama3.1\",\"message\":{\"role\":\"assistant\",\"content\":\"yo\"},\"done\":true}\n")
		default:
			t.Errorf("unexpected path %q", r.URL.Path)
		}
	}))
	defer srv.Close()

	c, _ := NewClient(mustDescriptor(t, "ollama"), "", WithBaseURL(srv.URL))
	var sb strings.Builder
	if err := c.Generate(context.Background(), "", "say hi", func(ch GenerateResponse) error {
		sb.WriteString(ch.Response)
		return nil
	}); err != nil {
		t.Fatalf("Generate: %v", err)
	}
	if sb.String() != "Hello" {
		t.Errorf("generate stream = %q", sb.String())
	}

	var got ChatStreamResponse
	if err := c.ChatStream(context.Background(), "", []Message{{Role: "user", Content: "hi"}}, func(ch ChatStreamResponse) error {
		got = ch
		return nil
	}); err != nil {
		t.Fatalf("ChatStream: %v", err)
	}
	if got.Message.Content != "yo" {
		t.Errorf("chat chunk = %+v", got)
	}

	// Native surface is ollama-only.
	envKey(t, "OPENAI_API_KEY")
	oc, _ := NewClient(mustDescriptor(t, "openai"), "", WithBaseURL(srv.URL))
	if err := oc.Generate(context.Background(), "gpt-5", "p", func(GenerateResponse) error { return nil }); err == nil {
		t.Error("Generate on non-ollama provider must fail")
	}
}

func TestCustomDescriptor(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"choices":[{"message":{"content":"custom works"},"finish_reason":"stop"}]}`)
	}))
	defer srv.Close()

	t.Setenv("MY_VENDOR_KEY", "vendor-key")
	custom := mustDescriptor(t, "custom")
	c, err := NewClient(custom, "env://MY_VENDOR_KEY", WithBaseURL(srv.URL))
	if err != nil {
		t.Fatalf("NewClient custom: %v", err)
	}
	choice, err := c.Chat(context.Background(), "any-model", []Message{{Role: "user", Content: "hi"}}, nil)
	if err != nil {
		t.Fatalf("Chat: %v", err)
	}
	if choice.Content != "custom works" {
		t.Errorf("content = %q", choice.Content)
	}
}

func TestResolveSymvaultReference(t *testing.T) {
	orig := resolveSymvault
	resolveSymvault = func(path string) (string, error) {
		if path != "secrets/anthropic_key" {
			t.Errorf("symvault path = %q", path)
		}
		return "sv-resolved-key", nil
	}
	defer func() { resolveSymvault = orig }()

	key, err := ResolveCredential("symvault://secrets/anthropic_key", "")
	if err != nil || key != "sv-resolved-key" {
		t.Fatalf("ResolveCredential symvault = (%q, %v)", key, err)
	}

	resolveSymvault = func(path string) (string, error) { return "", errors.New("boom") }
	_, err = ResolveCredential("symvault://secrets/x", "")
	e := AsError(err)
	if e == nil || e.Code != ErrCodeAuth {
		t.Fatalf("want auth-classified symvault failure, got %v", err)
	}
}
