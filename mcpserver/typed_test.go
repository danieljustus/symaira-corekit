package mcpserver

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"
)

type typedArgs struct {
	Query  string   `json:"query" desc:"search query"`
	Limit  int      `json:"limit,omitempty" desc:"max results"`
	Ratio  float64  `json:"ratio"`
	Exact  bool     `json:"exact,omitempty"`
	Tags   []string `json:"tags,omitempty" desc:"filter tags"`
	Detail *detail  `json:"detail,omitempty"`
	Hidden string   `json:"-"`
}

type detail struct {
	Depth int `json:"depth" desc:"recursion depth"`
}

func registeredTypedServer(t *testing.T, handler func(context.Context, typedArgs) (any, error)) *Server {
	t.Helper()
	srv := New("typed-test", "0.0.1")
	RegisterTyped(srv, "search", "typed search tool", handler)
	return srv
}

// roundTrip sends one line-mode JSON-RPC request and returns the raw response
// line for substring/unmarshal assertions.
func roundTrip(t *testing.T, srv *Server, request string) string {
	t.Helper()
	return strings.TrimSpace(runServer(t, srv, request+"\n").String())
}

func typedSchema(t *testing.T, srv *Server, tool string) map[string]any {
	t.Helper()
	resp := roundTrip(t, srv, `{"jsonrpc":"2.0","id":1,"method":"tools/list"}`)
	var r struct {
		Result struct {
			Tools []struct {
				Name        string         `json:"name"`
				InputSchema map[string]any `json:"inputSchema"`
			} `json:"tools"`
		} `json:"result"`
	}
	if err := json.Unmarshal([]byte(resp), &r); err != nil {
		t.Fatalf("unmarshal tools/list: %v", err)
	}
	for _, tool := range r.Result.Tools {
		if tool.Name == "search" {
			return tool.InputSchema
		}
	}
	t.Fatalf("tool %q not found in tools/list", tool)
	return nil
}

func TestRegisterTyped_SchemaDerivation(t *testing.T) {
	srv := registeredTypedServer(t, func(_ context.Context, a typedArgs) (any, error) {
		return a, nil
	})
	schema := typedSchema(t, srv, "search")

	if schema["type"] != "object" {
		t.Fatalf("schema type = %v, want object", schema["type"])
	}
	props, ok := schema["properties"].(map[string]any)
	if !ok {
		t.Fatalf("properties missing or wrong type: %v", schema["properties"])
	}

	wantTypes := map[string]string{
		"query": "string",
		"limit": "integer",
		"ratio": "number",
		"exact": "boolean",
		"tags":  "array",
	}
	for name, typ := range wantTypes {
		p, ok := props[name].(map[string]any)
		if !ok {
			t.Fatalf("property %q missing", name)
		}
		if p["type"] != typ {
			t.Errorf("property %q type = %v, want %s", name, p["type"], typ)
		}
	}

	if props["query"].(map[string]any)["description"] != "search query" {
		t.Errorf("desc tag not applied to query: %v", props["query"])
	}
	if _, exists := props["Hidden"]; exists {
		t.Errorf("json:\"-\" field must be skipped")
	}

	// Nested struct via pointer.
	d := props["detail"].(map[string]any)
	if d["type"] != "object" {
		t.Fatalf("detail type = %v, want object", d["type"])
	}
	depth := d["properties"].(map[string]any)["depth"].(map[string]any)
	if depth["type"] != "integer" || depth["description"] != "recursion depth" {
		t.Errorf("nested depth schema wrong: %v", depth)
	}

	// Required set: non-omitempty, non-pointer fields only.
	got := schema["required"]
	var required []string
	if got != nil {
		for _, v := range got.([]any) {
			required = append(required, v.(string))
		}
	}
	want := []string{"query", "ratio"}
	if !reflect.DeepEqual(required, want) {
		t.Errorf("required = %v, want %v", required, want)
	}
}

func TestRegisterTyped_HandlerDispatch(t *testing.T) {
	var got typedArgs
	srv := registeredTypedServer(t, func(_ context.Context, a typedArgs) (any, error) {
		got = a
		return map[string]any{"echo": a.Query}, nil
	})

	resp := roundTrip(t, srv, `{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search","arguments":{"query":"hello","limit":3,"detail":{"depth":2}}}}`)
	var r struct {
		Result struct {
			IsError bool `json:"isError"`
		} `json:"result"`
	}
	if err := json.Unmarshal([]byte(resp), &r); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}
	if r.Result.IsError {
		t.Fatalf("unexpected tool error: %s", resp)
	}
	if got.Query != "hello" || got.Limit != 3 || got.Detail == nil || got.Detail.Depth != 2 {
		t.Errorf("handler received %+v", got)
	}
}

