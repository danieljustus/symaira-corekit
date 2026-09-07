package mcpserver

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync/atomic"
	"testing"
)

func finalGapResponseBody(t *testing.T, raw []byte, framed bool) []byte {
	t.Helper()
	if !framed {
		return bytes.TrimSpace(raw)
	}
	separator := []byte("\r\n\r\n")
	idx := bytes.Index(raw, separator)
	if idx < 0 {
		t.Fatalf("missing response header separator: %q", raw)
	}
	return bytes.TrimSpace(raw[idx+len(separator):])
}

func TestNumericRequestIDPreservedInLineAndFramedResponses(t *testing.T) {
	const id = "9007199254740993"
	for _, framed := range []bool{false, true} {
		mode := "line"
		if framed {
			mode = "framed"
		}
		t.Run(mode, func(t *testing.T) {
			body := `{"jsonrpc":"2.0","id":` + id + `,"method":"ping"}`
			input := body + "\n"
			if framed {
				input = fmt.Sprintf("Content-Length: %d\r\n\r\n%s", len(body), body)
			}
			var output bytes.Buffer
			if err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(input), &output); err != nil {
				t.Fatalf("ServeIO: %v", err)
			}

			var response struct {
				ID json.RawMessage `json:"id"`
			}
			if err := json.Unmarshal(finalGapResponseBody(t, output.Bytes(), framed), &response); err != nil {
				t.Fatalf("decode response: %v", err)
			}
			if got := string(response.ID); got != id {
				t.Fatalf("response id = %s, want exact numeric id %s", got, id)
			}
		})
	}
}

func TestParamsMustBeObjectOrArray(t *testing.T) {
	for _, framed := range []bool{false, true} {
		mode := "line"
		if framed {
			mode = "framed"
		}
		t.Run(mode, func(t *testing.T) {
			for _, params := range []string{`"text"`, `42`, `true`, `null`} {
				t.Run(params, func(t *testing.T) {
					body := `{"jsonrpc":"2.0","id":1,"method":"ping","params":` + params + `}`
					input := body + "\n"
					if framed {
						input = fmt.Sprintf("Content-Length: %d\r\n\r\n%s", len(body), body)
					}
					var output bytes.Buffer
					if err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(input), &output); err != nil {
						t.Fatalf("ServeIO: %v", err)
					}
					if got := responseErrorCode(t, output.Bytes(), framed); got != CodeInvalidRequest {
						t.Fatalf("error code = %v, want %v", got, CodeInvalidRequest)
					}
				})
			}

			body := `{"jsonrpc":"2.0","id":1,"method":"ping","params":[]}`
			input := body + "\n"
			if framed {
				input = fmt.Sprintf("Content-Length: %d\r\n\r\n%s", len(body), body)
			}
			var output bytes.Buffer
			if err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(input), &output); err != nil {
				t.Fatalf("array params ServeIO: %v", err)
			}
			var response jsonRPCResponse
			if err := json.Unmarshal(finalGapResponseBody(t, output.Bytes(), framed), &response); err != nil {
				t.Fatalf("decode array-params response: %v", err)
			}
			if response.Error != nil {
				t.Fatalf("array params rejected: %#v", response.Error)
			}
		})
	}
}

func TestToolCallNotificationExecutesWithoutResponse(t *testing.T) {
	for _, framed := range []bool{false, true} {
		mode := "line"
		if framed {
			mode = "framed"
		}
		t.Run(mode, func(t *testing.T) {
			var calls atomic.Int32
			srv := New("test", "1.0")
			srv.RegisterTool(&Tool{
				Name: "write",
				Handler: func(context.Context, json.RawMessage) (any, error) {
					calls.Add(1)
					return "written", nil
				},
			})
			body := `{"jsonrpc":"2.0","method":"tools/call","params":{"name":"write","arguments":{}}}`
			input := body + "\n"
			if framed {
				input = fmt.Sprintf("Content-Length: %d\r\n\r\n%s", len(body), body)
			}
			var output bytes.Buffer
			if err := srv.ServeIO(context.Background(), strings.NewReader(input), &output); err != nil {
				t.Fatalf("ServeIO: %v", err)
			}
			if got := calls.Load(); got != 1 {
				t.Fatalf("tool calls = %d, want 1", got)
			}
			if output.Len() != 0 {
				t.Fatalf("notification produced response: %q", output.Bytes())
			}
		})
	}
}

func TestOrdinaryNotificationRemainsSilent(t *testing.T) {
	for _, framed := range []bool{false, true} {
		mode := "line"
		if framed {
			mode = "framed"
		}
		t.Run(mode, func(t *testing.T) {
			body := `{"jsonrpc":"2.0","method":"ping"}`
			input := body + "\n"
			if framed {
				input = fmt.Sprintf("Content-Length: %d\r\n\r\n%s", len(body), body)
			}
			var output bytes.Buffer
			if err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(input), &output); err != nil {
				t.Fatalf("ServeIO: %v", err)
			}
			if output.Len() != 0 {
				t.Fatalf("notification produced response: %q", output.Bytes())
			}
		})
	}
}
