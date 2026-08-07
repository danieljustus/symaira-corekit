package mcpserver

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"os"
	"strconv"
	"strings"
	"testing"
)

// TestToolsCallPointerToolResult covers the *ToolResult branch in
// handleToolsCall (a pointer-typed ToolResult return value).
func TestToolsCallPointerToolResult(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "ptr",
		Description: "Returns pointer ToolResult",
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			return &ToolResult{
				Content: []ContentBlock{
					{"type": "text", "text": "pointer result"},
				},
				Meta: map[string]any{"origin": "ptr"},
			}, nil
		},
	})

	req := frameRequest(t, "tools/call", map[string]any{
		"name":      "ptr",
		"arguments": map[string]any{},
	}, 21)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected JSON-RPC error: %v", resp.Error)
	}
	result := resp.Result.(map[string]any)
	if result["isError"] != false {
		t.Errorf("isError = %v, want false", result["isError"])
	}
	content := result["content"].([]any)
	item := content[0].(map[string]any)
	if item["text"] != "pointer result" {
		t.Errorf("content text = %#v, want %q", item["text"], "pointer result")
	}
	meta, ok := result["_meta"].(map[string]any)
	if !ok || meta["origin"] != "ptr" {
		t.Errorf("_meta = %#v, want map with origin=ptr", result["_meta"])
	}
}

// TestToolsCallToolResultNilContentAndMeta covers the Content==nil
// normalization and the omitted _meta when Meta is nil in sendToolResponse.
func TestToolsCallToolResultNilContentAndMeta(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "nilcontent",
		Description: "Returns ToolResult with nil content and nil meta",
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			return ToolResult{Content: nil, Meta: nil}, nil
		},
	})

	req := frameRequest(t, "tools/call", map[string]any{
		"name":      "nilcontent",
		"arguments": map[string]any{},
	}, 22)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected JSON-RPC error: %v", resp.Error)
	}
	result := resp.Result.(map[string]any)
	content, ok := result["content"].([]any)
	if !ok || len(content) != 0 {
		t.Errorf("content = %#v, want empty list", result["content"])
	}
	if _, hasMeta := result["_meta"]; hasMeta {
		t.Errorf("_meta should be omitted when nil, got %#v", result["_meta"])
	}
}

// TestWriteResponseMarshalFallback covers the writeResponse branch that
// emits fallbackError when the response payload cannot be marshalled.
func TestWriteResponseMarshalFallback(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "unmarshalable",
		Description: "Returns an unmarshalable ToolResult",
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			// A func value cannot be marshalled to JSON; this forces the
			// marshal-failure fallback inside writeResponse.
			return ToolResult{
				Content: []ContentBlock{
					{"type": "text", "text": func() {}}, //nolint:staticcheck
				},
			}, nil
		},
	})

	req := frameRequest(t, "tools/call", map[string]any{
		"name":      "unmarshalable",
		"arguments": map[string]any{},
	}, 23)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error == nil {
		t.Fatal("expected error response from marshal fallback")
	}
	errObj := resp.Error.(map[string]any)
	if errObj["code"] != float64(CodeInternalError) {
		t.Errorf("error code = %v, want %v", errObj["code"], CodeInternalError)
	}
}

// TestUnmarshalJSONErrorPaths covers the error branches of the custom
// jsonRPCRequest.UnmarshalJSON (malformed body in framed mode).
func TestUnmarshalJSONErrorPaths(t *testing.T) {
	srv := New("test", "1.0")

	// Body that is valid JSON but not a valid request object: the first
	// UnmarshalJSON step (requestAlias) fails on a JSON array.
	badBody := `[1,2,3]`
	frame := "Content-Length: " + strconv.Itoa(len(badBody)) + "\r\n\r\n" + badBody

	var buf bytes.Buffer
	err := srv.ServeIO(context.Background(), strings.NewReader(frame), &buf)
	if err != nil {
		t.Fatalf("ServeIO returned error: %v", err)
	}
	resp := readResponse(t, &buf)
	if resp.Error == nil {
		t.Fatal("expected parse error response for array body")
	}
	errObj := resp.Error.(map[string]any)
	if errObj["code"] != float64(CodeParseError) {
		t.Errorf("error code = %v, want %v", errObj["code"], CodeParseError)
	}
}

// TestSetInstructions covers SetInstructions and its effect on the
// initialize response.
func TestSetInstructions(t *testing.T) {
	srv := New("test", "1.0")
	srv.SetInstructions("Use the tools sparingly.")

	req := `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}` + "\n"
	buf := runServer(t, srv, req)
	resp := readLineResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected JSON-RPC error: %v", resp.Error)
	}
	result := resp.Result.(map[string]any)
	if got, ok := result["instructions"].(string); !ok || got != "Use the tools sparingly." {
		t.Errorf("instructions = %#v, want %q", result["instructions"], "Use the tools sparingly.")
	}
}

// TestServeStdio covers the ServeStdio entry point using pipe-replaced
// os.Stdin/os.Stdout.
func TestServeStdio(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "hello",
		Description: "Says hello",
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			return "hello", nil
		},
	})

	req := `{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"hello","arguments":{}}}` + "\n"

	origStdin, origStdout := os.Stdin, os.Stdout
	defer func() { os.Stdin, os.Stdout = origStdin, origStdout }()

	r, w, err := os.Pipe()
	if err != nil {
		t.Fatalf("create stdin pipe: %v", err)
	}
	defer r.Close()
	os.Stdin = r

	pr, pw, err := os.Pipe()
	if err != nil {
		t.Fatalf("create stdout pipe: %v", err)
	}
	defer pw.Close()
	os.Stdout = pw

	done := make(chan error, 1)
	go func() {
		done <- srv.ServeStdio(context.Background())
	}()

	if _, err := io.WriteString(w, req); err != nil {
		t.Fatalf("write request: %v", err)
	}
	_ = w.Close()

	if err := <-done; err != nil {
		t.Fatalf("ServeStdio returned error: %v", err)
	}
	_ = pw.Close()

	var outBuf bytes.Buffer
	buf := make([]byte, 4096)
	for {
		n, err := pr.Read(buf)
		outBuf.Write(buf[:n])
		if err != nil {
			break
		}
	}

	resp := readLineResponse(t, &outBuf)
	if resp.Error != nil {
		t.Fatalf("unexpected JSON-RPC error: %v", resp.Error)
	}
	result := resp.Result.(map[string]any)
	content := result["content"].([]any)
	item := content[0].(map[string]any)
	if item["text"] != "hello" {
		t.Errorf("content text = %#v, want %q", item["text"], "hello")
	}
}