func TestRegisterTyped_EmptyArguments(t *testing.T) {
	called := false
	srv := registeredTypedServer(t, func(_ context.Context, a typedArgs) (any, error) {
		called = true
		return "ok", nil
	})
	resp := roundTrip(t, srv, `{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search"}}`)
	if !called {
		t.Fatal("handler not called for empty arguments")
	}
	if strings.Contains(resp, `"isError":true`) {
		t.Errorf("empty arguments must decode to zero value: %s", resp)
	}
}

func TestRegisterTyped_BadJSON(t *testing.T) {
	srv := registeredTypedServer(t, func(_ context.Context, a typedArgs) (any, error) {
		t.Fatal("handler must not run on bad JSON")
		return nil, nil
	})
	resp := roundTrip(t, srv, `{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"search","arguments":"not-an-object"}}`)
	if !strings.Contains(resp, `"isError":true`) || !strings.Contains(resp, "invalid arguments for search") {
		t.Errorf("expected tool error for bad JSON, got %s", resp)
	}
}

func TestRegisterTyped_UnknownFieldRejected(t *testing.T) {
	srv := registeredTypedServer(t, func(_ context.Context, a typedArgs) (any, error) {
		t.Fatal("handler must not run on unknown field")
		return nil, nil
	})
	resp := roundTrip(t, srv, `{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"search","arguments":{"query":"x","nope":1}}}`)
	if !strings.Contains(resp, `"isError":true`) || !strings.Contains(resp, "unknown field") {
		t.Errorf("expected unknown-field tool error, got %s", resp)
	}
}

func TestRegisterTyped_WrongTypeRejected(t *testing.T) {
	srv := registeredTypedServer(t, func(_ context.Context, a typedArgs) (any, error) {
		t.Fatal("handler must not run on type mismatch")
		return nil, nil
	})
	resp := roundTrip(t, srv, `{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"search","arguments":{"limit":"three"}}}`)
	if !strings.Contains(resp, `"isError":true`) {
		t.Errorf("expected tool error for type mismatch, got %s", resp)
	}
}

func TestRegisterTyped_HandlerErrorPropagates(t *testing.T) {
	srv := registeredTypedServer(t, func(_ context.Context, a typedArgs) (any, error) {
		return nil, errors.New("boom")
	})
	resp := roundTrip(t, srv, `{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"search","arguments":{"query":"x"}}}`)
	if !strings.Contains(resp, `"isError":true`) || !strings.Contains(resp, "boom") {
		t.Errorf("expected handler error surfaced, got %s", resp)
	}
}

func TestRegisterTyped_NonStructPanics(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Fatal("expected panic for non-struct T")
		}
	}()
	srv := New("panic-test", "0.0.1")
	RegisterTyped[int](srv, "bad", "bad", func(_ context.Context, n int) (any, error) { return n, nil })
}

func TestRegisterTyped_UnsupportedKindPanics(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Fatal("expected panic for unsupported field kind")
		}
	}()
	type bad struct {
		Ch chan int `json:"ch"`
	}
	srv := New("panic-test", "0.0.1")
	RegisterTyped[bad](srv, "bad", "bad", func(_ context.Context, b bad) (any, error) { return nil, nil })
}

func TestRegisterTyped_RawToolPathUnchanged(t *testing.T) {
	srv := New("mixed", "0.0.1")
	RegisterTyped(srv, "typed", "typed tool", func(_ context.Context, a typedArgs) (any, error) {
		return a.Query, nil
	})
	srv.RegisterTool(&Tool{
		Name:        "raw",
		Description: "raw tool",
		InputSchema: json.RawMessage(`{"type":"object"}`),
		Handler: func(_ context.Context, input json.RawMessage) (any, error) {
			return string(input), nil
		},
	})

	resp := roundTrip(t, srv, `{"jsonrpc":"2.0","id":8,"method":"tools/call","params":{"name":"raw","arguments":{"anything":true}}}`)
	if strings.Contains(resp, `"isError":true`) {
		t.Errorf("raw tool path broken: %s", resp)
	}
}
