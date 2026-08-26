package llmkit

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

// Embedding is one embedding vector with the model that produced it.
type Embedding struct {
	Vector []float32
	Model  string
}

// Embed returns embeddings for inputs via the OpenAI /embeddings wire format.
// Requires the provider's embeddings capability.
func (c *Client) Embed(ctx context.Context, model string, inputs []string) ([]Embedding, error) {
	if !c.desc.Capabilities.Embeddings {
		return nil, fmt.Errorf("llmkit: provider %q does not promise embeddings", c.desc.ID)
	}
	if len(inputs) == 0 {
		return nil, fmt.Errorf("llmkit: embed inputs must not be empty")
	}
	if model == "" {
		model = c.desc.DefaultModel()
	}
	if model == "" {
		return nil, fmt.Errorf("llmkit: model is required for provider %q", c.desc.ID)
	}

	req := struct {
		Model string   `json:"model"`
		Input []string `json:"input"`
	}{Model: model, Input: inputs}

	resp, err := c.do(ctx, http.MethodPost, "/embeddings", req, "application/json")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(io.LimitReader(resp.Body, 64<<20))
	if err != nil {
		return nil, errTransport(err)
	}
	var parsed struct {
		Data []struct {
			Embedding []float32 `json:"embedding"`
		} `json:"data"`
	}
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return nil, &Error{Code: ErrCodeProvider, Err: fmt.Errorf("decode embeddings response: %w", err)}
	}
	if len(parsed.Data) != len(inputs) {
		return nil, &Error{Code: ErrCodeProvider, Err: fmt.Errorf("expected %d embeddings, got %d", len(inputs), len(parsed.Data))}
	}
	out := make([]Embedding, len(parsed.Data))
	for i, d := range parsed.Data {
		out[i] = Embedding{Vector: d.Embedding, Model: model}
	}
	return out, nil
}

// ModelInfo describes one discovered or static model.
type ModelInfo struct {
	ID string `json:"id"`
}

// ListModels resolves the model list for this client's provider. Static lists
// come from the descriptor; discovered lists are fetched live (OpenRouter
// /models, Ollama /api/tags).
func (c *Client) ListModels(ctx context.Context) ([]ModelInfo, error) {
	switch c.desc.Models.Mode {
	case "static":
		info := c.desc.Models.Default
		if info == "" {
			return nil, nil
		}
		return []ModelInfo{{ID: info}}, nil
	case "discovered":
		path := c.desc.Models.DiscoveryPath
		if path == "" {
			return nil, fmt.Errorf("llmkit: provider %q declares discovery without discovery_path", c.desc.ID)
		}
		return c.discoverModels(ctx, path)
	default:
		return nil, fmt.Errorf("llmkit: provider %q models.mode %q has no client-side listing", c.desc.ID, c.desc.Models.Mode)
	}
}

// discoverModels fetches and normalizes both discovery shapes:
// OpenAI-style {"data":[{"id":...}]} and Ollama {"models":[{"name":...}]}.
func (c *Client) discoverModels(ctx context.Context, path string) ([]ModelInfo, error) {
	resp, err := c.do(ctx, http.MethodGet, path, nil, "")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	if err != nil {
		return nil, errTransport(err)
	}

	var openaiShape struct {
		Data []struct {
			ID string `json:"id"`
		} `json:"data"`
	}
	if err := json.Unmarshal(raw, &openaiShape); err == nil && len(openaiShape.Data) > 0 {
		out := make([]ModelInfo, 0, len(openaiShape.Data))
		for _, m := range openaiShape.Data {
			out = append(out, ModelInfo{ID: m.ID})
		}
		return out, nil
	}

	var ollamaShape struct {
		Models []struct {
			Name string `json:"name"`
		} `json:"models"`
	}
	if err := json.Unmarshal(raw, &ollamaShape); err == nil && len(ollamaShape.Models) > 0 {
		out := make([]ModelInfo, 0, len(ollamaShape.Models))
		for _, m := range ollamaShape.Models {
			out = append(out, ModelInfo{ID: m.Name})
		}
		return out, nil
	}
	return nil, &Error{Code: ErrCodeProvider, Err: fmt.Errorf("unrecognized discovery response shape at %s", path)}
}

