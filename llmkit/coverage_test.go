//nolint:gosec // G104/G204: ignored write errors and the exec indirection are intentional in tests
package llmkit

// Behavioral coverage for the error/dialect branches of the llmkit provider
// layer (issue #183). Every test asserts real behavior — error codes,
// request shapes, headers, stream handling — not mere line execution.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"strings"
	"testing"

	"github.com/danieljustus/symaira-corekit/exitcodes"
)

// withCopy returns a shallow copy of a registry descriptor with mut applied.
// Copies let tests flip capability flags without touching the embedded registry.
func withCopy(t *testing.T, id string, mut func(*Descriptor)) Descriptor {
	t.Helper()
	d := mustDescriptor(t, id)
	mut(&d)
	return d
}

// failingBody is an io.ReadCloser that returns data first, then a hard error —
// deterministic stand-in for a mid-stream connection failure.
type failingBody struct {
	data   string
	offset int
	err    error
}

func (b *failingBody) Read(p []byte) (int, error) {
	if b.offset < len(b.data) {
		n := copy(p, b.data[b.offset:])
		b.offset += n
		return n, nil
	}
	return 0, b.err
}

func (b *failingBody) Close() error { return nil }

// failingTransport returns fixed responses whose body eventually fails to
// read, so ReadAll/scanner error paths are exercised without flaky TCP.
type failingTransport struct {
	status int
	header http.Header
	body   string
	err    error
}

func (t *failingTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	h := http.Header{}
	for k, v := range t.header {
		h[k] = v
	}
	return &http.Response{
		StatusCode: t.status,
		Status:     fmt.Sprintf("%d %s", t.status, http.StatusText(t.status)),
		Header:     h,
		Body:       &failingBody{data: t.body, err: t.err},
		Request:    req,
	}, nil
}

func ollamaClient(t *testing.T, srvURL string, opts ...Option) *Client {
	t.Helper()
	c, err := NewClient(mustDescriptor(t, "ollama"), "", append([]Option{WithBaseURL(srvURL)}, opts...)...)
	if err != nil {
		t.Fatalf("NewClient ollama: %v", err)
	}
	return c
}

// --- client.go ------------------------------------------------------------

func TestOptionSetters(t *testing.T) {
	cfg := clientConfig{}
	WithDialect(DialectAnthropic)(&cfg)
	if cfg.dialect != DialectAnthropic {
		t.Errorf("WithDialect cfg = %q", cfg.dialect)
	}
	WithTimeout(42)(&cfg)
	if cfg.timeout != 42 {
		t.Errorf("WithTimeout cfg = %v", cfg.timeout)
	}
	hc := &http.Client{}
	WithHTTPClient(hc)(&cfg)
	if cfg.httpClient != hc {
		t.Error("WithHTTPClient cfg not applied")
	}
}

func TestNewClientRejectsInvalidDescriptor(t *testing.T) {
	_, err := NewClient(Descriptor{ID: "bogus", Dialect: "grpc", BaseURL: "http://x"}, "")
	if err == nil || !strings.Contains(err.Error(), "unknown dialect") {
		t.Fatalf("want unknown-dialect validation error, got %v", err)
	}
}

func TestNewClientRejectsUnexpectedBaseURLOverride(t *testing.T) {
	d := withCopy(t, "ollama", func(d *Descriptor) { d.BaseURLOverridable = false })
	if _, err := NewClient(d, "", WithBaseURL("http://localhost:9999")); err == nil ||
		!strings.Contains(err.Error(), "does not allow base URL overrides") {
		t.Fatalf("want override rejection, got %v", err)
	}
}

func TestClientHelpers(t *testing.T) {
	c := ollamaClient(t, "http://localhost:11434/v1")
	if c.Descriptor().ID != "ollama" {
		t.Errorf("Descriptor() = %q", c.Descriptor().ID)
	}
	if c.BaseURL() != "http://localhost:11434/v1" {
		t.Errorf("BaseURL() = %q", c.BaseURL())
	}
}

func TestDoFollowsNoRedirects(t *testing.T) {
	hitTarget := false
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hitTarget = true
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()
	redir := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, srv.URL, http.StatusFound)
	}))
	defer redir.Close()

	c := ollamaClient(t, redir.URL)
	resp, err := c.do(context.Background(), http.MethodGet, "/x", nil, "")
	if err == nil {
		resp.Body.Close()
		t.Fatal("expected error for 302 (redirects are configured to stop)")
	}
	e := AsError(err)
	if e == nil || e.StatusCode != http.StatusFound {
		t.Fatalf("want status 302 classified error, got %v", err)
	}
	if hitTarget {
		t.Error("redirect target was reached; CheckRedirect must use ErrUseLastResponse")
	}
}

func TestDoEncodeAndURLFailures(t *testing.T) {
	c := ollamaClient(t, "http://localhost:11434/v1")

	// Body that json.Marshal cannot encode.
	_, err := c.do(context.Background(), http.MethodPost, "/x", make(chan int), "application/json")
	if e := AsError(err); e == nil || e.Code != ErrCodeProvider || !strings.Contains(err.Error(), "encode request") {
		t.Fatalf("want encode-request provider error, got %v", err)
	}

	// Base URL that url.JoinPath cannot parse.
	c2, err := NewClient(mustDescriptor(t, "ollama"), "", WithBaseURL("://"))
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	_, err = c2.do(context.Background(), http.MethodPost, "/x", struct{}{}, "application/json")
	if e := AsError(err); e == nil || !strings.Contains(err.Error(), "build url") {
		t.Fatalf("want build-url provider error, got %v", err)
	}
}

