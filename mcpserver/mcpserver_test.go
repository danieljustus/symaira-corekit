package mcpserver

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"testing"
)

func frameRequest(t *testing.T, method string, params any, id any) []byte {
	t.Helper()
	var rawParams json.RawMessage
	if params != nil {
		var err error
		rawParams, err = json.Marshal(params)
		if err != nil {
			t.Fatalf("marshal params: %v", err)
		}
	}
	req := jsonRPCRequest{
		JSONRPC: "2.0",
		Method:  method,
		Params:  rawParams,
	}
	if id != nil {
		req.ID = id
	}
	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("marshal request: %v", err)
	}
	return []byte(fmt.Sprintf("Content-Length: %d\r\n\r\n%s", len(data), data))
}

func readResponse(t *testing.T, buf *bytes.Buffer) jsonRPCResponse {
	t.Helper()
	var resp jsonRPCResponse
	if err := readFramedResponse(buf.Bytes(), &resp); err != nil {
		t.Fatalf("read response: %v\nraw: %s", err, buf.String())
	}
	return resp
}

func readLineResponse(t *testing.T, buf *bytes.Buffer) jsonRPCResponse {
	t.Helper()
	var resp jsonRPCResponse
	if err := json.Unmarshal(bytes.TrimSpace(buf.Bytes()), &resp); err != nil {
		t.Fatalf("read line response: %v\nraw: %s", err, buf.String())
	}
	return resp
}

func readFramedResponse(data []byte, resp *jsonRPCResponse) error {
	s := string(data)
	if !strings.HasPrefix(s, "Content-Length:") {
		return fmt.Errorf("response does not start with Content-Length")
	}
	idx := strings.Index(s, "\r\n\r\n")
	if idx < 0 {
		return fmt.Errorf("no header separator found")
	}
	header := s[:idx]
	body := s[idx+4:]
	_ = header
	return json.Unmarshal([]byte(body), resp)
}

func runServer(t *testing.T, srv *Server, requests string) *bytes.Buffer {
	t.Helper()
	var buf bytes.Buffer
	r := strings.NewReader(requests)
	err := srv.ServeIO(context.Background(), r, &buf)
	if err != nil {
		t.Fatalf("ServeIO: %v", err)
	}
	return &buf
}

func TestNew(t *testing.T) {
	srv := New("test-server", "1.0.0")
	if srv.name != "test-server" {
		t.Errorf("name = %q, want %q", srv.name, "test-server")
	}
	if srv.version != "1.0.0" {
		t.Errorf("version = %q, want %q", srv.version, "1.0.0")
	}
}

func TestRegisterTool(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "echo",
		Description: "Echoes input",
	})

	if len(srv.tools) != 1 {
		t.Fatalf("tools count = %d, want 1", len(srv.tools))
	}
	if _, ok := srv.tools["echo"]; !ok {
		t.Error("expected 'echo' tool to be registered")
	}
}

func TestRegisterToolPanicsOnNil(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Error("expected panic on nil Tool")
		}
	}()
	srv := New("test", "1.0")
	srv.RegisterTool(nil)
}

func TestRegisterToolPanicsOnEmptyName(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Error("expected panic on empty Name")
		}
	}()
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{Name: ""})
}

func TestRegisterToolPanicsOnDuplicate(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Error("expected panic on duplicate tool")
		}
	}()
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{Name: "echo"})
	srv.RegisterTool(&Tool{Name: "echo"})
}

func TestInitialize(t *testing.T) {
	srv := New("myserver", "2.0.0")
	req := frameRequest(t, "initialize", nil, 1)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected error: %v", resp.Error)
	}

	result, ok := resp.Result.(map[string]any)
	if !ok {
		t.Fatalf("result is not a map: %T", resp.Result)
	}
	if result["protocolVersion"] != ProtocolVersion {
		t.Errorf("protocolVersion = %v, want %v", result["protocolVersion"], ProtocolVersion)
	}
	serverInfo := result["serverInfo"].(map[string]any)
	if serverInfo["name"] != "myserver" {
		t.Errorf("serverInfo.name = %v, want myserver", serverInfo["name"])
	}
	if serverInfo["version"] != "2.0.0" {
		t.Errorf("serverInfo.version = %v, want 2.0.0", serverInfo["version"])
	}
	caps := result["capabilities"].(map[string]any)
	if caps["tools"] == nil {
		t.Error("expected tools capability")
	}
}

