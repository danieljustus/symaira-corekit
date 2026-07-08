package ollamakit

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

func ptrFloat32(f float32) *float32 { return &f }

func TestNewDefaults(t *testing.T) {
	c := New(Config{})
	if c.BaseURL() != DefaultBaseURL {
		t.Errorf("baseURL = %q, want %q", c.BaseURL(), DefaultBaseURL)
	}
	if c.Model() != "" {
		t.Errorf("model = %q, want empty", c.Model())
	}
}

func TestNewRespectsConfig(t *testing.T) {
	c := New(Config{BaseURL: "http://example.com/ollama/", Model: "llama3", Timeout: 5 * time.Second})
	if c.BaseURL() != "http://example.com/ollama" {
		t.Errorf("baseURL = %q, want %q", c.BaseURL(), "http://example.com/ollama")
	}
	if c.Model() != "llama3" {
		t.Errorf("model = %q, want llama3", c.Model())
	}
}

func TestNewFromEnv(t *testing.T) {
	os.Setenv("OLLAMAKIT_TEST_BASE_URL", "http://env.example")
	os.Setenv("OLLAMAKIT_TEST_MODEL", "env-model")
	os.Setenv("OLLAMAKIT_TEST_TIMEOUT", "3s")
	defer os.Unsetenv("OLLAMAKIT_TEST_BASE_URL")
	defer os.Unsetenv("OLLAMAKIT_TEST_MODEL")
	defer os.Unsetenv("OLLAMAKIT_TEST_TIMEOUT")

	c := NewFromEnv("OLLAMAKIT_TEST")
	if c.BaseURL() != "http://env.example" {
		t.Errorf("baseURL = %q, want env value", c.BaseURL())
	}
	if c.Model() != "env-model" {
		t.Errorf("model = %q, want env-model", c.Model())
	}
}

func TestParseBaseURLAndTimeout(t *testing.T) {
	if got := ParseBaseURL(" http://host/  "); got != "http://host" {
		t.Errorf("ParseBaseURL = %q, want http://host", got)
	}
	if got := ParseBaseURL(""); got != DefaultBaseURL {
		t.Errorf("ParseBaseURL empty = %q, want default", got)
	}
	if d, err := ParseTimeout("10"); err != nil || d != 10*time.Second {
		t.Errorf("ParseTimeout(10) = %v, %v", d, err)
	}
	if d, err := ParseTimeout("500ms"); err != nil || d != 500*time.Millisecond {
		t.Errorf("ParseTimeout(500ms) = %v, %v", d, err)
	}
	if d, err := ParseTimeout(""); err != nil || d != DefaultTimeout {
		t.Errorf("ParseTimeout empty = %v, %v", d, err)
	}
	if _, err := ParseTimeout("not-a-duration"); err == nil {
		t.Error("expected error for invalid duration")
	}
}

func TestEmbed(t *testing.T) {
	want := [][]float32{{1, 2, 3}, {4, 5, 6}}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/embed" {
			t.Errorf("path = %q, want /api/embed", r.URL.Path)
		}
		if r.Method != http.MethodPost {
			t.Errorf("method = %q, want POST", r.Method)
		}
		body, _ := io.ReadAll(r.Body)
		var req embedRequest
		if err := json.Unmarshal(body, &req); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		if req.Model != "mxbai" {
			t.Errorf("model = %q, want mxbai", req.Model)
		}
		if len(req.Input) != 2 {
			t.Errorf("input len = %d, want 2", len(req.Input))
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(embedResponse{Embeddings: want})
	}))
	defer server.Close()

	c := New(Config{BaseURL: server.URL, Model: "mxbai"})
	got, err := c.Embed(context.Background(), "", []string{"hello", "world"})
	if err != nil {
		t.Fatalf("Embed error: %v", err)
	}
	if len(got) != len(want) {
		t.Fatalf("len = %d, want %d", len(got), len(want))
	}
	for i := range want {
		if len(got[i]) != len(want[i]) {
			t.Fatalf("embedding %d len", i)
		}
		for j := range want[i] {
			if got[i][j] != want[i][j] {
				t.Errorf("embedding [%d][%d] = %v, want %v", i, j, got[i][j], want[i][j])
			}
		}
	}
}

func TestEmbedRequiresModel(t *testing.T) {
	c := New(Config{BaseURL: "http://unused"})
	if _, err := c.Embed(context.Background(), "", []string{"x"}); err == nil {
		t.Error("expected error without model")
	}
}

func TestEmbedEmptyInputs(t *testing.T) {
	c := New(Config{BaseURL: "http://unused", Model: "m"})
	if _, err := c.Embed(context.Background(), "", nil); err == nil {
		t.Error("expected error for empty inputs")
	}
}

