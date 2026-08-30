// Contract test for the shared MCP tool-annotation hints.
// mcp_tool_annotations.json is the cross-language source of truth the Go
// (mcpserver) and eventually the Swift (SymairaProviderKit) tool layers are
// specified against; this test asserts mcpserver.ToolAnnotations has not
// drifted from the documented contract.
package contracts

import (
	"encoding/json"
	"os"
	"reflect"
	"strings"
	"testing"

	"github.com/danieljustus/symaira-corekit/mcpserver"
)

type mcpHint struct {
	WireName                 string `json:"wire_name"`
	Type                     string `json:"type"`
	Meaning                  string `json:"meaning"`
	MustBeDeclaredExplicitly bool   `json:"must_be_declared_explicitly"`
}

type mcpToolAnnotationsContract struct {
	SchemaVersion           int       `json:"schema_version"`
	Hints                   []mcpHint `json:"hints"`
	ExplicitDeclarationRule string    `json:"explicit_declaration_rule"`
	CanonicalImplementation string    `json:"canonical_implementation"`
}

func loadMCPToolAnnotations(t *testing.T) mcpToolAnnotationsContract {
	t.Helper()
	raw, err := os.ReadFile("mcp_tool_annotations.json")
	if err != nil {
		t.Fatalf("read mcp_tool_annotations.json: %v", err)
	}
	var c mcpToolAnnotationsContract
	if err := json.Unmarshal(raw, &c); err != nil {
		t.Fatalf("parse mcp_tool_annotations.json: %v", err)
	}
	return c
}

// jsonTagName returns the wire name from a struct tag, dropping options like
// ",omitempty".
func jsonTagName(tag string) string {
	name, _, _ := strings.Cut(tag, ",")
	return name
}

func TestMCPToolAnnotationsMatchImplementation(t *testing.T) {
	c := loadMCPToolAnnotations(t)

	want := map[string]bool{}
	for _, h := range c.Hints {
		if h.Type != "boolean" {
			t.Errorf("hint %q has non-boolean type %q; ToolAnnotations hints are all bool", h.WireName, h.Type)
		}
		want[h.WireName] = true
	}

	got := map[string]bool{}
	typ := reflect.TypeOf(mcpserver.ToolAnnotations{})
	for i := 0; i < typ.NumField(); i++ {
		f := typ.Field(i)
		if f.Type.Kind() != reflect.Bool {
			continue // Title and any future non-hint field are not hints.
		}
		got[jsonTagName(f.Tag.Get("json"))] = true
	}

	if !reflect.DeepEqual(got, want) {
		t.Errorf("mcpserver.ToolAnnotations bool fields = %v, contract declares %v", got, want)
	}
}

func TestMCPToolAnnotationsExplicitDeclarationRuleNamesReadOnlyHint(t *testing.T) {
	c := loadMCPToolAnnotations(t)
	found := false
	for _, h := range c.Hints {
		if h.WireName == "readOnlyHint" {
			found = true
			if !h.MustBeDeclaredExplicitly {
				t.Error("readOnlyHint must be marked must_be_declared_explicitly")
			}
		} else if h.MustBeDeclaredExplicitly {
			t.Errorf("hint %q must not require explicit declaration; only readOnlyHint does", h.WireName)
		}
	}
	if !found {
		t.Fatal("contract is missing the readOnlyHint entry")
	}
	if c.ExplicitDeclarationRule == "" {
		t.Error("contract missing explicit_declaration_rule")
	}
}

func TestMCPToolAnnotationsCanonicalImplementationNamed(t *testing.T) {
	c := loadMCPToolAnnotations(t)
	if c.CanonicalImplementation != "corekit/mcpserver.ToolAnnotations" {
		t.Errorf("canonical_implementation = %q, want %q", c.CanonicalImplementation, "corekit/mcpserver.ToolAnnotations")
	}
}