func TestDoKeepsRetryAfterHeader(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Retry-After", "7")
		http.Error(w, "slow down", http.StatusTooManyRequests)
	}))
	defer srv.Close()

	c := ollamaClient(t, srv.URL)
	_, err := c.do(context.Background(), http.MethodPost, "/chat/completions", struct{}{}, "application/json")
	e := AsError(err)
	if e == nil || e.Code != ErrCodeRateLimited || e.RetryAfter != "7" {
		t.Fatalf("want rate-limited error with RetryAfter=7, got %v", err)
	}
}

func TestAuthHeaderDefaultsToAuthorization(t *testing.T) {
	got := make(chan string, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got <- r.Header.Get("Authorization")
		io.WriteString(w, `{"content":[{"type":"text","text":"hi"}]}`)
	}))
	defer srv.Close()

	envKey(t, "ANTHROPIC_API_KEY")
	d := withCopy(t, "anthropic", func(d *Descriptor) { d.AuthHeader = "" })
	c, err := NewClient(d, "", WithBaseURL(srv.URL))
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	if _, err := c.Chat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil); err != nil {
		t.Fatalf("Chat: %v", err)
	}
	if h := <-got; h != "test-key-123" {
		t.Errorf("Authorization header = %q", h)
	}
}

func TestResolveCredentialValidation(t *testing.T) {
	if _, err := ResolveCredential("", ""); AsError(err) == nil ||
		!strings.Contains(err.Error(), "no credential reference") {
		t.Fatalf("want missing-reference error, got %v", err)
	}
	if _, err := ResolveCredential("env://LLMKIT_DEFINITELY_UNSET", ""); AsError(err) == nil ||
		!strings.Contains(err.Error(), "not set") {
		t.Fatalf("want unset-env error, got %v", err)
	}
	if _, err := ResolveCredential("LLMKIT_DEFINITELY_UNSET", ""); AsError(err) == nil {
		t.Fatalf("bare env name must behave like env://, got %v", err)
	}
	// keychain:// is a Swift-side reference; llmkit must refuse it.
	_, err := ResolveCredential("keychain://svc/acct", "")
	if err == nil || !strings.Contains(err.Error(), "Swift half") {
		t.Fatalf("keychain ref must be refused with the Swift-side note, got %v", err)
	}
}

// helperProcess re-executes the test binary in a fake-CLI mode so the real
// resolveSymvault exec path can be exercised platform-neutrally.
func helperProcess(t *testing.T) {
	t.Helper()
	if os.Getenv("LLMKIT_HELPER_PROCESS") != "1" {
		t.Skip("helper subprocess target")
	}
	fmt.Println("secret-key-from-vault")
	os.Exit(0)
}

func TestResolveSymvaultExecPath(t *testing.T) {
	orig := execCommand
	execCommand = func(name string, args ...string) *exec.Cmd {
		c := exec.Command(os.Args[0], "-test.run=TestHelperResolveSymvault")
		c.Env = append(os.Environ(), "LLMKIT_HELPER_PROCESS=1")
		return c
	}
	defer func() { execCommand = orig }()

	// Success path: symvault prints the secret on stdout.
	key, err := ResolveCredential("symvault://secrets/ai_key", "")
	if err != nil || key != "secret-key-from-vault" {
		t.Fatalf("symvault resolution = (%q, %v)", key, err)
	}
}

func TestHelperResolveSymvault(t *testing.T) { helperProcess(t) }

func TestResolveSymvaultExecFailure(t *testing.T) {
	orig := execCommand
	execCommand = func(name string, args ...string) *exec.Cmd {
		c := exec.Command(os.Args[0], "-test.run=TestHelperResolveSymvaultFail")
		c.Env = append(os.Environ(), "LLMKIT_HELPER_PROCESS=1")
		return c
	}
	defer func() { execCommand = orig }()

	_, err := ResolveCredential("symvault://secrets/missing", "")
	e := AsError(err)
	if e == nil || e.Code != ErrCodeAuth {
		t.Fatalf("want auth-classified symvault exec failure, got %v", err)
	}
}

func TestHelperResolveSymvaultFail(t *testing.T) {
	if os.Getenv("LLMKIT_HELPER_PROCESS") != "1" {
		t.Skip("helper subprocess target")
	}
	fmt.Fprintln(os.Stderr, "entry not found")
	os.Exit(1)
}

func TestExecCommandIndirection(t *testing.T) {
	// The real execCommand hook must produce a runnable command (issue #183
	// coverage: exec.go package-level indirection).
	cmd := execCommand("go", "version")
	out, err := cmd.Output()
	if err != nil {
		t.Fatalf("execCommand go version: %v", err)
	}
	if !strings.Contains(string(out), "go version") {
		t.Errorf("go version output = %q", out)
	}
}

func TestRetryAfterSeconds(t *testing.T) {
	cases := []struct {
		in     string
		wantN  int
		wantOK bool
	}{
		{"30", 30, true},
		{"", 0, false},
		{"soon", 0, false},
		{"-5", 0, false},
	}
	for _, tc := range cases {
		n, ok := retryAfterSeconds(tc.in)
		if n != tc.wantN || ok != tc.wantOK {
			t.Errorf("retryAfterSeconds(%q) = (%d, %v), want (%d, %v)", tc.in, n, ok, tc.wantN, tc.wantOK)
		}
	}
}

