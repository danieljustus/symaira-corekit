package versionkit

import (
	"bytes"
	"encoding/json"
	"testing"
)

func TestJSONFieldNamesAreTheContract(t *testing.T) {
	data, err := New("symprint", "v0.1.0", 1).JSON()
	if err != nil {
		t.Fatal(err)
	}
	var raw map[string]any
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"tool", "version", "schema_version"} {
		if _, ok := raw[key]; !ok {
			t.Errorf("missing contract field %q in %s", key, data)
		}
	}
	if len(raw) != 3 {
		t.Errorf("payload grew beyond the contract: %s", data)
	}
}

func TestWriteEmitsSingleLine(t *testing.T) {
	var buf bytes.Buffer
	if err := New("symscope", "0.1.2", 2).Write(&buf); err != nil {
		t.Fatal(err)
	}
	want := `{"tool":"symscope","version":"0.1.2","schema_version":2}` + "\n"
	if buf.String() != want {
		t.Errorf("got %q, want %q", buf.String(), want)
	}
}

func TestStringMatchesAppkitFallbackParser(t *testing.T) {
	// appkit's ToolDetector fallback extracts the first semver-looking
	// token from "tool version" output — keep this shape stable.
	got := New("symseek", "v0.4.1", 1).String()
	if got != "symseek v0.4.1" {
		t.Errorf("got %q", got)
	}
}

func TestRoundTrip(t *testing.T) {
	data, _ := New("symfetch", "1.2.3", 4).JSON()
	var info Info
	if err := json.Unmarshal(data, &info); err != nil {
		t.Fatal(err)
	}
	if info != New("symfetch", "1.2.3", 4) {
		t.Errorf("round trip mismatch: %+v", info)
	}
}
