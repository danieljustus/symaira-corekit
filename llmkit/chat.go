package llmkit

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// Message is one turn in a chat conversation.
type Message struct {
	Role    string `json:"role"` // "system", "user", "assistant", "tool"
	Content string `json:"content"`
}

// Tool is a function the model may call, in OpenAI tool-use shape. Anthropic
// tools are converted at request time.
type Tool struct {
	Name        string          `json:"name"`
	Description string          `json:"description,omitempty"`
	InputSchema json.RawMessage `json:"parameters,omitempty"`
}

// ToolCall is one tool invocation requested by the model.
type ToolCall struct {
	ID        string          `json:"id"`
	Name      string          `json:"name"`
	Arguments json.RawMessage `json:"arguments"` // JSON object
}

// Choice is the assistant's response to a chat request.
type Choice struct {
	Content      string     `json:"content"`
	ToolCalls    []ToolCall `json:"tool_calls,omitempty"`
	FinishReason string     `json:"finish_reason,omitempty"`
}

// ChatOptions carries optional per-request parameters.
type ChatOptions struct {
	Temperature *float64
	MaxTokens   int
	System      string // convenience system prompt; merged into messages
	Tools       []Tool // requires the provider's tool_use capability
}

// Chat performs a non-streaming chat completion and returns the first choice.
func (c *Client) Chat(ctx context.Context, model string, messages []Message, opts *ChatOptions) (*Choice, error) {
	if model == "" {
		model = c.desc.DefaultModel()
	}
	if model == "" {
		return nil, fmt.Errorf("llmkit: model is required for provider %q", c.desc.ID)
	}
	if len(messages) == 0 {
		return nil, fmt.Errorf("llmkit: messages must not be empty")
	}

	switch c.dialect {
	case DialectOpenAI:
		return c.chatOpenAI(ctx, model, messages, opts)
	case DialectAnthropic:
		return c.chatAnthropic(ctx, model, messages, opts)
	default:
		return nil, fmt.Errorf("llmkit: unsupported dialect %q", c.dialect)
	}
}

// --- OpenAI dialect -----------------------------------------------------

type openaiChatRequest struct {
	Model       string       `json:"model"`
	Messages    []openaiMsg  `json:"messages"`
	Temperature *float64     `json:"temperature,omitempty"`
	MaxTokens   int          `json:"max_tokens,omitempty"`
	Stream      bool         `json:"stream"`
	Tools       []openaiTool `json:"tools,omitempty"`
}

type openaiMsg struct {
	Role       string           `json:"role"`
	Content    string           `json:"content"`
	ToolCalls  []openaiToolCall `json:"tool_calls,omitempty"`
	ToolCallID string           `json:"tool_call_id,omitempty"`
}

type openaiTool struct {
	Type     string       `json:"type"`
	Function openaiFnSpec `json:"function"`
}

type openaiFnSpec struct {
	Name        string          `json:"name"`
	Description string          `json:"description,omitempty"`
	Parameters  json.RawMessage `json:"parameters,omitempty"`
}

type openaiToolCall struct {
	ID       string `json:"id"`
	Type     string `json:"type"`
	Function struct {
		Name      string `json:"name"`
		Arguments string `json:"arguments"`
	} `json:"function"`
}

type openaiChatResponse struct {
	Choices []struct {
		Message struct {
			Content   string           `json:"content"`
			ToolCalls []openaiToolCall `json:"tool_calls,omitempty"`
		} `json:"message"`
		FinishReason string `json:"finish_reason"`
	} `json:"choices"`
	Error *struct {
		Message string `json:"message"`
		Type    string `json:"type"`
		Code    any    `json:"code"`
	} `json:"error"`
}

func toOpenAIMessages(messages []Message, opts *ChatOptions) []openaiMsg {
	var out []openaiMsg
	if opts != nil && opts.System != "" {
		out = append(out, openaiMsg{Role: "system", Content: opts.System})
	}
	for _, m := range messages {
		out = append(out, openaiMsg{Role: m.Role, Content: m.Content})
	}
	return out
}

func toOpenAITools(tools []Tool) []openaiTool {
	out := make([]openaiTool, 0, len(tools))
	for _, t := range tools {
		out = append(out, openaiTool{
			Type: "function",
			Function: openaiFnSpec{
				Name:        t.Name,
				Description: t.Description,
				Parameters:  t.InputSchema,
			},
		})
	}
	return out
}

func fromOpenAIToolCalls(raw []openaiToolCall) []ToolCall {
	out := make([]ToolCall, 0, len(raw))
	for _, tc := range raw {
		out = append(out, ToolCall{
			ID:        tc.ID,
			Name:      tc.Function.Name,
			Arguments: json.RawMessage(tc.Function.Arguments),
		})
	}
	return out
}