// --- chat.go --------------------------------------------------------------

func TestChatValidationAndDialectSwitch(t *testing.T) {
	d := withCopy(t, "ollama", func(d *Descriptor) { d.Models.Default = "" })
	c, err := NewClient(d, "", WithBaseURL("http://localhost:11434/v1"))
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	if _, err := c.Chat(context.Background(), "", []Message{{Role: "user", Content: "x"}}, nil); err == nil ||
		!strings.Contains(err.Error(), "model is required") {
		t.Fatalf("want model-required error, got %v", err)
	}
	if _, err := c.Chat(context.Background(), "m", nil, nil); err == nil ||
		!strings.Contains(err.Error(), "messages must not be empty") {
		t.Fatalf("want empty-messages error, got %v", err)
	}

	custom, err := NewClient(mustDescriptor(t, "ollama"), "", WithBaseURL("http://x"), WithDialect("weird"))
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	if _, err := custom.Chat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil); err == nil ||
		!strings.Contains(err.Error(), "unsupported dialect") {
		t.Fatalf("want unsupported-dialect error, got %v", err)
	}
	if err := custom.StreamChat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil, func(string) error { return nil }); err == nil ||
		!strings.Contains(err.Error(), "unsupported dialect") {
		t.Fatalf("want unsupported-dialect stream error, got %v", err)
	}
}

func TestChatOpenAIStructuredErrorImprovement(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":{"message":"invalid api key","type":"authentication_error"}}`, http.StatusBadRequest)
	}))
	defer srv.Close()

	c := ollamaClient(t, srv.URL)
	_, err := c.Chat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil)
	e := AsError(err)
	if e == nil || e.Code != ErrCodeAuth {
		t.Fatalf("structured 400 body must be re-classified as auth, got %v", err)
	}
}

func TestChatOpenAIResponseFailures(t *testing.T) {
	t.Run("read failure", func(t *testing.T) {
		tr := &failingTransport{status: 200, body: `{"choices":[`, err: io.ErrUnexpectedEOF}
		c, _ := NewClient(mustDescriptor(t, "ollama"), "", WithHTTPClient(&http.Client{Transport: tr}))
		_, err := c.Chat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil)
		if e := AsError(err); e == nil || e.Code != ErrCodeTransport {
			t.Fatalf("want transport error on mid-body failure, got %v", err)
		}
	})
	t.Run("decode failure", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			io.WriteString(w, `this is not json`)
		}))
		defer srv.Close()
		c := ollamaClient(t, srv.URL)
		_, err := c.Chat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil)
		if e := AsError(err); e == nil || e.Code != ErrCodeProvider || !strings.Contains(err.Error(), "decode chat response") {
			t.Fatalf("want decode error, got %v", err)
		}
	})
	t.Run("no choices", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			io.WriteString(w, `{"choices":[]}`)
		}))
		defer srv.Close()
		c := ollamaClient(t, srv.URL)
		_, err := c.Chat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil)
		if e := AsError(err); e == nil || e.Code != ErrCodeProvider || !strings.Contains(err.Error(), "no choices") {
			t.Fatalf("want no-choices error, got %v", err)
		}
	})
}

func TestStreamChatValidation(t *testing.T) {
	d := withCopy(t, "ollama", func(d *Descriptor) { d.Capabilities.Streaming = false })
	c, err := NewClient(d, "", WithBaseURL("http://localhost:11434/v1"))
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	if err := c.StreamChat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil, func(string) error { return nil }); err == nil ||
		!strings.Contains(err.Error(), "does not promise streaming") {
		t.Fatalf("want streaming-capability error, got %v", err)
	}

	d2 := withCopy(t, "ollama", func(d *Descriptor) { d.Models.Default = "" })
	c2, err := NewClient(d2, "", WithBaseURL("http://localhost:11434/v1"))
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	if err := c2.StreamChat(context.Background(), "", []Message{{Role: "user", Content: "x"}}, nil, func(string) error { return nil }); err == nil ||
		!strings.Contains(err.Error(), "model is required") {
		t.Fatalf("want model-required stream error, got %v", err)
	}
}

func TestStreamOpenAIChunkVariants(t *testing.T) {
	var sb strings.Builder
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(w, "data: not-json\n\n")                                       // decode failure
		io.WriteString(w, "data: {\"choices\":[]}\n\n")                               // no choices
		io.WriteString(w, "data: {\"choices\":[{\"delta\":{\"content\":\"\"}}]}\n\n") // empty delta
		io.WriteString(w, "data: {\"choices\":[{\"delta\":{\"content\":\"ok\"}}]}\n\n")
		io.WriteString(w, "data: [DONE]\n\n")
	}))
	defer srv.Close()

	c := ollamaClient(t, srv.URL)
	err := c.StreamChat(context.Background(), "llama3.1", []Message{{Role: "user", Content: "x"}},
		&ChatOptions{Temperature: ptr(0.5), MaxTokens: 10}, func(d string) error { sb.WriteString(d); return nil })
	if err == nil || !strings.Contains(err.Error(), "decode stream chunk") {
		t.Fatalf("invalid first chunk must abort the stream, got %v", err)
	}
	if sb.String() != "" {
		t.Errorf("no deltas may be delivered before the corrupt chunk, got %q", sb.String())
	}
}

