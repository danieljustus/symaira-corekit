package mcpserver

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"testing"

	"github.com/danieljustus/symaira-corekit/exitcodes"
)

// structuredError implements every optional tool-error interface, standing in
// for a consumer's own error type (symbrowse's daemon-proxy error carries
// exactly these methods).
type structuredError struct {
	code       string
	message    string
	retryable  bool
	confirm    bool
	resumeHint string
	hint       string
	details    map[string]any
}

func (e *structuredError) Error() string                { return e.message }
func (e *structuredError) ErrorCode() string            { return e.code }
func (e *structuredError) RetryableError() bool         { return e.retryable }
func (e *structuredError) RequiresConfirmation() bool   { return e.confirm }
func (e *structuredError) ResumeGuidance() string       { return e.resumeHint }
func (e *structuredError) ErrorHint() string            { return e.hint }
func (e *structuredError) ErrorDetails() map[string]any { return e.details }

func TestToolErrorDataNil(t *testing.T) {
	if data := ToolErrorData(nil); data != nil {
		t.Errorf("ToolErrorData(nil) = %v, want nil", data)
	}
}

// An error that only has a message must not grow a metadata object: the
// result of such a call has to stay byte-identical to a server without this
// feature.
func TestToolErrorDataPlainErrorHasNoMetadata(t *testing.T) {
	if data := ToolErrorData(errors.New("something went wrong")); data != nil {
		t.Errorf("ToolErrorData(plain) = %v, want nil", data)
	}
}

func TestToolErrorDataCollectsEveryField(t *testing.T) {
	err := &structuredError{
		code:       "operation_failed",
		message:    "operation_failed: fetch https://example.com/gone: 404",
		retryable:  false,
		confirm:    false,
		resumeHint: "try one of the candidate URLs",
		hint:       "the page moved",
		details:    map[string]any{"recovery": map[string]any{"nearest_ancestor": "https://example.com/"}},
	}

	want := map[string]any{
		"code":                  "operation_failed",
		"message":               err.message,
		"retryable":             false,
		"requires_confirmation": false,
		"resume_hint":           "try one of the candidate URLs",
		"hint":                  "the page moved",
		"details":               err.details,
	}
	if got := ToolErrorData(err); !reflect.DeepEqual(got, want) {
		t.Errorf("ToolErrorData() = %#v, want %#v", got, want)
	}
}

// "retryable": false is a claim the caller can act on — it says a second
// attempt is wasted. Only an error that never implements the interface may
// leave the field out.
func TestToolErrorDataReportsNegativeBooleans(t *testing.T) {
	data := ToolErrorData(&structuredError{code: "peer_denied", message: "denied"})
	if retryable, ok := data["retryable"]; !ok || retryable != false {
		t.Errorf("retryable = %v (present: %v), want false", retryable, ok)
	}
	if confirm, ok := data["requires_confirmation"]; !ok || confirm != false {
		t.Errorf("requires_confirmation = %v (present: %v), want false", confirm, ok)
	}
}

// Handlers routinely wrap the error they got with the tool name, so the
// metadata has to survive a %w.
func TestToolErrorDataUnwraps(t *testing.T) {
	wrapped := fmt.Errorf("fetch_url: %w", &structuredError{code: "operation_timeout", message: "timed out", retryable: true})

	data := ToolErrorData(wrapped)
	if data["code"] != "operation_timeout" {
		t.Errorf("code = %v, want operation_timeout", data["code"])
	}
	if data["retryable"] != true {
		t.Errorf("retryable = %v, want true", data["retryable"])
	}
	if data["message"] != "fetch_url: timed out" {
		t.Errorf("message = %v, want the wrapped message", data["message"])
	}
}

// A corekit CLIError already classifies itself; a tool returning one gets a
// code and a hint without implementing anything.
func TestToolErrorDataFromCLIError(t *testing.T) {
	err := &exitcodes.CLIError{
		Code:    exitcodes.ExitNoInput,
		Kind:    exitcodes.KindValidation,
		Message: "url is required",
		Hint:    "pass --url",
	}

	data := ToolErrorData(err)
	if data["code"] != string(exitcodes.KindValidation) {
		t.Errorf("code = %v, want %v", data["code"], exitcodes.KindValidation)
	}
	if data["hint"] != "pass --url" {
		t.Errorf("hint = %v, want the CLIError hint", data["hint"])
	}
	if data["message"] != "url is required" {
		t.Errorf("message = %v, want the CLIError message", data["message"])
	}
}