func TestGenerate(t *testing.T) {
	chunks := []string{"Hello, ", "world", "!"}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/generate" {
			t.Errorf("path = %q, want /api/generate", r.URL.Path)
		}
		body, _ := io.ReadAll(r.Body)
		if !strings.Contains(string(body), `"prompt":"say hi"`) {
			t.Errorf("request body missing prompt: %s", body)
		}
		if !strings.Contains(string(body), `"stream":true`) {
			t.Errorf("request body missing stream flag: %s", body)
		}
		w.Header().Set("Content-Type", "application/x-ndjson")
		for i, text := range chunks {
			json.NewEncoder(w).Encode(GenerateResponse{
				Model:    "llama3",
				Response: text,
				Done:     i == len(chunks)-1,
			})
		}
	}))
	defer server.Close()

	c := New(Config{BaseURL: server.URL, Model: "llama3"})
	var got []string
	err := c.Generate(context.Background(), "", "say hi", &GenerateOptions{Temperature: ptrFloat32(0.5)}, func(resp GenerateResponse) error {
		got = append(got, resp.Response)
		if resp.Done && resp.Response != chunks[len(chunks)-1] {
			t.Errorf("done response = %q, want %q", resp.Response, chunks[len(chunks)-1])
		}
		return nil
	})
	if err != nil {
		t.Fatalf("Generate error: %v", err)
	}
	if len(got) != len(chunks) {
		t.Fatalf("got %d chunks, want %d", len(got), len(chunks))
	}
	for i := range chunks {
		if got[i] != chunks[i] {
			t.Errorf("chunk %d = %q, want %q", i, got[i], chunks[i])
		}
	}
}

func TestGenerateCallbackError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/x-ndjson")
		json.NewEncoder(w).Encode(GenerateResponse{Response: "one", Done: false})
		json.NewEncoder(w).Encode(GenerateResponse{Response: "two", Done: true})
	}))
	defer server.Close()

	c := New(Config{BaseURL: server.URL, Model: "m"})
	var calls int
	err := c.Generate(context.Background(), "", "p", nil, func(resp GenerateResponse) error {
		calls++
		return fmt.Errorf("stop here")
	})
	if err == nil || err.Error() != "stop here" {
		t.Fatalf("expected callback error, got: %v", err)
	}
	if calls != 1 {
		t.Errorf("calls = %d, want 1", calls)
	}
}

func TestGenerateMidStreamError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/x-ndjson")
		flusher, ok := w.(http.Flusher)
		if !ok {
			t.Fatal("expected flusher")
		}
		json.NewEncoder(w).Encode(GenerateResponse{Response: "partial ", Done: false})
		flusher.Flush()
		// Simulate a dropped connection.
		hj, ok := w.(http.Hijacker)
		if !ok {
			t.Fatal("expected hijacker")
		}
		conn, _, _ := hj.Hijack()
		conn.Close()
	}))
	defer server.Close()

	c := New(Config{BaseURL: server.URL, Model: "m"})
	var got string
	err := c.Generate(context.Background(), "", "p", nil, func(resp GenerateResponse) error {
		got += resp.Response
		return nil
	})
	if err == nil {
		t.Fatal("expected error on dropped stream")
	}
	if !errors.Is(err, ErrStream) {
		t.Errorf("expected ErrStream, got %v", err)
	}
	if got != "partial " {
		t.Errorf("got = %q, want partial ", got)
	}
}

func TestChat(t *testing.T) {
	messages := []Message{{Role: "user", Content: "hello"}}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/chat" {
			t.Errorf("path = %q, want /api/chat", r.URL.Path)
		}
		body, _ := io.ReadAll(r.Body)
		if !strings.Contains(string(body), `"messages"`) {
			t.Errorf("request body missing messages: %s", body)
		}
		w.Header().Set("Content-Type", "application/x-ndjson")
		json.NewEncoder(w).Encode(ChatResponse{Model: "llama3", Message: Message{Role: "assistant", Content: "Hi"}, Done: false})
		json.NewEncoder(w).Encode(ChatResponse{Model: "llama3", Message: Message{Role: "assistant", Content: " there"}, Done: true})
	}))
	defer server.Close()

	c := New(Config{BaseURL: server.URL, Model: "llama3"})
	var content string
	err := c.Chat(context.Background(), "", messages, &ChatOptions{Temperature: ptrFloat32(0.7)}, func(resp ChatResponse) error {
		content += resp.Message.Content
		return nil
	})
	if err != nil {
		t.Fatalf("Chat error: %v", err)
	}
	if content != "Hi there" {
		t.Errorf("content = %q, want Hi there", content)
	}
}

func TestChatEmptyMessages(t *testing.T) {
	c := New(Config{BaseURL: "http://unused", Model: "m"})
	if err := c.Chat(context.Background(), "", nil, nil, func(ChatResponse) error { return nil }); err == nil {
		t.Error("expected error for empty messages")
	}
}

func TestListModels(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/tags" {
			t.Errorf("path = %q, want /api/tags", r.URL.Path)
		}
		if r.Method != http.MethodGet {
			t.Errorf("method = %q, want GET", r.Method)
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(modelsResponse{Models: []ModelInfo{{Name: "llama3", Size: 42}}})
	}))
	defer server.Close()

	c := New(Config{BaseURL: server.URL})
	models, err := c.ListModels(context.Background())
	if err != nil {
		t.Fatalf("ListModels error: %v", err)
	}
	if len(models) != 1 || models[0].Name != "llama3" {
		t.Errorf("models = %+v", models)
	}
}

