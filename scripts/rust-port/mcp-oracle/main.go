package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"

	"github.com/danieljustus/symaira-corekit/mcpserver"
)

type fixtureError struct{}

func (fixtureError) Error() string        { return "denied" }
func (fixtureError) ErrorCode() string    { return "denied" }
func (fixtureError) RetryableError() bool { return false }
func (fixtureError) ErrorHint() string    { return "check policy" }

type fixture struct {
	Message string `json:"message"`
}

type typedInput struct {
	Query string `json:"query"`
}

func main() {
	srv := mcpserver.New("fixture", "1.0.0")
	srv.RegisterTool(&mcpserver.Tool{
		Name: "echo", Description: "Echo input",
		InputSchema: json.RawMessage(`{"type":"object","properties":{"message":{"type":"string"}}}`),
		Handler: func(_ context.Context, input json.RawMessage) (any, error) {
			var args fixture
			if err := json.Unmarshal(input, &args); err != nil {
				return nil, err
			}
			return args.Message, nil
		},
	})
	mcpserver.RegisterTyped(srv, "typed", "Typed input", func(_ context.Context, input typedInput) (any, error) {
		return input.Query, nil
	})
	srv.RegisterTool(&mcpserver.Tool{
		Name: "number", Description: "Return structured JSON",
		Handler: func(_ context.Context, _ json.RawMessage) (any, error) {
			return map[string]any{"free": []int{39000, 39001}}, nil
		},
	})
	srv.RegisterTool(&mcpserver.Tool{
		Name: "rich", Description: "Return rich content",
		Handler: func(_ context.Context, _ json.RawMessage) (any, error) {
			return mcpserver.ToolResult{
				Content: []mcpserver.ContentBlock{
					{"type": "text", "text": "hello"},
					{"type": "image", "data": "aGVsbG8=", "mimeType": "image/png"},
				},
				StructuredContent: map[string]any{"count": 2},
			}, nil
		},
	})
	srv.RegisterTool(&mcpserver.Tool{
		Name: "fail", Description: "Return a structured error",
		Handler: func(_ context.Context, _ json.RawMessage) (any, error) {
			return nil, fixtureError{}
		},
	})
	srv.RegisterTool(&mcpserver.Tool{
		Name: "panic", Description: "Panic for recovery",
		Handler: func(_ context.Context, _ json.RawMessage) (any, error) {
			panic("fixture panic")
		},
	})
	srv.RegisterTool(&mcpserver.Tool{
		Name: "read", Description: "Read-only annotated tool",
		Annotations: &mcpserver.ToolAnnotations{Title: "Read", ReadOnlyHint: true, IdempotentHint: true},
	})
	srv.RegisterTool(&mcpserver.Tool{
		Name: "all-hints", Description: "All annotation hints",
		Annotations: &mcpserver.ToolAnnotations{Title: "All", ReadOnlyHint: true, IdempotentHint: true, OpenWorldHint: true, DestructiveHint: true},
	})
	srv.RegisterTool(&mcpserver.Tool{
		Name: "false-hints", Description: "Explicit false annotation hints",
		Annotations: &mcpserver.ToolAnnotations{},
	})
	srv.RegisterTool(&mcpserver.Tool{
		Name: "bool", Description: "Return boolean",
		Handler: func(_ context.Context, _ json.RawMessage) (any, error) { return true, nil },
	})
	srv.RegisterTool(&mcpserver.Tool{
		Name: "special", Description: "Return HTML-sensitive JSON",
		Handler: func(_ context.Context, _ json.RawMessage) (any, error) {
			return map[string]any{"text": "<>&\u2028\u2029"}, nil
		},
	})
	srv.RegisterTool(&mcpserver.Tool{
		Name: "special-structured", Description: "Return HTML-sensitive structured JSON",
		Handler: func(_ context.Context, _ json.RawMessage) (any, error) {
			return mcpserver.ToolResult{
				Content:           []mcpserver.ContentBlock{},
				StructuredContent: map[string]any{"text": "<>&\u2028\u2029"},
			}, nil
		},
	})
	srv.RegisterTool(&mcpserver.Tool{
		Name: "plain", Description: "Return a plain error",
		Handler: func(_ context.Context, _ json.RawMessage) (any, error) { return nil, errors.New("plain failure") },
	})
	srv.RegisterTool(&mcpserver.Tool{
		Name: "wrapped", Description: "Return a wrapped structured error",
		Handler: func(_ context.Context, _ json.RawMessage) (any, error) {
			return nil, fmt.Errorf("wrapped: %w", fixtureError{})
		},
	})
	if err := srv.ServeStdio(context.Background()); err != nil {
		_, _ = fmt.Fprintf(os.Stderr, "mcp fixture: %v\n", err)
		os.Exit(1)
	}
}