func TestStreamOpenAIToleratesChoicelessAndEmptyDeltas(t *testing.T) {
	var sb strings.Builder
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(w, "data: {\"choices\":[]}\n\n")
		io.WriteString(w, "data: {\"choices\":[{\"delta\":{\"content\":\"\"}}]}\n\n")
		io.WriteString(w, "data: {\"choices\":[{\"delta\":{\"content\":\"ok\"}}]}\n\n")
		io.WriteString(w, "data: [DONE]\n\n")
	}))
	defer srv.Close()

	c := ollamaClient(t, srv.URL)
	err := c.StreamChat(context.Background(), "llama3.1", []Message{{Role: "user", Content: "x"}}, &ChatOptions{Temperature: ptr(0.5), MaxTokens: 10},
		func(d string) error { sb.WriteString(d); return nil })
	if err != nil {
		t.Fatalf("StreamChat: %v", err)
	}
	if sb.String() != "ok" {
		t.Errorf("streamed deltas = %q, want only 'ok'", sb.String())
	}
}

func ptr[T any](v T) *T { return &v }

func TestStreamSSEScannerFailures(t *testing.T) {
	t.Run("error before any data", func(t *testing.T) {
		tr := &failingTransport{status: 200, body: "", err: io.ErrUnexpectedEOF}
		c, _ := NewClient(mustDescriptor(t, "ollama"), "", WithHTTPClient(&http.Client{Transport: tr}))
		err := c.StreamChat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil, func(string) error { return nil })
		if e := AsError(err); e == nil || e.Code != ErrCodeTransport {
			t.Fatalf("want transport error for empty broken stream, got %v", err)
		}
	})
	t.Run("error after data", func(t *testing.T) {
		tr := &failingTransport{status: 200, body: "data: {\"choices\":[{\"delta\":{\"content\":\"x\"}}]}\n\n", err: io.ErrUnexpectedEOF}
		c, _ := NewClient(mustDescriptor(t, "ollama"), "", WithHTTPClient(&http.Client{Transport: tr}))
		err := c.StreamChat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil, func(string) error { return nil })
		e := AsError(err)
		if e == nil || e.Code != ErrCodeTransport || !strings.Contains(err.Error(), "stream interrupted") {
			t.Fatalf("want stream-interrupted transport error, got %v", err)
		}
	})
	t.Run("no data at all", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK) // 200 with empty body, no event
		}))
		defer srv.Close()
		c := ollamaClient(t, srv.URL)
		err := c.StreamChat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil, func(string) error { return nil })
		if e := AsError(err); e == nil || e.Code != ErrCodeProvider || !strings.Contains(err.Error(), "no stream data") {
			t.Fatalf("want no-stream-data error, got %v", err)
		}
	})
	t.Run("transport error", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
		url := srv.URL
		srv.Close()
		c := ollamaClient(t, url)
		err := c.StreamChat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil, func(string) error { return nil })
		if e := AsError(err); e == nil || e.Code != ErrCodeTransport {
			t.Fatalf("want transport error, got %v", err)
		}
	})
}

func TestClassifyFromTypedMarkers(t *testing.T) {
	if e := classifyFromTyped(http.StatusBadRequest, "authentication_error", "bad key"); e.Code != ErrCodeAuth {
		t.Errorf("auth marker: code = %s", e.Code)
	}
	if e := classifyFromTyped(http.StatusBadRequest, "rate_limit_error", "overloaded"); e.Code != ErrCodeRateLimited {
		t.Errorf("rate-limit marker: code = %s", e.Code)
	}
	if e := classifyFromTyped(http.StatusBadRequest, "not_found", "no such model"); e.Code != ErrCodeModelNotFound {
		t.Errorf("not-found marker: code = %s", e.Code)
	}
	if e := classifyFromTyped(http.StatusBadRequest, "server_error", "mystery"); e.Code != ErrCodeProvider {
		t.Errorf("unmatched type must stay provider-error, got %s", e.Code)
	}
	if containsAny("plain text", "auth", "rate") {
		t.Error("containsAny must miss absent markers")
	}
}

func TestBuildAnthropicRequest(t *testing.T) {
	c := ollamaClient(t, "http://localhost:11434/v1")
	req := c.buildAnthropicRequest("claude", []Message{
		{Role: "system", Content: "first"},
		{Role: "system", Content: "second"},
		{Role: "user", Content: "hi"},
	}, &ChatOptions{MaxTokens: 321, System: "opts-sys", Tools: []Tool{
		{Name: "f", Description: "d", InputSchema: json.RawMessage(`{"type":"object"}`)},
	}}, false)
	if req.MaxTokens != 321 {
		t.Errorf("MaxTokens = %d", req.MaxTokens)
	}
	if req.System != "opts-sys\n\nfirst\n\nsecond" {
		t.Errorf("System = %q", req.System)
	}
	if len(req.Messages) != 1 || req.Messages[0].Role != "user" {
		t.Errorf("Messages = %+v", req.Messages)
	}
	if len(req.Tools) != 1 || req.Tools[0].Name != "f" || string(req.Tools[0].InputSchema) != `{"type":"object"}` {
		t.Errorf("Tools = %+v", req.Tools)
	}
	// No opts: default max tokens, system only from messages.
	req2 := c.buildAnthropicRequest("claude", []Message{{Role: "user", Content: "hi"}}, nil, false)
	if req2.MaxTokens != anthropicDefaultMaxTokens {
		t.Errorf("default MaxTokens = %d", req2.MaxTokens)
	}
}