func TestPing(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(modelsResponse{Models: []ModelInfo{}})
	}))
	defer server.Close()

	c := New(Config{BaseURL: server.URL})
	if err := c.Ping(context.Background()); err != nil {
		t.Fatalf("Ping error: %v", err)
	}
}

func TestModelNotFound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		json.NewEncoder(w).Encode(map[string]string{"error": "model 'missing' not found"})
	}))
	defer server.Close()

	c := New(Config{BaseURL: server.URL, Model: "missing"})
	if _, err := c.Embed(context.Background(), "", []string{"x"}); !errors.Is(err, ErrModelNotFound) {
		t.Errorf("expected ErrModelNotFound, got %v", err)
	}
	if err := c.Generate(context.Background(), "", "p", nil, func(GenerateResponse) error { return nil }); !errors.Is(err, ErrModelNotFound) {
		t.Errorf("expected ErrModelNotFound for generate, got %v", err)
	}
	if err := c.Chat(context.Background(), "", []Message{{Role: "user", Content: "x"}}, nil, func(ChatResponse) error { return nil }); !errors.Is(err, ErrModelNotFound) {
		t.Errorf("expected ErrModelNotFound for chat, got %v", err)
	}
}

func TestUnexpectedResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		fmt.Fprintln(w, "boom")
	}))
	defer server.Close()

	c := New(Config{BaseURL: server.URL, Model: "m"})
	if _, err := c.Embed(context.Background(), "", []string{"x"}); !errors.Is(err, ErrResponse) {
		t.Errorf("expected ErrResponse, got %v", err)
	}
}

// TestResponseErrorExposesStatusCode verifies that a non-2xx, non-404
// response surfaces a *ResponseError callers can use to classify a failure
// as transient (5xx) versus not, without parsing the error string.
func TestResponseErrorExposesStatusCode(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		io.WriteString(w, "upstream down")
	}))
	defer server.Close()

	c := New(Config{BaseURL: server.URL, Model: "m"})
	_, err := c.Embed(context.Background(), "", []string{"x"})
	if !errors.Is(err, ErrResponse) {
		t.Fatalf("expected ErrResponse, got %v", err)
	}
	var respErr *ResponseError
	if !errors.As(err, &respErr) {
		t.Fatalf("expected *ResponseError, got %T: %v", err, err)
	}
	if respErr.StatusCode != http.StatusBadGateway {
		t.Errorf("expected StatusCode %d, got %d", http.StatusBadGateway, respErr.StatusCode)
	}
	if respErr.Body != "upstream down" {
		t.Errorf("expected Body %q, got %q", "upstream down", respErr.Body)
	}
}

func TestUnreachable(t *testing.T) {
	c := New(Config{BaseURL: "http://localhost:1", Model: "m", Timeout: 500 * time.Millisecond})
	if _, err := c.Embed(context.Background(), "", []string{"x"}); !errors.Is(err, ErrUnreachable) {
		t.Errorf("expected ErrUnreachable, got %v", err)
	}
	if err := c.Ping(context.Background()); !errors.Is(err, ErrUnreachable) {
		t.Errorf("expected ErrUnreachable for ping, got %v", err)
	}
}

func TestGenerateRequiresCallback(t *testing.T) {
	c := New(Config{BaseURL: "http://unused", Model: "m"})
	if err := c.Generate(context.Background(), "", "p", nil, nil); err == nil {
		t.Error("expected error for nil callback")
	}
}

func TestChatRequiresCallback(t *testing.T) {
	c := New(Config{BaseURL: "http://unused", Model: "m"})
	if err := c.Chat(context.Background(), "", []Message{{Role: "user", Content: "x"}}, nil, nil); err == nil {
		t.Error("expected error for nil callback")
	}
}

// TestRedirectNotFollowed verifies that the client does not follow a
// redirect response — a redirected Ollama host is treated as an error, not
// silently rerouted, so a misconfigured or hostile endpoint cannot bounce
// requests to an unexpected host.
func TestRedirectNotFollowed(t *testing.T) {
	var targetHits int32
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		targetHits++
		w.WriteHeader(http.StatusOK)
	}))
	defer target.Close()

	var redirectorHits int32
	redirector := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		redirectorHits++
		http.Redirect(w, r, target.URL, http.StatusMovedPermanently)
	}))
	defer redirector.Close()

	c := New(Config{BaseURL: redirector.URL, Model: "m"})
	if _, err := c.Embed(context.Background(), "", []string{"x"}); err == nil {
		t.Fatal("expected an error from the redirect response, got nil")
	}
	if redirectorHits != 1 {
		t.Errorf("expected 1 hit on the redirector, got %d", redirectorHits)
	}
	if targetHits != 0 {
		t.Errorf("expected 0 hits on the redirect target (redirect was followed!), got %d", targetHits)
	}
}
