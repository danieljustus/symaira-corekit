// Contract test for the structured MCP tool-error metadata.
// mcp_tool_errors.json is the cross-language source of truth for the object a
// failed tools/call publishes under the tool result's _meta; this test asserts
// the Go implementation (mcpserver.ToolErrorData) still produces exactly the
// documented field set, with the documented omission rules.
package contracts

import (
	"encoding/json"
	"errors"
	"os"
	"sort"
	"testing"

	"github.com/danieljustus/symaira-corekit/mcpserver"
)

type mcpToolErrorField struct {
	WireName     string `json:"wire_name"`
	Type         string `json:"type"`
	SourceMethod string `json:"source_method"`
	Meaning      string `json:"meaning"`
	OmittedWhen  string `json:"omitted_when"`
}

type mcpToolErrorsContract struct {
	SchemaVersion           int                 `json:"schema_version"`
	Transport               string              `json:"transport"`
	MetaKey                 string              `json:"meta_key"`
	KeyCase                 string              `json:"key_case"`
	OmitWhenEmpty           bool                `json:"omit_when_empty"`
	Fields                  []mcpToolErrorField `json:"fields"`
	Resolution              string              `json:"resolution"`
	CanonicalImplementation string              `json:"canonical_implementation"`
}

func loadMCPToolErrors(t *testing.T) mcpToolErrorsContract {
	t.Helper()
	raw, err := os.ReadFile("mcp_tool_errors.json")
	if err != nil {
		t.Fatalf("read mcp_tool_errors.json: %v", err)
	}
	var c mcpToolErrorsContract
	if err := json.Unmarshal(raw, &c); err != nil {
		t.Fatalf("parse mcp_tool_errors.json: %v", err)
	}
	return c
}

// fullyDescribedError implements every optional interface the contract names,
// so ToolErrorData must emit every documented field and nothing else.
type fullyDescribedError struct{}

func (fullyDescribedError) Error() string              { return "peer_denied: robots.txt forbids this path" }
func (fullyDescribedError) ErrorCode() string          { return "peer_denied" }
func (fullyDescribedError) RetryableError() bool       { return false }
func (fullyDescribedError) RequiresConfirmation() bool { return false }
func (fullyDescribedError) ResumeGuidance() string     { return "pick an allowed path" }
func (fullyDescribedError) ErrorHint() string          { return "robots.txt disallows /private" }
func (fullyDescribedError) ErrorDetails() map[string]any {
	return map[string]any{"rule": "Disallow: /private"}
}

func TestMCPToolErrorsMatchImplementation(t *testing.T) {
	c := loadMCPToolErrors(t)

	want := make([]string, 0, len(c.Fields))
	for _, f := range c.Fields {
		want = append(want, f.WireName)
	}
	sort.Strings(want)

	data := mcpserver.ToolErrorData(fullyDescribedError{})
	got := make([]string, 0, len(data))
	for name := range data {
		got = append(got, name)
	}
	sort.Strings(got)

	if len(got) != len(want) {
		t.Fatalf("ToolErrorData fields = %v, contract declares %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("ToolErrorData fields = %v, contract declares %v", got, want)
			break
		}
	}
}

func TestMCPToolErrorsOmitWhenEmptyHolds(t *testing.T) {
	c := loadMCPToolErrors(t)
	if !c.OmitWhenEmpty {
		t.Fatal("contract must declare omit_when_empty: an error with nothing to add may not change the wire format")
	}
	if data := mcpserver.ToolErrorData(errors.New("plain")); data != nil {
		t.Errorf("ToolErrorData(plain error) = %v, want nil", data)
	}
}

func TestMCPToolErrorsMetaKeyMatchesImplementation(t *testing.T) {
	c := loadMCPToolErrors(t)
	if c.MetaKey != mcpserver.ToolErrorMetaKey {
		t.Errorf("meta_key = %q, mcpserver.ToolErrorMetaKey = %q", c.MetaKey, mcpserver.ToolErrorMetaKey)
	}
	if c.CanonicalImplementation != "corekit/mcpserver.ToolErrorData" {
		t.Errorf("canonical_implementation = %q, want %q", c.CanonicalImplementation, "corekit/mcpserver.ToolErrorData")
	}
}

// The key case is not decoration: contracts/json_encoding.json makes
// snake_case the rule for tool-defined payloads, and this object is one.
func TestMCPToolErrorsUseSnakeCaseKeys(t *testing.T) {
	c := loadMCPToolErrors(t)
	if c.KeyCase != "snake_case" {
		t.Errorf("key_case = %q, want snake_case", c.KeyCase)
	}
	for _, f := range c.Fields {
		for _, r := range f.WireName {
			if r >= 'A' && r <= 'Z' {
				t.Errorf("field %q is not snake_case", f.WireName)
				break
			}
		}
		if f.SourceMethod == "" || f.Meaning == "" || f.OmittedWhen == "" {
			t.Errorf("field %q is missing source_method, meaning or omitted_when", f.WireName)
		}
	}
}
