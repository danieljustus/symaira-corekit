// Package ollamakit provides a compatibility surface for the shared Ollama
// provider in llmkit.
//
// Deprecated: use llmkit directly for new code. This package remains as a thin
// shim so existing consumers can migrate without a flag-day API change. All
// HTTP requests are delegated to llmkit; no second Ollama transport is kept.
package ollamakit

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/danieljustus/symaira-corekit/llmkit"
)

// Common errors. Callers can degrade by checking these with errors.Is.
var (
	ErrUnreachable   = errors.New("ollamakit: ollama host unreachable")
	ErrModelNotFound = errors.New("ollamakit: model not found")
	ErrStream        = errors.New("ollamakit: stream interrupted")
	ErrResponse      = errors.New("ollamakit: unexpected response")
)

// ResponseError wraps an unexpected HTTP response from Ollama.
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
	BaseURL string
	Model   string
	Timeout time.Duration
}

const (
	DefaultBaseURL = "http://localhost:11434"
	DefaultTimeout = 2 * time.Minute
)

// These wire structs remain package-private compatibility names for tests and
// same-package consumers from the original implementation. Requests are now
// encoded by llmkit.
type embedRequest struct {
	Model      string   `json:"model"`
	Input      []string `json:"input"`
	Dimensions int      `json:"dimensions,omitempty"`
}

type embedResponse struct {
	Embeddings [][]float32 `json:"embeddings"`
}

type modelsResponse struct {
	Models []ModelInfo `json:"models"`
}

// Client is a compatibility wrapper around an llmkit Ollama client.
type Client struct {
	baseURL string
	model   string
	backend *llmkit.Client
	initErr error
}

// New returns a Client from cfg. Missing fields are filled with defaults.
func New(cfg Config) *Client {
	baseURL := ParseBaseURL(cfg.BaseURL)
	timeout := cfg.Timeout
	if timeout <= 0 {
		timeout = DefaultTimeout
	}

	c := &Client{baseURL: baseURL, model: cfg.Model}
	desc, ok := llmkit.Lookup("ollama")
	if !ok {
		c.initErr = errors.New("ollamakit: ollama provider descriptor unavailable")
		return c
	}
	backend, err := llmkit.NewClient(desc, "", llmkit.WithBaseURL(baseURL), llmkit.WithTimeout(timeout))
	if err != nil {
		c.initErr = err
		return c
	}
	c.backend = backend
	return c
}

// NewFromEnv reads <PREFIX>_BASE_URL, <PREFIX>_MODEL and <PREFIX>_TIMEOUT.
// An empty prefix defaults to OLLAMA.
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

func (c *Client) BaseURL() string { return c.baseURL }
func (c *Client) Model() string   { return c.model }

func (c *Client) checkReady() error {
	if c.initErr != nil {
		return c.initErr
	}
	return nil
}

func translateError(err error, streamStarted bool) error {
	if err == nil {
		return nil
	}
	e := llmkit.AsError(err)
	if e == nil {
		return err
	}
	switch e.Code {
	case llmkit.ErrCodeModelNotFound:
		return fmt.Errorf("%w: %v", ErrModelNotFound, err)
	case llmkit.ErrCodeTransport:
		if streamStarted {
			return fmt.Errorf("%w: %v", ErrStream, err)
		}
		return fmt.Errorf("%w: %v", ErrUnreachable, err)
	}
	if e.StatusCode != 0 {
		return &ResponseError{StatusCode: e.StatusCode, Body: e.Body}
	}
	return err
}

// Embed returns native Ollama embeddings.
func (c *Client) Embed(ctx context.Context, model string, inputs []string) ([][]float32, error) {
	if err := c.checkReady(); err != nil {
		return nil, err
	}
	result, err := c.backend.EmbedNative(ctx, c.resolveModel(model), inputs, 0)
	return result, translateError(err, false)
}

// EmbedWithDim returns native Ollama embeddings at the requested dimension.
func (c *Client) EmbedWithDim(ctx context.Context, model string, inputs []string, dim int) ([][]float32, error) {
	if err := c.checkReady(); err != nil {
		return nil, err
	}
	result, err := c.backend.EmbedNative(ctx, c.resolveModel(model), inputs, dim)
	return result, translateError(err, false)
}