func openAIErrorFromBody(body []byte) *Error {
	var parsed openaiChatResponse
	if err := json.Unmarshal(body, &parsed); err == nil && parsed.Error != nil {
		e := classify(http.StatusBadRequest, parsed.Error.Message)
		// Re-classify with the real status: classify saw only the excerpt.
		e = classifyFromTyped(http.StatusBadRequest, parsed.Error.Type, parsed.Error.Message)
		return e
	}
	return nil
}

func (c *Client) chatOpenAI(ctx context.Context, model string, messages []Message, opts *ChatOptions) (*Choice, error) {
	req := openaiChatRequest{
		Model:    model,
		Messages: toOpenAIMessages(messages, opts),
	}
	if opts != nil {
		req.Temperature = opts.Temperature
		req.MaxTokens = opts.MaxTokens
		if len(opts.Tools) > 0 {
			if !c.desc.Capabilities.ToolUse {
				return nil, fmt.Errorf("llmkit: provider %q does not promise tool_use", c.desc.ID)
			}
			req.Tools = toOpenAITools(opts.Tools)
		}
	}

	resp, err := c.do(ctx, http.MethodPost, "/chat/completions", req, "application/json")
	if err != nil {
		// Enrich 4xx bodies that carry a structured OpenAI error object.
		if e, ok := err.(*Error); ok && e.Body != "" {
			if typed := openAIErrorFromBody([]byte(e.Body)); typed != nil && typed.Code != ErrCodeProvider {
				return nil, typed
			}
		}
		return nil, err
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	if err != nil {
		return nil, errTransport(err)
	}
	var parsed openaiChatResponse
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return nil, &Error{Code: ErrCodeProvider, Err: fmt.Errorf("decode chat response: %w", err)}
	}
	if len(parsed.Choices) == 0 {
		return nil, &Error{Code: ErrCodeProvider, Err: fmt.Errorf("chat response contained no choices")}
	}
	ch := parsed.Choices[0]
	return &Choice{
		Content:      ch.Message.Content,
		ToolCalls:    fromOpenAIToolCalls(ch.Message.ToolCalls),
		FinishReason: ch.FinishReason,
	}, nil
}

// StreamChat performs a streaming chat completion, invoking callback for each
// content delta. Requires the provider's streaming capability.
func (c *Client) StreamChat(ctx context.Context, model string, messages []Message, opts *ChatOptions, callback func(delta string) error) error {
	if !c.desc.Capabilities.Streaming {
		return fmt.Errorf("llmkit: provider %q does not promise streaming", c.desc.ID)
	}
	if model == "" {
		model = c.desc.DefaultModel()
	}
	if model == "" {
		return fmt.Errorf("llmkit: model is required for provider %q", c.desc.ID)
	}
	switch c.dialect {
	case DialectOpenAI:
		return c.streamOpenAI(ctx, model, messages, opts, callback)
	case DialectAnthropic:
		return c.streamAnthropicDialect(ctx, model, messages, opts, callback)
	default:
		return fmt.Errorf("llmkit: unsupported dialect %q", c.dialect)
	}
}

type openaiStreamChunk struct {
	Choices []struct {
		Delta struct {
			Content   string           `json:"content"`
			ToolCalls []openaiToolCall `json:"tool_calls,omitempty"`
		} `json:"delta"`
		FinishReason string `json:"finish_reason"`
	} `json:"choices"`
}

func (c *Client) streamSSE(ctx context.Context, path string, body any, handle func(data []byte) error) error {
	resp, err := c.do(ctx, http.MethodPost, path, body, "application/json")
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	started := false
	scanner := bufio.NewScanner(resp.Body)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		data := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
		if data == "" || data == "[DONE]" {
			continue
		}
		started = true
		if err := handle([]byte(data)); err != nil {
			return err
		}
	}
	if err := scanner.Err(); err != nil {
		if started {
			return &Error{Code: ErrCodeTransport, Err: fmt.Errorf("stream interrupted: %w", err)}
		}
		return errTransport(err)
	}
	if !started {
		return &Error{Code: ErrCodeProvider, Err: fmt.Errorf("no stream data received")}
	}
	return nil
}

func (c *Client) streamOpenAI(ctx context.Context, model string, messages []Message, opts *ChatOptions, callback func(string) error) error {
	body := openaiChatRequest{
		Model:    model,
		Messages: toOpenAIMessages(messages, opts),
		Stream:   true,
	}
	if opts != nil {
		body.Temperature = opts.Temperature
		body.MaxTokens = opts.MaxTokens
	}
	return c.streamSSE(ctx, "/chat/completions", body, func(data []byte) error {
		var chunk openaiStreamChunk
		if err := json.Unmarshal(data, &chunk); err != nil {
			return &Error{Code: ErrCodeProvider, Err: fmt.Errorf("decode stream chunk: %w", err)}
		}
		if len(chunk.Choices) == 0 {
			return nil
		}
		delta := chunk.Choices[0].Delta.Content
		if delta == "" {
			return nil
		}
		return callback(delta)
	})
}

