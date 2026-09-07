package mcpserver

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"sync"
	"testing"
	"time"
)

func validPingBody() string {
	return `{"jsonrpc":"2.0","id":1,"method":"ping"}`
}

func framedHeaders(headers []string, body string) string {
	return strings.Join(headers, "\r\n") + "\r\n\r\n" + body
}

func framedPing(headers []string) string {
	return framedHeaders(headers, validPingBody())
}

func responseErrorCode(t *testing.T, raw []byte, framed bool) float64 {
	t.Helper()
	var body []byte
	if framed {
		separator := []byte("\r\n\r\n")
		idx := bytes.Index(raw, separator)
		if idx < 0 {
			t.Fatalf("missing response header separator: %q", raw)
		}
		body = raw[idx+len(separator):]
	} else {
		body = bytes.TrimSpace(raw)
	}
	var response jsonRPCResponse
	if err := json.Unmarshal(body, &response); err != nil {
		t.Fatalf("decode response: %v\nraw: %q", err, raw)
	}
	errObject, ok := response.Error.(map[string]any)
	if !ok {
		t.Fatalf("response error = %#v", response.Error)
	}
	code, ok := errObject["code"].(float64)
	if !ok {
		t.Fatalf("response error code = %#v", errObject["code"])
	}
	if response.ID != nil {
		t.Errorf("response id = %#v, want nil", response.ID)
	}
	return code
}

func TestFramedHeaderAggregateBytes(t *testing.T) {
	body := validPingBody()
	tests := []struct {
		name   string
		prefix []string
	}{
		{name: "content-length-first", prefix: []string{"Content-Length: " + fmt.Sprint(len(body))}},
		{name: "leading-content-type", prefix: []string{"Content-Type: application/vscode-jsonrpc; charset=utf-8", "Content-Length: " + fmt.Sprint(len(body))}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			baseBytes := 0
			for _, line := range tt.prefix {
				baseBytes += len(line) + 2
			}
			filler := maxHeaderBytes - baseBytes - len("X:") - 2
			if filler <= 0 || filler >= maxLineBytes {
				t.Fatalf("invalid test filler size: %d", filler)
			}
			exact := append(append([]string{}, tt.prefix...), "X:"+strings.Repeat("a", filler))
			input := framedHeaders(exact, body)
			var output bytes.Buffer
			if err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(input), &output); err != nil {
				t.Fatalf("boundary header bytes rejected: %v", err)
			}
			if output.Len() == 0 {
				t.Fatal("boundary request produced no response")
			}

			over := append(append([]string{}, tt.prefix...), "X:"+strings.Repeat("a", filler+1))
			output.Reset()
			err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(framedHeaders(over, body)), &output)
			if err == nil {
				t.Fatal("expected aggregate header byte limit error")
			}
			if got := err.Error(); got != "mcpserver: read error: framed header limits exceeded" {
				t.Fatalf("error = %q, want stable framing error", got)
			}
		})
	}
}

func TestFramedHeaderAggregateLines(t *testing.T) {
	body := validPingBody()
	tests := []struct {
		name   string
		prefix []string
	}{
		{name: "content-length-first", prefix: []string{"Content-Length: " + fmt.Sprint(len(body))}},
		{name: "leading-content-type", prefix: []string{"Content-Type: application/vscode-jsonrpc; charset=utf-8", "Content-Length: " + fmt.Sprint(len(body))}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			exact := append([]string{}, tt.prefix...)
			for len(exact) < maxHeaderLines {
				exact = append(exact, "X:")
			}
			var output bytes.Buffer
			if err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(framedHeaders(exact, body)), &output); err != nil {
				t.Fatalf("boundary header line count rejected: %v", err)
			}
			if output.Len() == 0 {
				t.Fatal("boundary request produced no response")
			}

			over := append(append([]string{}, exact...), "X:")
			output.Reset()
			err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(framedHeaders(over, body)), &output)
			if err == nil {
				t.Fatal("expected aggregate header line limit error")
			}
			if got := err.Error(); got != "mcpserver: read error: framed header limits exceeded" {
				t.Fatalf("error = %q, want stable framing error", got)
			}
		})
	}
}

