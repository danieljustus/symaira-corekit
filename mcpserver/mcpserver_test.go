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