// GenerateOptions carries optional native Ollama generation parameters.
type GenerateOptions struct {
	Temperature *float32 `json:"temperature,omitempty"`
	Format      string   `json:"format,omitempty"`
	System      string   `json:"system,omitempty"`
	Images      []string `json:"images,omitempty"`
}

type GenerateResponse = llmkit.GenerateResponse

// Generate streams a native Ollama text generation.
func (c *Client) Generate(ctx context.Context, model, prompt string, opts *GenerateOptions, callback func(GenerateResponse) error) error {
	if err := c.checkReady(); err != nil {
		return err
	}
	if callback == nil {
		return errors.New("ollamakit: callback is required")
	}
	var llmOpts []llmkit.GenerateOption
	if opts != nil {
		if opts.Temperature != nil {
			llmOpts = append(llmOpts, llmkit.WithGenerateTemperature(*opts.Temperature))
		}
		if opts.Format != "" {
			llmOpts = append(llmOpts, llmkit.WithGenerateFormatValue(opts.Format))
		}
		if opts.System != "" {
			llmOpts = append(llmOpts, llmkit.WithGenerateSystem(opts.System))
		}
		if len(opts.Images) > 0 {
			llmOpts = append(llmOpts, llmkit.WithGenerateImages(opts.Images))
		}
	}
	started := false
	err := c.backend.Generate(ctx, c.resolveModel(model), prompt, func(resp llmkit.GenerateResponse) error {
		started = true
		return callback(resp)
	}, llmOpts...)
	return translateError(err, started)
}

type Message = llmkit.Message

type ChatOptions struct {
	Temperature *float32 `json:"temperature,omitempty"`
	Format      string   `json:"format,omitempty"`
}

type ChatResponse = llmkit.ChatStreamResponse

// Chat streams a native Ollama chat completion.
func (c *Client) Chat(ctx context.Context, model string, messages []Message, opts *ChatOptions, callback func(ChatResponse) error) error {
	if err := c.checkReady(); err != nil {
		return err
	}
	if callback == nil {
		return errors.New("ollamakit: callback is required")
	}
	var llmOpts []llmkit.NativeChatOption
	if opts != nil {
		if opts.Temperature != nil {
			llmOpts = append(llmOpts, llmkit.WithNativeChatTemperature(*opts.Temperature))
		}
		if opts.Format != "" {
			llmOpts = append(llmOpts, llmkit.WithNativeChatFormat(opts.Format))
		}
	}
	started := false
	err := c.backend.ChatStreamWithOptions(ctx, c.resolveModel(model), messages, func(resp llmkit.ChatStreamResponse) error {
		started = true
		return callback(resp)
	}, llmOpts...)
	return translateError(err, started)
}

type ModelInfo struct {
	Name     string `json:"name"`
	Modified string `json:"modified_at"`
	Size     int64  `json:"size"`
}

// ListModels returns the models available on the Ollama server.
func (c *Client) ListModels(ctx context.Context) ([]ModelInfo, error) {
	if err := c.checkReady(); err != nil {
		return nil, err
	}
	models, err := c.backend.ListOllamaModels(ctx)
	if err != nil {
		return nil, translateError(err, false)
	}
	out := make([]ModelInfo, 0, len(models))
	for _, model := range models {
		out = append(out, ModelInfo{Name: model.Name, Modified: model.Modified, Size: model.Size})
	}
	return out, nil
}

func (c *Client) Ping(ctx context.Context) error {
	if err := c.checkReady(); err != nil {
		return err
	}
	return translateError(c.backend.Ping(ctx), false)
}

func (c *Client) resolveModel(model string) string {
	if model != "" {
		return model
	}
	return c.model
}

func ParseBaseURL(s string) string {
	if s == "" {
		return DefaultBaseURL
	}
	return strings.TrimRight(strings.TrimSpace(s), "/")
}

func ParseTimeout(s string) (time.Duration, error) {
	if s == "" {
		return DefaultTimeout, nil
	}
	if i, err := strconv.Atoi(s); err == nil {
		return time.Duration(i) * time.Second, nil
	}
	return time.ParseDuration(s)
}