func TestInvalidJSONRPCEnvelopesInBothModes(t *testing.T) {
	invalidBodies := []string{
		`{}`,
		`null`,
		`[]`,
		`{"method":"ping"}`,
		`{"jsonrpc":"1.0","method":"ping"}`,
		`{"jsonrpc":"2.0"}`,
		`{"jsonrpc":"2.0","method":""}`,
		`{"jsonrpc":"2.0","method":1}`,
	}
	for _, framed := range []bool{false, true} {
		mode := "line"
		if framed {
			mode = "framed"
		}
		t.Run(mode, func(t *testing.T) {
			for _, body := range invalidBodies {
				t.Run(body, func(t *testing.T) {
					input := body + "\n"
					if framed {
						input = fmt.Sprintf("Content-Length: %d\r\n\r\n%s", len(body), body)
					}
					var output bytes.Buffer
					err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(input), &output)
					if err != nil {
						t.Fatalf("ServeIO: %v", err)
					}
					if got := responseErrorCode(t, output.Bytes(), framed); got != CodeInvalidRequest {
						t.Fatalf("error code = %v, want %v", got, CodeInvalidRequest)
					}
				})
			}
		})
	}
}

func TestMalformedJSONIsParseErrorAndNotificationsAreSilent(t *testing.T) {
	for _, framed := range []bool{false, true} {
		mode := "line"
		if framed {
			mode = "framed"
		}
		t.Run(mode, func(t *testing.T) {
			bad := `{"jsonrpc":`
			input := bad + "\n"
			if framed {
				input = fmt.Sprintf("Content-Length: %d\r\n\r\n%s", len(bad), bad)
			}
			var output bytes.Buffer
			if err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(input), &output); err != nil {
				t.Fatalf("ServeIO: %v", err)
			}
			if got := responseErrorCode(t, output.Bytes(), framed); got != CodeParseError {
				t.Fatalf("error code = %v, want %v", got, CodeParseError)
			}

			notification := `{"jsonrpc":"2.0","method":"ping"}` + "\n"
			if framed {
				notification = fmt.Sprintf("Content-Length: %d\r\n\r\n%s", len(strings.TrimSpace(notification)), strings.TrimSpace(notification))
			}
			output.Reset()
			if err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(notification), &output); err != nil {
				t.Fatalf("notification ServeIO: %v", err)
			}
			if output.Len() != 0 {
				t.Fatalf("notification produced response: %q", output.Bytes())
			}
		})
	}
}

func TestExplicitNullIDRequestResponds(t *testing.T) {
	for _, framed := range []bool{false, true} {
		body := `{"jsonrpc":"2.0","id":null,"method":"ping"}`
		input := body + "\n"
		if framed {
			input = fmt.Sprintf("Content-Length: %d\r\n\r\n%s", len(body), body)
		}
		var output bytes.Buffer
		if err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(input), &output); err != nil {
			t.Fatalf("ServeIO: %v", err)
		}
		if output.Len() == 0 {
			t.Fatalf("framed=%v: explicit null id request produced no response", framed)
		}
	}
}

type flushWriter struct {
	mu       sync.Mutex
	buf      bytes.Buffer
	flushes  int
	flushErr error
	writeErr error
}

func (w *flushWriter) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.writeErr != nil {
		return len(p) / 2, w.writeErr
	}
	return w.buf.Write(p)
}

func (w *flushWriter) Flush() error {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.flushes++
	return w.flushErr
}

func (w *flushWriter) Bytes() []byte {
	w.mu.Lock()
	defer w.mu.Unlock()
	return append([]byte(nil), w.buf.Bytes()...)
}

func TestServeIOFlushesEachCompleteResponse(t *testing.T) {
	for _, framed := range []bool{false, true} {
		body := validPingBody()
		input := body + "\n"
		if framed {
			input = fmt.Sprintf("Content-Length: %d\r\n\r\n%s", len(body), body)
		}
		writer := &flushWriter{}
		if err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(input), writer); err != nil {
			t.Fatalf("framed=%v: ServeIO: %v", framed, err)
		}
		if writer.flushes != 1 {
			t.Fatalf("framed=%v: flushes = %d, want 1", framed, writer.flushes)
		}
		if len(writer.Bytes()) == 0 {
			t.Fatalf("framed=%v: no response written", framed)
		}
	}
}

func TestServeIOPropagatesWriteAndFlushErrors(t *testing.T) {
	writeErr := errors.New("write failed")
	flushErr := errors.New("flush failed")
	body := validPingBody()
	input := body + "\n"

	writer := &flushWriter{writeErr: writeErr}
	if err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(input), writer); !errors.Is(err, writeErr) {
		t.Fatalf("write error = %v, want %v", err, writeErr)
	}

	writer = &flushWriter{flushErr: flushErr}
	if err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(input), writer); !errors.Is(err, flushErr) {
		t.Fatalf("flush error = %v, want %v", err, flushErr)
	}
}