// --- Anthropic dialect --------------------------------------------------

type anthropicRequest struct {
	Model     string          `json:"model"`
	MaxTokens int             `json:"max_tokens"`
	Messages  []anthropicMsg  `json:"messages"`
	System    string          `json:"system,omitempty"`
	Tools     []anthropicTool `json:"tools,omitempty"`
	Stream    bool            `json:"stream,omitempty"`
}

type anthropicMsg struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type anthropicTool struct {
	Name        string          `json:"name"`
	Description string          `json:"description,omitempty"`
	InputSchema json.RawMessage `json:"input_schema,omitempty"`
}

type anthropicResponse struct {
	Content []struct {
		Type string `json:"type,omitempty"`
		Text string `json:"text"`
	} `json:"content"`
	StopReason string `json:"stop_reason"`
	Error      *struct {
		Type    string `json:"type"`
		Message string `json:"message"`
	} `json:"error"`
}

const anthropicDefaultMaxTokens = 8192

// classifyFromTyped refines classification using the structured error type
// some providers report alongside the status.
func classifyFromTyped(status int, errType, message string) *Error {
	e := classify(status, message)
	lower := strings.ToLower(errType + " " + message)
	switch {
	case containsAny(lower, "authentication", "invalid api key", "permission"):
		e.Code = ErrCodeAuth
	case containsAny(lower, "rate limit", "overloaded"):
		e.Code = ErrCodeRateLimited
	case containsAny(lower, "not_found", "no such model"):
		e.Code = ErrCodeModelNotFound
	}
	return e
}

func containsAny(s string, markers ...string) bool {
	for _, m := range markers {
		if strings.Contains(s, m) {
			return true
		}
	}
	return false
}

func (c *Client) buildAnthropicRequest(model string, messages []Message, opts *ChatOptions, stream bool) anthropicRequest {
	maxTokens := anthropicDefaultMaxTokens
	system := ""
	var tools []Tool
	if opts != nil {
		if opts.MaxTokens > 0 {
			maxTokens = opts.MaxTokens
		}
		system = opts.System
		tools = opts.Tools
	}
	req := anthropicRequest{
		Model:     model,
		MaxTokens: maxTokens,
		Stream:    stream,
		System:    system,
	}
	for _, m := range messages {
		if m.Role == "system" {
			// Anthropic takes the system prompt as a top-level field.
			if req.System == "" {
				req.System = m.Content
			} else {
				req.System += "\n\n" + m.Content
			}
			continue
		}
		req.Messages = append(req.Messages, anthropicMsg{Role: m.Role, Content: m.Content})
	}
	for _, t := range tools {
		req.Tools = append(req.Tools, anthropicTool{
			Name:        t.Name,
			Description: t.Description,
			InputSchema: t.InputSchema,
		})
	}
	return req
}

func (c *Client) chatAnthropic(ctx context.Context, model string, messages []Message, opts *ChatOptions) (*Choice, error) {
	resp, err := c.do(ctx, http.MethodPost, "/messages", c.buildAnthropicRequest(model, messages, opts, false), "application/json")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	if err != nil {
		return nil, errTransport(err)
	}
	var parsed anthropicResponse
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return nil, &Error{Code: ErrCodeProvider, Err: fmt.Errorf("decode anthropic response: %w", err)}
	}
	content := ""
	for _, part := range parsed.Content {
		if part.Text != "" {
			content += part.Text
		}
	}
	return &Choice{Content: content, FinishReason: parsed.StopReason}, nil
}

type anthropicStreamEvent struct {
	Type  string `json:"type"`
	Delta struct {
		Type string `json:"type"`
		Text string `json:"text"`
	} `json:"delta"`
	Error *struct {
		Message string `json:"message"`
	} `json:"error"`
}

func (c *Client) streamAnthropicDialect(ctx context.Context, model string, messages []Message, opts *ChatOptions, callback func(string) error) error {
	return c.streamSSE(ctx, "/messages", c.buildAnthropicRequest(model, messages, opts, true), func(data []byte) error {
		var ev anthropicStreamEvent
		if err := json.Unmarshal(data, &ev); err != nil {
			return nil // skip unknown event shapes rather than killing streams
		}
		if ev.Type == "content_block_delta" && ev.Delta.Text != "" {
			return callback(ev.Delta.Text)
		}
		return nil
	})
}