func TestChatAnthropicFailures(t *testing.T) {
	t.Run("decode failure", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			io.WriteString(w, `not json`)
		}))
		defer srv.Close()
		envKey(t, "ANTHROPIC_API_KEY")
		c, _ := NewClient(mustDescriptor(t, "anthropic"), "", WithBaseURL(srv.URL))
		_, err := c.Chat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil)
		if e := AsError(err); e == nil || e.Code != ErrCodeProvider || !strings.Contains(err.Error(), "decode anthropic") {
			t.Fatalf("want anthropic decode error, got %v", err)
		}
	})
	t.Run("read failure", func(t *testing.T) {
		tr := &failingTransport{status: 200, body: `{"cont`, err: io.ErrUnexpectedEOF}
		d := withCopy(t, "anthropic", func(d *Descriptor) { d.BaseURLOverridable = true })
		envKey(t, "ANTHROPIC_API_KEY")
		c, err := NewClient(d, "env://ANTHROPIC_API_KEY", WithHTTPClient(&http.Client{Transport: tr}))
		if err != nil {
			t.Fatalf("NewClient: %v", err)
		}
		_, err = c.Chat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil)
		if e := AsError(err); e == nil || e.Code != ErrCodeTransport {
			t.Fatalf("want transport error, got %v", err)
		}
	})
	t.Run("transport failure", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
		url := srv.URL
		srv.Close()
		envKey(t, "ANTHROPIC_API_KEY")
		c, _ := NewClient(mustDescriptor(t, "anthropic"), "", WithBaseURL(url))
		_, err := c.Chat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil)
		if e := AsError(err); e == nil || e.Code != ErrCodeTransport {
			t.Fatalf("want transport error, got %v", err)
		}
	})
}

func TestStreamAnthropicDialect(t *testing.T) {
	var sb strings.Builder
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(w, "data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"Hel\"}}\n\n")
		io.WriteString(w, "data: {\"type\":\"message_stop\"}\n\n")
		io.WriteString(w, "data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"lo\"}}\n\n")
		io.WriteString(w, "data: broken-json\n\n") // unknown shapes are skipped, not fatal
		io.WriteString(w, "data: [DONE]\n\n")
	}))
	defer srv.Close()

	envKey(t, "ANTHROPIC_API_KEY")
	c, err := NewClient(mustDescriptor(t, "anthropic"), "", WithBaseURL(srv.URL))
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	err = c.StreamChat(context.Background(), "claude", []Message{{Role: "user", Content: "x"}}, nil, func(d string) error {
		sb.WriteString(d)
		return nil
	})
	if err != nil {
		t.Fatalf("StreamChat anthropic: %v", err)
	}
	if sb.String() != "Hello" {
		t.Errorf("anthropic stream deltas = %q", sb.String())
	}
}

// --- embeddings.go ---------------------------------------------------------

func TestEmbedValidation(t *testing.T) {
	d := withCopy(t, "ollama", func(d *Descriptor) { d.Capabilities.Embeddings = false })
	c, err := NewClient(d, "", WithBaseURL("http://localhost:11434/v1"))
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	if _, err := c.Embed(context.Background(), "m", []string{"x"}); err == nil ||
		!strings.Contains(err.Error(), "does not promise embeddings") {
		t.Fatalf("want embeddings-capability error, got %v", err)
	}

	d2 := withCopy(t, "ollama", func(d *Descriptor) { d.Models.Default = "" })
	c2, _ := NewClient(d2, "", WithBaseURL("http://localhost:11434/v1"))
	if _, err := c2.Embed(context.Background(), "m", nil); err == nil ||
		!strings.Contains(err.Error(), "must not be empty") {
		t.Fatalf("want empty-inputs error, got %v", err)
	}
	if _, err := c2.Embed(context.Background(), "", []string{"x"}); err == nil ||
		!strings.Contains(err.Error(), "model is required") {
		t.Fatalf("want model-required embed error, got %v", err)
	}
}

func TestEmbedFailures(t *testing.T) {
	t.Run("transport failure", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
		url := srv.URL
		srv.Close()
		c := ollamaClient(t, url)
		if _, err := c.Embed(context.Background(), "m", []string{"x"}); AsError(err) == nil {
			t.Fatalf("want transport error, got %v", err)
		}
	})
	t.Run("read failure", func(t *testing.T) {
		tr := &failingTransport{status: 200, body: `{"data":`, err: io.ErrUnexpectedEOF}
		c, _ := NewClient(mustDescriptor(t, "ollama"), "", WithHTTPClient(&http.Client{Transport: tr}))
		if _, err := c.Embed(context.Background(), "m", []string{"x"}); AsError(err) == nil || AsError(err).Code != ErrCodeTransport {
			t.Fatalf("want transport error, got %v", err)
		}
	})
	t.Run("decode failure", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			io.WriteString(w, `nope`)
		}))
		defer srv.Close()
		c := ollamaClient(t, srv.URL)
		if _, err := c.Embed(context.Background(), "m", []string{"x"}); AsError(err) == nil || !strings.Contains(err.Error(), "decode embeddings") {
			t.Fatalf("want decode error, got %v", err)
		}
	})
	t.Run("count mismatch", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			io.WriteString(w, `{"data":[{"embedding":[1]},{"embedding":[2]}]}`)
		}))
		defer srv.Close()
		c := ollamaClient(t, srv.URL)
		if _, err := c.Embed(context.Background(), "m", []string{"x"}); AsError(err) == nil || !strings.Contains(err.Error(), "expected 1 embeddings") {
			t.Fatalf("want count mismatch error, got %v", err)
		}
	})
	t.Run("model reported", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			io.WriteString(w, `{"data":[{"embedding":[1,2]}]}`)
		}))
		defer srv.Close()
		c := ollamaClient(t, srv.URL)
		embs, err := c.Embed(context.Background(), "llama3.1", []string{"x"})
		if err != nil {
			t.Fatalf("Embed: %v", err)
		}
		if len(embs) != 1 || embs[0].Model != "llama3.1" {
			t.Errorf("embeddings = %+v", embs)
		}
	})
}

