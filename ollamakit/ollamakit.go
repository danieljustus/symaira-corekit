// Package ollamakit provides a shared, CGO-free Ollama HTTP client for the
// Symaira tools. It covers the three call patterns that have independently
// grown across the sibling repositories: batch embeddings, streamed text
// generation, and streamed chat, plus model discovery and health checks.
//
// The client is intentionally thin over the Ollama REST API so it can be
// adopted by seek, memory, and desktop without forcing a new abstraction on
// any of them. The value it adds is consistency: base URL / model / timeout
// configuration, request timeouts, and a small set of typed errors that let
// callers degrade honestly (unreachable host, missing model, mid-stream
// failure).
//
// All network calls accept a context and respect the configured timeout. The
// streaming helpers read NDJSON responses line by line and invoke the caller's
// callback for every chunk; they stop early if the context is cancelled or the
// callback returns an error.
//
// This package has no cloud, LLM, or tool-specific dependencies and does not
// import any sibling Symaira tool. It uses only the Go standard library.
package ollamakit

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

// Common errors. Callers can degrade by checking these with errors.Is.
var (
	// ErrUnreachable means the Ollama host could not be reached at all
	// (network error, DNS failure, connection refused, timeout).
	ErrUnreachable = errors.New("ollamakit: ollama host unreachable")
	// ErrModelNotFound means Ollama responded with a 404 for the requested
	// model, or the model list did not contain the expected model.
	ErrModelNotFound = errors.New("ollamakit: model not found")
	// ErrStream means a streaming response was interrupted after at least
	// one chunk had already been delivered.
	ErrStream = errors.New("ollamakit: stream interrupted")
	// ErrResponse means Ollama returned an HTTP status other than 2xx that
	// is not covered by a more specific error.
	ErrResponse = errors.New("ollamakit: unexpected response")
)

// ResponseError wraps ErrResponse with the HTTP status code Ollama
// returned, so callers can classify a failure as transient (5xx — worth
// retrying) versus non-transient (a client error like a malformed request)
// without parsing the error string. Use errors.As to extract it.
type ResponseError struct {
	StatusCode int
	Body       string
}

func (e *ResponseError) Error() string {
	return fmt.Sprintf("%v: status %d: %s", ErrResponse, e.StatusCode, e.Body)
}

func (e *ResponseError) Unwrap() error { return ErrResponse }

// Config holds the client settings. A zero Config uses the package defaults.
type Config struct {
	// BaseURL is the Ollama server root. Defaults to DefaultBaseURL.
	BaseURL string
	// Model is the default model used when a call does not specify one.
	Model string
	// Timeout is the default HTTP request timeout. Defaults to DefaultTimeout.
	Timeout time.Duration
}

const (
	// DefaultBaseURL is the conventional Ollama local URL.
	DefaultBaseURL = "http://localhost:11434"
	// DefaultTimeout is the default HTTP request timeout.
	DefaultTimeout = 2 * time.Minute
)

// Client is an Ollama HTTP client. It is safe for concurrent use once
// constructed, but the underlying http.Client is already safe for concurrent
// use.
type Client struct {
	baseURL string
	model   string
	http    *http.Client
}