func TestServeIOConcurrentResponsesAreSerializedAndFlushed(t *testing.T) {
	started := make(chan struct{}, 2)
	release := make(chan struct{})
	srv := New("test", "1.0")
	for _, name := range []string{"one", "two"} {
		name := name
		srv.RegisterTool(&Tool{
			Name: name,
			Handler: func(context.Context, json.RawMessage) (any, error) {
				started <- struct{}{}
				<-release
				return name, nil
			},
		})
	}
	go func() {
		<-started
		<-started
		close(release)
	}()

	request := func(id int, name string) string {
		body := fmt.Sprintf(`{"jsonrpc":"2.0","id":%d,"method":"tools/call","params":{"name":%q,"arguments":{}}}`, id, name)
		return fmt.Sprintf("Content-Length: %d\r\n\r\n%s", len(body), body)
	}
	writer := &flushWriter{}
	input := request(1, "one") + request(2, "two")
	if err := srv.ServeIO(context.Background(), strings.NewReader(input), writer); err != nil {
		t.Fatalf("ServeIO: %v", err)
	}
	if writer.flushes != 2 {
		t.Fatalf("flushes = %d, want 2", writer.flushes)
	}

	raw := writer.Bytes()
	responseCount := 0
	for len(raw) > 0 {
		if !bytes.HasPrefix(raw, []byte("Content-Length: ")) {
			t.Fatalf("response %d is not a complete frame: %q", responseCount, raw)
		}
		separator := bytes.Index(raw, []byte("\r\n\r\n"))
		if separator < 0 {
			t.Fatalf("response %d missing separator: %q", responseCount, raw)
		}
		var length int
		if _, err := fmt.Sscanf(string(raw[len("Content-Length: "):separator]), "%d", &length); err != nil {
			t.Fatalf("response %d content length: %v", responseCount, err)
		}
		start := separator + 4
		if len(raw) < start+length {
			t.Fatalf("response %d body is partial", responseCount)
		}
		var response jsonRPCResponse
		if err := json.Unmarshal(raw[start:start+length], &response); err != nil {
			t.Fatalf("response %d JSON: %v", responseCount, err)
		}
		raw = raw[start+length:]
		if response.Error != nil {
			t.Fatalf("response %d returned error: %#v", responseCount, response.Error)
		}
		responseCount++
	}
	if responseCount != 2 {
		t.Fatalf("response count = %d, want 2", responseCount)
	}
}

func TestPartialWriteWithoutErrorStillSurfacesShortWrite(t *testing.T) {
	writer := &shortWriter{}
	body := validPingBody()
	input := body + "\n"
	err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(input), writer)
	if !errors.Is(err, io.ErrShortWrite) {
		t.Fatalf("error = %v, want io.ErrShortWrite", err)
	}
}

func TestConcurrentWriteErrorStopsServeIOWithOpenReader(t *testing.T) {
	writeErr := errors.New("flush failed")
	reader, writer := io.Pipe()
	t.Cleanup(func() {
		_ = writer.Close()
		_ = reader.Close()
	})

	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name: "fail",
		Handler: func(context.Context, json.RawMessage) (any, error) {
			return "done", nil
		},
	})

	done := make(chan error, 1)
	go func() {
		done <- srv.ServeIO(context.Background(), reader, &flushWriter{flushErr: writeErr})
	}()

	body := `{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"fail","arguments":{}}}`
	if _, err := io.WriteString(writer, fmt.Sprintf("Content-Length: %d\r\n\r\n%s", len(body), body)); err != nil {
		t.Fatalf("write request: %v", err)
	}

	select {
	case err := <-done:
		if !errors.Is(err, writeErr) {
			t.Fatalf("ServeIO error = %v, want %v", err, writeErr)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("ServeIO remained blocked on the open reader after a concurrent write error")
	}
}

func TestLineModeJSONValuesWithColonAreInvalidRequests(t *testing.T) {
	for _, body := range []string{`["x:y"]`, `"x:y"`} {
		t.Run(body, func(t *testing.T) {
			var output bytes.Buffer
			if err := New("test", "1.0").ServeIO(context.Background(), strings.NewReader(body+"\n"), &output); err != nil {
				t.Fatalf("ServeIO: %v", err)
			}
			if got := responseErrorCode(t, output.Bytes(), false); got != CodeInvalidRequest {
				t.Fatalf("error code = %v, want %v", got, CodeInvalidRequest)
			}
		})
	}
}

func TestInvalidRequestIDTypes(t *testing.T) {
	for _, framed := range []bool{false, true} {
		mode := "line"
		if framed {
			mode = "framed"
		}
		t.Run(mode, func(t *testing.T) {
			for _, id := range []string{`{}`, `[]`, `true`, `false`} {
				t.Run(id, func(t *testing.T) {
					body := fmt.Sprintf(`{"jsonrpc":"2.0","id":%s,"method":"ping"}`, id)
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
		})
	}
}

type shortWriter struct{}

func (*shortWriter) Write(p []byte) (int, error) {
	return len(p) / 2, nil
}