func TestListModelsModes(t *testing.T) {
	// static with default: returns the single default model.
	envKey(t, "ANTHROPIC_API_KEY")
	ac, _ := NewClient(mustDescriptor(t, "anthropic"), "", WithBaseURL("http://localhost"))
	models, err := ac.ListModels(context.Background())
	if err != nil {
		t.Fatalf("ListModels static: %v", err)
	}
	if len(models) != 1 || models[0].ID != "claude-sonnet-5-20250915" {
		t.Errorf("static models = %+v", models)
	}

	// static without default: empty list, no error.
	envKey(t, "GROQ_API_KEY")
	gc, _ := NewClient(mustDescriptor(t, "groq"), "", WithBaseURL("http://localhost"))
	models, err = gc.ListModels(context.Background())
	if err != nil || len(models) != 0 {
		t.Errorf("static-empty models = %+v, err %v", models, err)
	}

	// discovered without discovery_path: validation error.
	d := withCopy(t, "openrouter", func(d *Descriptor) { d.Models.DiscoveryPath = "" })
	envKey(t, "OPENROUTER_API_KEY")
	dc, _ := NewClient(d, "", WithBaseURL("http://localhost"))
	if _, err := dc.ListModels(context.Background()); err == nil || !strings.Contains(err.Error(), "discovery_path") {
		t.Fatalf("want discovery-path error, got %v", err)
	}

	// unknown mode: client-side listing error.
	d2 := withCopy(t, "ollama", func(d *Descriptor) { d.Models.Mode = "fancy" })
	c2, _ := NewClient(d2, "", WithBaseURL("http://localhost"))
	if _, err := c2.ListModels(context.Background()); err == nil || !strings.Contains(err.Error(), `models.mode "fancy"`) {
		t.Fatalf("want unknown-mode error, got %v", err)
	}
}

func TestDiscoverModelsFailures(t *testing.T) {
	t.Run("unrecognized shape", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			io.WriteString(w, `{}`)
		}))
		defer srv.Close()
		c := ollamaClient(t, srv.URL)
		if _, err := c.ListModels(context.Background()); AsError(err) == nil || !strings.Contains(err.Error(), "unrecognized discovery") {
			t.Fatalf("want unrecognized-shape error, got %v", err)
		}
	})
	t.Run("transport failure", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
		url := srv.URL
		srv.Close()
		c := ollamaClient(t, url)
		if _, err := c.ListModels(context.Background()); AsError(err) == nil {
			t.Fatalf("want transport error, got %v", err)
		}
	})
	t.Run("read failure", func(t *testing.T) {
		tr := &failingTransport{status: 200, body: `{"data":`, err: io.ErrUnexpectedEOF}
		c, _ := NewClient(mustDescriptor(t, "ollama"), "", WithHTTPClient(&http.Client{Transport: tr}))
		if _, err := c.ListModels(context.Background()); AsError(err) == nil || AsError(err).Code != ErrCodeTransport {
			t.Fatalf("want transport error, got %v", err)
		}
	})
}

func TestNativeOllamaGuardsAndFailures(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/tags":
			io.WriteString(w, `{"models":[{"name":"llama3.1"}]}`)
		case "/api/generate":
			io.WriteString(w, "{not-json}\n")
		case "/api/chat":
			io.WriteString(w, "{also-not-json}\n")
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	envKey(t, "OPENAI_API_KEY")
	oc, _ := NewClient(mustDescriptor(t, "openai"), "", WithBaseURL(srv.URL))
	if err := oc.Generate(context.Background(), "m", "p", func(GenerateResponse) error { return nil }); err == nil ||
		!strings.Contains(err.Error(), "only available for the ollama") {
		t.Fatalf("Generate on openai must fail, got %v", err)
	}
	if err := oc.ChatStream(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, func(ChatStreamResponse) error { return nil }); err == nil ||
		!strings.Contains(err.Error(), "only available for the ollama") {
		t.Fatalf("ChatStream on openai must fail, got %v", err)
	}
	if err := oc.Ping(context.Background()); err == nil || !strings.Contains(err.Error(), "only available for the ollama") {
		t.Fatalf("Ping on openai must fail, got %v", err)
	}

	co := ollamaClient(t, srv.URL)
	if err := co.Ping(context.Background()); err != nil {
		t.Fatalf("Ping ollama: %v", err)
	}
	if err := co.Generate(context.Background(), "", "p", func(GenerateResponse) error { return nil }); err == nil ||
		!strings.Contains(err.Error(), "decode generate chunk") {
		t.Fatalf("Generate decode failure, got %v", err)
	}
	if err := co.ChatStream(context.Background(), "", []Message{{Role: "user", Content: "x"}}, func(ChatStreamResponse) error { return nil }); err == nil ||
		!strings.Contains(err.Error(), "decode chat chunk") {
		t.Fatalf("ChatStream decode failure, got %v", err)
	}
}