// New returns a Client from cfg. Missing fields are filled with defaults.
func New(cfg Config) *Client {
	baseURL := cfg.BaseURL
	if baseURL == "" {
		baseURL = DefaultBaseURL
	}
	// Trim trailing slash so path joining is predictable.
	baseURL = strings.TrimRight(baseURL, "/")

	timeout := cfg.Timeout
	if timeout <= 0 {
		timeout = DefaultTimeout
	}

	return &Client{
		baseURL: baseURL,
		model:   cfg.Model,
		http: &http.Client{
			Timeout: timeout,
			// Ollama is expected to answer directly; a redirect is either a
			// misconfigured host or a hostile one. Do not follow it, so a
			// consumer's configured local endpoint can never be silently
			// bounced to an unexpected host.
			CheckRedirect: func(req *http.Request, via []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
	}
}

// NewFromEnv returns a Client whose Config is read from environment variables
// prefixed with prefix. If prefix is empty it defaults to "OLLAMA". The
// recognized variables are <PREFIX>_BASE_URL, <PREFIX>_MODEL and
// <PREFIX>_TIMEOUT (a Go duration string). Unset variables fall back to the
// package defaults.
func NewFromEnv(prefix string) *Client {
	if prefix == "" {
		prefix = "OLLAMA"
	}
	cfg := Config{
		BaseURL: os.Getenv(prefix + "_BASE_URL"),
		Model:   os.Getenv(prefix + "_MODEL"),
	}
	if d := os.Getenv(prefix + "_TIMEOUT"); d != "" {
		if td, err := time.ParseDuration(d); err == nil {
			cfg.Timeout = td
		}
	}
	return New(cfg)
}

// BaseURL returns the resolved base URL used by the client.
func (c *Client) BaseURL() string { return c.baseURL }

// Model returns the configured default model.
func (c *Client) Model() string { return c.model }

func (c *Client) resolveModel(model string) string {
	if model != "" {
		return model
	}
	return c.model
}

func (c *Client) post(ctx context.Context, path string, body, dst any) error {
	u, err := url.JoinPath(c.baseURL, path)
	if err != nil {
		return fmt.Errorf("ollamakit: build url: %w", err)
	}

	var bodyReader io.Reader
	if body != nil {
		var buf strings.Builder
		enc := json.NewEncoder(&buf)
		if err := enc.Encode(body); err != nil {
			return fmt.Errorf("ollamakit: encode request: %w", err)
		}
		bodyReader = strings.NewReader(buf.String())
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u, bodyReader)
	if err != nil {
		return fmt.Errorf("ollamakit: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		if isNetworkError(err) {
			return fmt.Errorf("ollamakit: %w: %v", ErrUnreachable, err)
		}
		return fmt.Errorf("ollamakit: request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return ErrModelNotFound
	}
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<10))
		return &ResponseError{StatusCode: resp.StatusCode, Body: strings.TrimSpace(string(b))}
	}

	if dst != nil {
		if err := json.NewDecoder(resp.Body).Decode(dst); err != nil {
			return fmt.Errorf("ollamakit: decode response: %w", err)
		}
	}
	return nil
}

