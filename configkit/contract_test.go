package configkit

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type configPathsFixture struct {
	ConfigPathPattern string `json:"config_path_pattern"`
	ConfigFileFormat  string `json:"config_file_format"`
}

// TestDefaultPathMatchesContractFixture asserts DefaultPath produces the
// "~/.config/<app>/config.toml" shape the fixture documents, and that the
// documented format extension (toml) is what DefaultPath actually appends.
func TestDefaultPathMatchesContractFixture(t *testing.T) {
	raw, err := os.ReadFile("../contracts/config_paths.json")
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var f configPathsFixture
	if err := json.Unmarshal(raw, &f); err != nil {
		t.Fatalf("parse fixture: %v", err)
	}

	got := DefaultPath("symfetch")

	if !strings.HasSuffix(got, filepath.Join(".config", "symfetch", "config."+f.ConfigFileFormat)) {
		t.Fatalf("DefaultPath(%q) = %q, does not match fixture pattern %q with format %q",
			"symfetch", got, f.ConfigPathPattern, f.ConfigFileFormat)
	}
}