func TestStreamNDJSONFailures(t *testing.T) {
	t.Run("transport failure", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
		url := srv.URL
		srv.Close()
		c := ollamaClient(t, url)
		if err := c.Generate(context.Background(), "m", "p", func(GenerateResponse) error { return nil }); err == nil {
			t.Fatal("want transport error")
		}
	})
	t.Run("callback failure aborts stream", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			io.WriteString(w, "{\"done\":true}\n")
		}))
		defer srv.Close()
		c := ollamaClient(t, srv.URL)
		wantErr := errors.New("consumer stopped")
		err := c.Generate(context.Background(), "m", "p", func(GenerateResponse) error { return wantErr })
		if !errors.Is(err, wantErr) {
			t.Fatalf("callback error must propagate, got %v", err)
		}
	})
	t.Run("blank line skipped", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			io.WriteString(w, "\n{\"response\":\"x\",\"done\":true}\n")
		}))
		defer srv.Close()
		c := ollamaClient(t, srv.URL)
		var n int
		if err := c.Generate(context.Background(), "m", "p", func(ch GenerateResponse) error { n++; return nil }); err != nil {
			t.Fatalf("Generate: %v", err)
		}
		if n != 1 {
			t.Errorf("chunks = %d, want 1 (blank lines skipped)", n)
		}
	})
	t.Run("stream interrupted after data", func(t *testing.T) {
		tr := &failingTransport{status: 200, body: "{\"response\":\"x\"}\n", err: io.ErrUnexpectedEOF}
		c, _ := NewClient(mustDescriptor(t, "ollama"), "", WithHTTPClient(&http.Client{Transport: tr}))
		err := c.Generate(context.Background(), "m", "p", func(GenerateResponse) error { return nil })
		if e := AsError(err); e == nil || e.Code != ErrCodeTransport {
			t.Fatalf("want stream-interrupted transport error, got %v", err)
		}
	})
	t.Run("transport failure before data", func(t *testing.T) {
		tr := &failingTransport{status: 200, body: "", err: io.ErrUnexpectedEOF}
		c, _ := NewClient(mustDescriptor(t, "ollama"), "", WithHTTPClient(&http.Client{Transport: tr}))
		err := c.Generate(context.Background(), "m", "p", func(GenerateResponse) error { return nil })
		if e := AsError(err); e == nil || e.Code != ErrCodeTransport {
			t.Fatalf("want transport error, got %v", err)
		}
	})
}

// --- errors.go -------------------------------------------------------------

func TestErrorStringFormatting(t *testing.T) {
	if got := (&Error{Code: ErrCodeAuth}).Error(); got != "llmkit: auth_failure" {
		t.Errorf("bare error string = %q", got)
	}
	if got := (&Error{Code: ErrCodeAuth, StatusCode: 401}).Error(); got != "llmkit: auth_failure (status 401)" {
		t.Errorf("status error string = %q", got)
	}
	if got := (&Error{Code: ErrCodeAuth, StatusCode: 401, Body: "bad key"}).Error(); got != "llmkit: auth_failure (status 401): bad key" {
		t.Errorf("full error string = %q", got)
	}
	// Local failures must surface their underlying error, not a bare code.
	err := errors.New("expected 1 embeddings, got 2")
	if got := (&Error{Code: ErrCodeProvider, Err: err}).Error(); got != "llmkit: provider_error: expected 1 embeddings, got 2" {
		t.Errorf("local error string = %q", got)
	}
}

func TestErrorUnwrapAndAs(t *testing.T) {
	inner := errors.New("dial failed")
	e := &Error{Code: ErrCodeTransport, Err: inner}
	if !errors.Is(e, inner) {
		t.Error("errors.Is must see the wrapped transport error")
	}
	if AsError(fmt.Errorf("plain: %w", e)) != e {
		t.Error("AsError must find a wrapped *Error")
	}
	if AsError(errors.New("plain")) != nil {
		t.Error("AsError must return nil for non-classified errors")
	}
}

func TestErrorExitCodes(t *testing.T) {
	cases := []struct {
		code ErrorCode
		want exitcodes.ExitCode
	}{
		{ErrCodeAuth, exitcodes.ExitNoAuth},
		{ErrCodeRateLimited, exitcodes.ExitConflict},
		{ErrCodeContextOverflow, exitcodes.ExitData},
		{ErrCodeModelNotFound, exitcodes.ExitNotFound},
		{ErrCodeProvider, exitcodes.ExitGeneric},
	}
	for _, tc := range cases {
		if got := (&Error{Code: tc.code}).ExitCode(); got != tc.want {
			t.Errorf("ExitCode(%s) = %d, want %d", tc.code, got, tc.want)
		}
	}
	if (&Error{Code: ErrCodeTransport}).Retryable() == false {
		t.Error("transport errors must be retryable")
	}
}

func TestTruncateBody(t *testing.T) {
	short := "short body"
	if got := truncateBody(short); got != short {
		t.Errorf("short body changed: %q", got)
	}
	long := strings.Repeat("x", 600)
	got := truncateBody(long)
	if len(got) != maxBodyExcerpt {
		t.Errorf("truncated length = %d, want %d", len(got), maxBodyExcerpt)
	}
	if got := truncateBody("  padded  "); got != "padded" {
		t.Errorf("trimmed body = %q", got)
	}
}