// --- Native Ollama surface (absorbs ollamakit) --------------------------
//
// Ollama's native API offers capabilities the OpenAI-compat endpoint does not
// expose cleanly (generate with images, native chat streaming shape). These
// methods speak it directly against the same client.

// GenerateResponse is one chunk from a streaming native /api/generate call.
type GenerateResponse struct {
	Model    string `json:"model"`
	Response string `json:"response"`
	Done     bool   `json:"done"`
}

// GenerateOption configures a native /api/generate call.
type GenerateOption func(*generateConfig)

type generateConfig struct {
	system string
	format any // JSON-schema object for Ollama's `format` field
}

// WithGenerateSystem sets the system prompt on a native generate call.
func WithGenerateSystem(p string) GenerateOption {
	return func(c *generateConfig) { c.system = p }
}

// WithGenerateFormat constrains the generated output to a JSON-schema
// object (Ollama `format` field). Pass the schema itself, e.g. the
// consolidation schema consumers send for structured replies.
func WithGenerateFormat(schema map[string]any) GenerateOption {
	return func(c *generateConfig) { c.format = schema }
}

// Generate streams a native Ollama text generation. The callback receives one
// chunk per line of the NDJSON stream.
func (c *Client) Generate(ctx context.Context, model, prompt string, callback func(GenerateResponse) error, opts ...GenerateOption) error {
	if !c.isOllama() {
		return fmt.Errorf("llmkit: Generate is only available for the ollama provider")
	}
	if model == "" {
		model = c.desc.DefaultModel()
	}
	var cfg generateConfig
	for _, opt := range opts {
		opt(&cfg)
	}
	body := map[string]any{"model": model, "prompt": prompt, "stream": true}
	if cfg.system != "" {
		body["system"] = cfg.system
	}
	if cfg.format != nil {
		body["format"] = cfg.format
	}
	return c.streamNDJSON(ctx, "/api/generate", body, func(raw []byte) error {
		var chunk GenerateResponse
		if err := json.Unmarshal(raw, &chunk); err != nil {
			return &Error{Code: ErrCodeProvider, Err: fmt.Errorf("decode generate chunk: %w", err)}
		}
		return callback(chunk)
	})
}

// ChatStreamResponse is one chunk from a streaming native /api/chat call.
type ChatStreamResponse struct {
	Model   string  `json:"model"`
	Message Message `json:"message"`
	Done    bool    `json:"done"`
}

// ChatStream streams a native Ollama chat completion.
func (c *Client) ChatStream(ctx context.Context, model string, messages []Message, callback func(ChatStreamResponse) error) error {
	if !c.isOllama() {
		return fmt.Errorf("llmkit: ChatStream is only available for the ollama provider")
	}
	if model == "" {
		model = c.desc.DefaultModel()
	}
	body := map[string]any{"model": model, "messages": messages, "stream": true}
	return c.streamNDJSON(ctx, "/api/chat", body, func(raw []byte) error {
		var chunk ChatStreamResponse
		if err := json.Unmarshal(raw, &chunk); err != nil {
			return &Error{Code: ErrCodeProvider, Err: fmt.Errorf("decode chat chunk: %w", err)}
		}
		return callback(chunk)
	})
}

// Ping checks whether the local Ollama server answers.
func (c *Client) Ping(ctx context.Context) error {
	if !c.isOllama() {
		return fmt.Errorf("llmkit: Ping is only available for the ollama provider")
	}
	_, err := c.discoverModels(ctx, "/api/tags")
	return err
}

func (c *Client) isOllama() bool { return c.desc.ID == "ollama" }

// streamNDJSON consumes a newline-delimited JSON stream (Ollama native shape).
func (c *Client) streamNDJSON(ctx context.Context, path string, body any, handle func([]byte) error) error {
	resp, err := c.do(ctx, http.MethodPost, path, body, "application/json")
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	started := false
	scanner := newLineScanner(resp.Body)
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
			return &Error{Code: ErrCodeTransport, Err: fmt.Errorf("stream interrupted: %w", err)}
		}
		return errTransport(err)
	}
	return nil
}