func TestInitializeFromJSONLine(t *testing.T) {
	srv := New("myserver", "2.0.0")
	req := `{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}` + "\n"
	buf := runServer(t, srv, req)

	resp := readLineResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected error: %v", resp.Error)
	}

	result, ok := resp.Result.(map[string]any)
	if !ok {
		t.Fatalf("result is not a map: %T", resp.Result)
	}
	if result["protocolVersion"] != ProtocolVersion {
		t.Errorf("protocolVersion = %v, want %v", result["protocolVersion"], ProtocolVersion)
	}
}

func TestInitializeFromFrameWithLeadingHeader(t *testing.T) {
	srv := New("myserver", "2.0.0")
	body := `{"jsonrpc":"2.0","id":1,"method":"initialize"}`
	req := fmt.Sprintf("Content-Type: application/vscode-jsonrpc; charset=utf-8\r\nContent-Length: %d\r\n\r\n%s", len(body), body)
	buf := runServer(t, srv, req)

	resp := readResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected error: %v", resp.Error)
	}

	result, ok := resp.Result.(map[string]any)
	if !ok {
		t.Fatalf("result is not a map: %T", resp.Result)
	}
	if result["protocolVersion"] != ProtocolVersion {
		t.Errorf("protocolVersion = %v, want %v", result["protocolVersion"], ProtocolVersion)
	}
}

func TestNotificationsInitializedNoop(t *testing.T) {
	srv := New("test", "1.0")
	req := frameRequest(t, "notifications/initialized", nil, nil)
	var buf bytes.Buffer
	err := srv.ServeIO(context.Background(), strings.NewReader(string(req)), &buf)
	if err != nil {
		t.Fatalf("ServeIO: %v", err)
	}
	if buf.Len() != 0 {
		t.Errorf("expected no response for notification, got: %s", buf.String())
	}
}

func TestToolsList(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "search",
		Description: "Search documents",
		InputSchema: json.RawMessage(`{"type":"object","properties":{"query":{"type":"string"}}}`),
	})
	srv.RegisterTool(&Tool{
		Name:        "index",
		Description: "Index a document",
	})

	req := frameRequest(t, "tools/list", nil, 2)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected error: %v", resp.Error)
	}

	result := resp.Result.(map[string]any)
	tools := result["tools"].([]any)
	if len(tools) != 2 {
		t.Fatalf("tools count = %d, want 2", len(tools))
	}

	first := tools[0].(map[string]any)
	if first["name"] != "search" {
		t.Errorf("first tool name = %v, want search", first["name"])
	}
	if first["description"] != "Search documents" {
		t.Errorf("first tool description = %v", first["description"])
	}
	if first["inputSchema"] == nil {
		t.Error("expected inputSchema on first tool")
	}

	second := tools[1].(map[string]any)
	if second["name"] != "index" {
		t.Errorf("second tool name = %v, want index", second["name"])
	}
	if second["inputSchema"] != nil {
		t.Error("expected no inputSchema on second tool")
	}
}

func TestToolsCallDispatch(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "echo",
		Description: "Echoes input",
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			var args struct {
				Message string `json:"message"`
			}
			if err := json.Unmarshal(input, &args); err != nil {
				return nil, err
			}
			return args.Message, nil
		},
	})

	req := frameRequest(t, "tools/call", map[string]any{
		"name":      "echo",
		"arguments": map[string]string{"message": "hello"},
	}, 3)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected error: %v", resp.Error)
	}

	result := resp.Result.(map[string]any)
	content := result["content"].([]any)
	item := content[0].(map[string]any)
	if item["text"] != "hello" {
		t.Errorf("tool result text = %v, want hello", item["text"])
	}
	if result["isError"] != false {
		t.Error("expected isError=false")
	}
}

func TestToolsCallUnknownTool(t *testing.T) {
	srv := New("test", "1.0")
	req := frameRequest(t, "tools/call", map[string]any{
		"name":      "nonexistent",
		"arguments": map[string]any{},
	}, 4)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error == nil {
		t.Fatal("expected error response")
	}
	errObj := resp.Error.(map[string]any)
	if errObj["code"] != float64(CodeMethodNotFound) {
		t.Errorf("error code = %v, want %v", errObj["code"], CodeMethodNotFound)
	}
}