func TestStreamFinishedReason(t *testing.T) {
	t.Run("openai finish_reason", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "text/event-stream")
			io.WriteString(w, "data: {\"choices\":[{\"delta\":{\"content\":\"x\"}}]}\n\n")
			io.WriteString(w, "data: {\"choices\":[{\"delta\":{},\"finish_reason\":\"max_tokens\"}]}\n\n")
			io.WriteString(w, "data: [DONE]\n\n")
		}))
		defer srv.Close()
		c := ollamaClient(t, srv.URL)
		var fin string
		err := c.StreamChat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil,
			func(string) error { return nil },
			WithStreamFinished(func(reason string) { fin = reason }))
		if err != nil {
			t.Fatalf("StreamChat: %v", err)
		}
		if fin != "max_tokens" {
			t.Errorf("finish reason = %q, want max_tokens", fin)
		}
	})
	t.Run("anthropic message_delta stop_reason", func(t *testing.T) {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "text/event-stream")
			io.WriteString(w, "data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"hi\"}}\n\n")
			io.WriteString(w, "data: {\"type\":\"message_delta\",\"delta\":{\"stop_reason\":\"max_tokens\"}}\n\n")
			io.WriteString(w, "data: [DONE]\n\n")
		}))
		defer srv.Close()
		envKey(t, "ANTHROPIC_API_KEY")
		c, err := NewClient(mustDescriptor(t, "anthropic"), "", WithBaseURL(srv.URL))
		if err != nil {
			t.Fatalf("NewClient: %v", err)
		}
		var fin string
		var sb strings.Builder
		err = c.StreamChat(context.Background(), "m", []Message{{Role: "user", Content: "x"}}, nil,
			func(d string) error { sb.WriteString(d); return nil },
			WithStreamFinished(func(reason string) { fin = reason }))
		if err != nil {
			t.Fatalf("StreamChat: %v", err)
		}
		if fin != "max_tokens" {
			t.Errorf("finish reason = %q, want max_tokens", fin)
		}
		if sb.String() != "hi" {
			t.Errorf("deltas = %q", sb.String())
		}
	})
}

// --- provider.go -----------------------------------------------------------

func TestDescriptorValidate(t *testing.T) {
	if err := (Descriptor{ID: "x", Dialect: "grpc", BaseURL: "http://x"}).Validate(); err == nil ||
		!strings.Contains(err.Error(), "unknown dialect") {
		t.Fatalf("want unknown-dialect error, got %v", err)
	}
	if err := (Descriptor{ID: "x", Dialect: DialectOpenAI}).Validate(); err == nil ||
		!strings.Contains(err.Error(), "no base URL") {
		t.Fatalf("want no-base-url error, got %v", err)
	}
	if err := (Descriptor{ID: "x", Dialect: DialectAnthropic, BaseURL: "http://x"}).Validate(); err != nil {
		t.Fatalf("valid descriptor rejected: %v", err)
	}
}

// --- structured-output options (issue #321 support) ------------------------

func TestChatSendsResponseFormat(t *testing.T) {
	var got openaiChatRequest
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&got)
		io.WriteString(w, `{"choices":[{"message":{"content":"{}"},"finish_reason":"stop"}]}`)
	}))
	defer srv.Close()

	c := ollamaClient(t, srv.URL)
	schema := json.RawMessage(`{"type":"json_schema","json_schema":{"name":"x","schema":{"type":"object"}}}`)
	if _, err := c.Chat(context.Background(), "m", []Message{{Role: "user", Content: "go"}},
		&ChatOptions{ResponseFormat: schema}); err != nil {
		t.Fatalf("Chat: %v", err)
	}
	if string(got.ResponseFormat) != string(schema) {
		t.Errorf("response_format = %s, want %s", got.ResponseFormat, schema)
	}
	// Omitted when unset.
	got = openaiChatRequest{} // decoder does not reset missing fields
	if _, err := c.Chat(context.Background(), "m", []Message{{Role: "user", Content: "go"}}, nil); err != nil {
		t.Fatalf("Chat: %v", err)
	}
	if got.ResponseFormat != nil {
		t.Error("response_format must be omitted when not configured")
	}
}

func TestGenerateOptionsOnWire(t *testing.T) {
	var got struct {
		Model  string         `json:"model"`
		Prompt string         `json:"prompt"`
		Stream bool           `json:"stream"`
		System string         `json:"system"`
		Format map[string]any `json:"format"`
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&got)
		io.WriteString(w, "{\"response\":\"ok\",\"done\":true}\n")
	}))
	defer srv.Close()

	c := ollamaClient(t, srv.URL)
	schema := map[string]any{"type": "object", "properties": map[string]any{"a": map[string]any{"type": "string"}}}
	err := c.Generate(context.Background(), "", "summarize", func(ch GenerateResponse) error {
		if ch.Response != "ok" {
			t.Errorf("chunk = %+v", ch)
		}
		return nil
	}, WithGenerateSystem("be strict"), WithGenerateFormat(schema))
	if err != nil {
		t.Fatalf("Generate: %v", err)
	}
	if got.System != "be strict" {
		t.Errorf("system = %q", got.System)
	}
	if got.Format["type"] != "object" {
		t.Errorf("format = %v", got.Format)
	}
}