// An explicit ErrorCode beats the CLIError kind it is wrapped in: the
// specific classification is the one the tool chose.
func TestToolErrorDataPrefersExplicitCodeOverCLIErrorKind(t *testing.T) {
	inner := &structuredError{code: "stale_ref", message: "ref vanished"}
	err := &exitcodes.CLIError{Code: exitcodes.ExitConflict, Kind: exitcodes.KindConflict, Message: "snapshot", Cause: inner}

	if data := ToolErrorData(err); data["code"] != "stale_ref" {
		t.Errorf("code = %v, want stale_ref", data["code"])
	}
}

type plainHintError struct{ message string }

func (e *plainHintError) Error() string { return e.message }
func (e *plainHintError) Hint() string  { return "shorter hint method" }

func TestToolErrorDataAcceptsShortHintMethod(t *testing.T) {
	data := ToolErrorData(&plainHintError{message: "boom"})
	if data["hint"] != "shorter hint method" {
		t.Errorf("hint = %v, want the Hint() value", data["hint"])
	}
}

// The end-to-end shape: a failing tools/call still returns an isError result
// with the prose intact, and the structured twin under the namespaced _meta
// key.
func TestToolsCallErrorCarriesStructuredMeta(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "fetch_url",
		Description: "Fetch a URL",
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			return nil, &structuredError{
				code:       "peer_denied",
				message:    "peer_denied: robots.txt forbids this path",
				retryable:  false,
				resumeHint: "pick a path robots.txt allows",
				details:    map[string]any{"robots_rule": "Disallow: /private"},
			}
		},
	})

	req := frameRequest(t, "tools/call", map[string]any{"name": "fetch_url", "arguments": map[string]any{}}, 7)
	resp := readResponse(t, runServer(t, srv, string(req)))
	if resp.Error != nil {
		t.Fatalf("unexpected JSON-RPC error: %v", resp.Error)
	}

	result := resp.Result.(map[string]any)
	if result["isError"] != true {
		t.Fatal("expected isError=true")
	}
	item := result["content"].([]any)[0].(map[string]any)
	if item["text"] != "peer_denied: robots.txt forbids this path" {
		t.Errorf("error text = %v, want the handler message unchanged", item["text"])
	}

	meta, ok := result["_meta"].(map[string]any)
	if !ok {
		t.Fatalf("result has no _meta: %#v", result)
	}
	data, ok := meta[ToolErrorMetaKey].(map[string]any)
	if !ok {
		t.Fatalf("_meta has no %q member: %#v", ToolErrorMetaKey, meta)
	}
	if data["code"] != "peer_denied" {
		t.Errorf("code = %v, want peer_denied", data["code"])
	}
	if data["retryable"] != false {
		t.Errorf("retryable = %v, want false", data["retryable"])
	}
	if data["resume_hint"] != "pick a path robots.txt allows" {
		t.Errorf("resume_hint = %v", data["resume_hint"])
	}
	details, ok := data["details"].(map[string]any)
	if !ok || details["robots_rule"] != "Disallow: /private" {
		t.Errorf("details = %#v, want the robots rule", data["details"])
	}
}

func TestToolsCallPlainErrorOmitsMeta(t *testing.T) {
	srv := New("test", "1.0")
	srv.RegisterTool(&Tool{
		Name:        "fail",
		Description: "Always fails",
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			return nil, errors.New("something went wrong")
		},
	})

	req := frameRequest(t, "tools/call", map[string]any{"name": "fail", "arguments": map[string]any{}}, 8)
	resp := readResponse(t, runServer(t, srv, string(req)))

	result := resp.Result.(map[string]any)
	if _, ok := result["_meta"]; ok {
		t.Errorf("plain error grew a _meta member: %#v", result["_meta"])
	}
}