func TestToolsCallHandlerError(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "fail",
		Description: "Always fails",
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			return nil, fmt.Errorf("something went wrong")
		},
	})

	req := frameRequest(t, "tools/call", map[string]any{
		"name":      "fail",
		"arguments": map[string]any{},
	}, 5)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected JSON-RPC error: %v", resp.Error)
	}

	result := resp.Result.(map[string]any)
	if result["isError"] != true {
		t.Error("expected isError=true")
	}
	content := result["content"].([]any)
	item := content[0].(map[string]any)
	if item["text"] != "something went wrong" {
		t.Errorf("error text = %v", item["text"])
	}
}

func TestToolsCallInvalidParams(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{Name: "echo", Description: "Echo"})

	req := frameRequest(t, "tools/call", "not-an-object", 6)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error == nil {
		t.Fatal("expected error response")
	}
	errObj := resp.Error.(map[string]any)
	if errObj["code"] != float64(CodeInvalidParams) {
		t.Errorf("error code = %v, want %v", errObj["code"], CodeInvalidParams)
	}
}

func TestUnknownMethod(t *testing.T) {
	srv := New("test", "1.0")
	req := frameRequest(t, "foo/bar", nil, 7)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error == nil {
		t.Fatal("expected error response")
	}
	errObj := resp.Error.(map[string]any)
	if errObj["code"] != float64(CodeMethodNotFound) {
		t.Errorf("error code = %v, want %v", errObj["code"], CodeMethodNotFound)
	}
}

func TestParseError(t *testing.T) {
	srv := New("test", "1.0")
	badFrame := "Content-Length: 5\r\n\r\n{bad}"
	var buf bytes.Buffer
	err := srv.ServeIO(context.Background(), strings.NewReader(badFrame), &buf)
	if err != nil {
		t.Fatalf("ServeIO returned error: %v", err)
	}
}

func TestPanicRecovery(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "panic",
		Description: "Panics",
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			panic("test panic")
		},
	})

	req := frameRequest(t, "tools/call", map[string]any{
		"name":      "panic",
		"arguments": map[string]any{},
	}, 8)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error == nil {
		t.Fatal("expected error response from panic recovery")
	}
	errObj := resp.Error.(map[string]any)
	if errObj["code"] != float64(CodeInternalError) {
		t.Errorf("error code = %v, want %v", errObj["code"], CodeInternalError)
	}
}

func TestMultipleRequests(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "add",
		Description: "Adds numbers",
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			var args struct {
				A float64 `json:"a"`
				B float64 `json:"b"`
			}
			if err := json.Unmarshal(input, &args); err != nil {
				return nil, err
			}
			return args.A + args.B, nil
		},
	})

	initReq := frameRequest(t, "initialize", nil, 1)
	listReq := frameRequest(t, "tools/list", nil, 2)
	callReq := frameRequest(t, "tools/call", map[string]any{
		"name":      "add",
		"arguments": map[string]float64{"a": 3, "b": 4},
	}, 3)

	all := string(initReq) + string(listReq) + string(callReq)
	buf := runServer(t, srv, all)

	raw := buf.Bytes()
	var respCount int
	for _, line := range strings.Split(string(raw), "Content-Length:") {
		if strings.TrimSpace(line) != "" {
			respCount++
		}
	}

	if respCount != 3 {
		t.Fatalf("expected 3 responses, got %d (raw: %s)", respCount, buf.String())
	}
}

func TestEOF(t *testing.T) {
	srv := New("test", "1.0")
	err := srv.ServeIO(context.Background(), strings.NewReader(""), &bytes.Buffer{})
	if err != nil {
		t.Fatalf("expected nil error on EOF, got: %v", err)
	}
}

func TestContextCancellation(t *testing.T) {
	srv := New("test", "1.0")
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	err := srv.ServeIO(ctx, strings.NewReader(""), &bytes.Buffer{})
	if err != context.Canceled {
		t.Errorf("expected context.Canceled, got: %v", err)
	}
}