func (c *Client) get(ctx context.Context, path string, dst any) error {
	u, err := url.JoinPath(c.baseURL, path)
	if err != nil {
		return fmt.Errorf("ollamakit: build url: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return fmt.Errorf("ollamakit: build request: %w", err)
	}
	req.Header.Set("Accept", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		if isNetworkError(err) {
			return fmt.Errorf("ollamakit: %w: %v", ErrUnreachable, err)
		}
		return fmt.Errorf("ollamakit: request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<10))
		return &ResponseError{StatusCode: resp.StatusCode, Body: strings.TrimSpace(string(b))}
	}

	if dst != nil {
		if err := json.NewDecoder(resp.Body).Decode(dst); err != nil {
			return fmt.Errorf("ollamakit: decode response: %w", err)
		}
	}
	return nil
}

func isNetworkError(err error) bool {
	if err == nil {
		return false
	}
	// Common network error strings. We avoid importing net/url or net packages
	// for error type assertions because the concrete error types vary by OS and
	// Go version; the string check is portable and sufficient for degradation.
	s := err.Error()
	return strings.Contains(s, "no such host") ||
		strings.Contains(s, "connection refused") ||
		strings.Contains(s, "timeout") ||
		strings.Contains(s, "Temporary failure in name resolution") ||
		strings.Contains(s, "i/o timeout") ||
		strings.Contains(s, "context deadline exceeded")
}

// embedRequest is the Ollama /api/embed request body.
type embedRequest struct {
	Model string   `json:"model"`
	Input []string `json:"input"`
}

// embedResponse is the Ollama /api/embed response body.
type embedResponse struct {
	Embeddings [][]float32 `json:"embeddings"`
}

// Embed returns embeddings for the given input strings. If model is empty the
// client's configured default model is used.
func (c *Client) Embed(ctx context.Context, model string, inputs []string) ([][]float32, error) {
	if len(inputs) == 0 {
		return nil, errors.New("ollamakit: embed inputs must not be empty")
	}
	model = c.resolveModel(model)
	if model == "" {
		return nil, errors.New("ollamakit: model is required")
	}

	req := embedRequest{Model: model, Input: inputs}
	var resp embedResponse
	if err := c.post(ctx, "/api/embed", req, &resp); err != nil {
		return nil, err
	}
	if len(resp.Embeddings) != len(inputs) {
		return nil, fmt.Errorf("ollamakit: expected %d embeddings, got %d", len(inputs), len(resp.Embeddings))
	}
	return resp.Embeddings, nil
}

// GenerateOptions carries optional parameters for generation.
type GenerateOptions struct {
	// Temperature controls sampling randomness. Ollama ignores a zero value
	// by default, so we use a *float32 to distinguish unset from zero.
	Temperature *float32 `json:"temperature,omitempty"`
	// Format requests a structured response, e.g. "json" for Ollama's JSON
	// mode. Empty means the model's default (unstructured) text output.
	Format string `json:"format,omitempty"`
	// System sets a system prompt for this request, overriding any system
	// message baked into the model.
	System string `json:"system,omitempty"`
}

// GenerateResponse is one chunk from a streaming /api/generate response.
// When Done is true the stream is complete and Response contains the final
// accumulated text for this chunk.
type GenerateResponse struct {
	Model    string `json:"model"`
	Response string `json:"response"`
	Done     bool   `json:"done"`
}

// Generate streams a text generation request for prompt. It calls callback
// for every chunk; if callback returns an error the stream is cancelled and
// that error is returned. If the stream is interrupted after it has started,
// ErrStream is returned (wrapped with the underlying error if any).
func (c *Client) Generate(ctx context.Context, model, prompt string, opts *GenerateOptions, callback func(GenerateResponse) error) error {
	model = c.resolveModel(model)
	if model == "" {
		return errors.New("ollamakit: model is required")
	}
	if callback == nil {
		return errors.New("ollamakit: callback is required")
	}

	body := map[string]any{
		"model":  model,
		"prompt": prompt,
		"stream": true,
	}
	if opts != nil {
		if opts.Temperature != nil {
			body["temperature"] = *opts.Temperature
		}
		if opts.Format != "" {
			body["format"] = opts.Format
		}
		if opts.System != "" {
			body["system"] = opts.System
		}
	}

	return c.stream(ctx, "/api/generate", body, func(raw []byte) error {
		var chunk GenerateResponse
		if err := json.Unmarshal(raw, &chunk); err != nil {
			return fmt.Errorf("ollamakit: decode generate chunk: %w", err)
		}
		return callback(chunk)
	})
}

// Message is one turn in a chat request.
type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// ChatOptions carries optional parameters for chat.
type ChatOptions struct {
	Temperature *float32 `json:"temperature,omitempty"`
	// Format requests a structured response, e.g. "json" for Ollama's JSON
	// mode. Empty means the model's default (unstructured) text output.
	Format string `json:"format,omitempty"`
}

// ChatResponse is one chunk from a streaming /api/chat response.
type ChatResponse struct {
	Model   string  `json:"model"`
	Message Message `json:"message"`
	Done    bool    `json:"done"`
}

// Chat streams a chat completion request. It calls callback for every chunk;
// if callback returns an error the stream is cancelled and that error is
// returned. If the stream is interrupted after it has started, ErrStream is
// returned (wrapped with the underlying error if any).
func (c *Client) Chat(ctx context.Context, model string, messages []Message, opts *ChatOptions, callback func(ChatResponse) error) error {
	model = c.resolveModel(model)
	if model == "" {
		return errors.New("ollamakit: model is required")
	}
	if len(messages) == 0 {
		return errors.New("ollamakit: messages must not be empty")
	}
	if callback == nil {
		return errors.New("ollamakit: callback is required")
	}

	body := map[string]any{
		"model":    model,
		"messages": messages,
		"stream":   true,
	}
	if opts != nil {
		if opts.Temperature != nil {
			body["temperature"] = *opts.Temperature
		}
		if opts.Format != "" {
			body["format"] = opts.Format
		}
	}

	return c.stream(ctx, "/api/chat", body, func(raw []byte) error {
		var chunk ChatResponse
		if err := json.Unmarshal(raw, &chunk); err != nil {
			return fmt.Errorf("ollamakit: decode chat chunk: %w", err)
		}
		return callback(chunk)
	})
}

// stream performs a POST request that returns newline-delimited JSON.
func (c *Client) stream(ctx context.Context, path string, body any, handle func([]byte) error) error {
	u, err := url.JoinPath(c.baseURL, path)
	if err != nil {
		return fmt.Errorf("ollamakit: build url: %w", err)
	}

	var buf strings.Builder
	if err := json.NewEncoder(&buf).Encode(body); err != nil {
		return fmt.Errorf("ollamakit: encode request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u, strings.NewReader(buf.String()))
	if err != nil {
		return fmt.Errorf("ollamakit: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/x-ndjson")

	resp, err := c.http.Do(req)
	if err != nil {
		if isNetworkError(err) {
			return fmt.Errorf("ollamakit: %w: %v", ErrUnreachable, err)
		}
		return fmt.Errorf("ollamakit: request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return ErrModelNotFound
	}
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<10))
		return &ResponseError{StatusCode: resp.StatusCode, Body: strings.TrimSpace(string(b))}
	}

	started := false
	scanner := bufio.NewScanner(resp.Body)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		started = true
		if err := handle(line); err != nil {
			return err
		}
	}

	if err := scanner.Err(); err != nil {
		if started {
			return fmt.Errorf("ollamakit: %w: %v", ErrStream, err)
		}
		if isNetworkError(err) {
			return fmt.Errorf("ollamakit: %w: %v", ErrUnreachable, err)
		}
		return fmt.Errorf("ollamakit: read stream: %w", err)
	}
	return nil
}

// ModelInfo describes one model returned by /api/tags.
type ModelInfo struct {
	Name     string `json:"name"`
	Modified string `json:"modified_at"`
	Size     int64  `json:"size"`
}

// modelsResponse is the Ollama /api/tags response body.
type modelsResponse struct {
	Models []ModelInfo `json:"models"`
}

// ListModels returns the list of models available on the Ollama server.
func (c *Client) ListModels(ctx context.Context) ([]ModelInfo, error) {
	var resp modelsResponse
	if err := c.get(ctx, "/api/tags", &resp); err != nil {
		return nil, err
	}
	return resp.Models, nil
}

// Ping reports whether the Ollama server is reachable by hitting /api/tags.
// It returns nil on success and an error on failure. Use errors.Is to detect
// ErrUnreachable.
func (c *Client) Ping(ctx context.Context) error {
	_, err := c.ListModels(ctx)
	return err
}

// ParseBaseURL is a small helper that normalizes a base URL string, returning
// the cleaned form used by the client. It is useful when loading a config
// value that may contain a trailing slash or whitespace.
func ParseBaseURL(s string) string {
	if s == "" {
		return DefaultBaseURL
	}
	return strings.TrimRight(strings.TrimSpace(s), "/")
}

// ParseTimeout parses a timeout string. It accepts an integer interpreted as
// seconds or a Go duration string. The zero string returns the default.
func ParseTimeout(s string) (time.Duration, error) {
	if s == "" {
		return DefaultTimeout, nil
	}
	if i, err := strconv.Atoi(s); err == nil {
		return time.Duration(i) * time.Second, nil
	}
	return time.ParseDuration(s)
}