func TestNilHandlerTool(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "nohandler",
		Description: "No handler set",
		Handler:     nil,
	})

	req := frameRequest(t, "tools/call", map[string]any{
		"name":      "nohandler",
		"arguments": map[string]any{},
	}, 9)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error == nil {
		t.Fatal("expected error response for nil handler")
	}
	errObj := resp.Error.(map[string]any)
	if errObj["code"] != float64(CodeInternalError) {
		t.Errorf("error code = %v, want %v", errObj["code"], CodeInternalError)
	}
}

func TestToolsCallStructuredResult(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "ports",
		Description: "List open ports",
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			return map[string]any{"free": []int{39000, 39001}}, nil
		},
	})

	req := frameRequest(t, "tools/call", map[string]any{
		"name":      "ports",
		"arguments": map[string]any{},
	}, 10)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected JSON-RPC error: %v", resp.Error)
	}

	result := resp.Result.(map[string]any)
	content := result["content"].([]any)
	item := content[0].(map[string]any)
	text, ok := item["text"].(string)
	if !ok {
		t.Fatalf("text field is not a string: %T", item["text"])
	}
	if text != `{"free":[39000,39001]}` {
		t.Errorf("text = %q, want %q", text, `{"free":[39000,39001]}`)
	}
	if result["isError"] != false {
		t.Error("expected isError=false")
	}
}

func TestToolsCallScalarResult(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "count",
		Description: "Return a number",
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			return 42, nil
		},
	})

	req := frameRequest(t, "tools/call", map[string]any{
		"name":      "count",
		"arguments": map[string]any{},
	}, 11)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected JSON-RPC error: %v", resp.Error)
	}

	result := resp.Result.(map[string]any)
	content := result["content"].([]any)
	item := content[0].(map[string]any)
	text, ok := item["text"].(string)
	if !ok {
		t.Fatalf("text field is not a string: %T", item["text"])
	}
	if text != "42" {
		t.Errorf("text = %q, want %q", text, "42")
	}
}

func TestToolsCallBooleanResult(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "check",
		Description: "Return a boolean",
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			return true, nil
		},
	})

	req := frameRequest(t, "tools/call", map[string]any{
		"name":      "check",
		"arguments": map[string]any{},
	}, 12)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected JSON-RPC error: %v", resp.Error)
	}

	result := resp.Result.(map[string]any)
	content := result["content"].([]any)
	item := content[0].(map[string]any)
	text, ok := item["text"].(string)
	if !ok {
		t.Fatalf("text field is not a string: %T", item["text"])
	}
	if text != "true" {
		t.Errorf("text = %q, want %q", text, "true")
	}
}
func TestToolsListNoAnnotations(t *testing.T) {
	// Tools without annotations must not emit an "annotations" field,
	// preserving backward compatibility.
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "search",
		Description: "Search documents",
		InputSchema: json.RawMessage(`{"type":"object"}`),
	})
	srv.RegisterTool(&Tool{
		Name: "index",
	})

	req := frameRequest(t, "tools/list", nil, 1)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected error: %v", resp.Error)
	}

	result := resp.Result.(map[string]any)
	tools := result["tools"].([]any)
	for i, raw := range tools {
		tool := raw.(map[string]any)
		if _, exists := tool["annotations"]; exists {
			t.Errorf("tool[%d] has unexpected annotations field", i)
		}
	}
}

func TestToolsListWithAnnotations(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "read-file",
		Description: "Read a file from disk",
		InputSchema: json.RawMessage(`{"type":"object"}`),
		Annotations: &ToolAnnotations{
			Title:         "Read File",
			ReadOnlyHint:  true,
			IdempotentHint: true,
		},
	})
	srv.RegisterTool(&Tool{
		Name:        "delete-file",
		Description: "Delete a file",
		InputSchema: json.RawMessage(`{"type":"object"}`),
		Annotations: &ToolAnnotations{
			Title:            "Delete File",
			DestructiveHint:  true,
		},
	})

	req := frameRequest(t, "tools/list", nil, 2)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected error: %v", resp.Error)
	}

	result := resp.Result.(map[string]any)
	tools := result["tools"].([]any)
	if len(tools) != 2 {
		t.Fatalf("tools count = %d, want 2", len(tools))
	}

	// First tool: read-file with ReadOnlyHint
	t1 := tools[0].(map[string]any)
	if t1["name"] != "read-file" {
		t.Errorf("tool[0] name = %v, want read-file", t1["name"])
	}
	a1, ok := t1["annotations"].(map[string]any)
	if !ok {
		t.Fatal("tool[0] annotations is not a map")
	}
	if a1["title"] != "Read File" {
		t.Errorf("tool[0] annotations.title = %v, want 'Read File'", a1["title"])
	}
	if a1["readOnlyHint"] != true {
		t.Errorf("tool[0] annotations.readOnlyHint = %v, want true", a1["readOnlyHint"])
	}
	if a1["idempotentHint"] != true {
		t.Errorf("tool[0] annotations.idempotentHint = %v, want true", a1["idempotentHint"])
	}
	// Should NOT be present because it was not set
	if _, exists := a1["destructiveHint"]; exists {
		t.Error("tool[0] annotations should not have destructiveHint")
	}
	if _, exists := a1["openWorldHint"]; exists {
		t.Error("tool[0] annotations should not have openWorldHint")
	}

	// Second tool: delete-file with DestructiveHint
	t2 := tools[1].(map[string]any)
	if t2["name"] != "delete-file" {
		t.Errorf("tool[1] name = %v, want delete-file", t2["name"])
	}
	a2, ok := t2["annotations"].(map[string]any)
	if !ok {
		t.Fatal("tool[1] annotations is not a map")
	}
	if a2["title"] != "Delete File" {
		t.Errorf("tool[1] annotations.title = %v, want 'Delete File'", a2["title"])
	}
	if a2["destructiveHint"] != true {
		t.Errorf("tool[1] annotations.destructiveHint = %v, want true", a2["destructiveHint"])
	}
	// Should NOT have readOnlyHint (not set)
	if _, exists := a2["readOnlyHint"]; exists {
		t.Error("tool[1] annotations should not have readOnlyHint")
	}
}

func TestToolsListAnnotationsAllHints(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "full-annotations",
		Description: "Tool with every annotation set",
		Annotations: &ToolAnnotations{
			Title:            "Full",
			ReadOnlyHint:     false,
			IdempotentHint:   true,
			OpenWorldHint:    true,
			DestructiveHint:  false,
		},
	})

	req := frameRequest(t, "tools/list", nil, 3)
	buf := runServer(t, srv, string(req))

	resp := readResponse(t, buf)
	if resp.Error != nil {
		t.Fatalf("unexpected error: %v", resp.Error)
	}

	result := resp.Result.(map[string]any)
	tools := result["tools"].([]any)
	if len(tools) != 1 {
		t.Fatalf("tools count = %d, want 1", len(tools))
	}

	tool := tools[0].(map[string]any)
	a, ok := tool["annotations"].(map[string]any)
	if !ok {
		t.Fatal("annotations is not a map")
	}

	// Check all fields are present
	if a["title"] != "Full" {
		t.Errorf("title = %v, want 'Full'", a["title"])
	}
	// readOnlyHint=false and destructiveHint=false are omitted by
	// omitempty, which is correct MCP behaviour — only true-valued
	// hints are meaningful in the protocol.
	if _, exists := a["readOnlyHint"]; exists {
		t.Error("readOnlyHint should be omitted (false + omitempty)")
	}
	if a["idempotentHint"] != true {
		t.Errorf("idempotentHint = %v, want true", a["idempotentHint"])
	}
	if a["openWorldHint"] != true {
		t.Errorf("openWorldHint = %v, want true", a["openWorldHint"])
	}
	if _, exists := a["destructiveHint"]; exists {
		t.Error("destructiveHint should be omitted (false + omitempty)")
	}
}
func TestServeIORejectsOversizedLine(t *testing.T) {
	srv := New("test", "1.0.0")
	// A single line far larger than maxLineBytes with no newline must be
	// rejected instead of buffered without bound.
	oversized := strings.Repeat("a", maxLineBytes+10)

	var buf bytes.Buffer
	err := srv.ServeIO(context.Background(), strings.NewReader(oversized), &buf)
	if err == nil {
		t.Fatal("expected error for oversized line, got nil")
	}
	if !strings.Contains(err.Error(), "exceeds") {
		t.Errorf("expected size-limit error, got %v", err)
	}
}
