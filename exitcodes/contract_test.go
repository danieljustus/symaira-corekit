package exitcodes

import (
	"encoding/json"
	"os"
	"testing"
)

type exitCodeFixture struct {
	Code    int    `json:"code"`
	Name    string `json:"name"`
	Meaning string `json:"meaning"`
}

// TestExitCodesMatchContractFixture asserts that every entry in
// contracts/exit_codes.json matches the corresponding typed constant here.
// The fixture is the cross-language source of truth documented in
// docs/cross-language-conventions.md; a mismatch here means the doc or the
// Swift/Python consumers have drifted from what this package actually does.
func TestExitCodesMatchContractFixture(t *testing.T) {
	raw, err := os.ReadFile("../contracts/exit_codes.json")
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}

	var fixtures []exitCodeFixture
	if err := json.Unmarshal(raw, &fixtures); err != nil {
		t.Fatalf("parse fixture: %v", err)
	}

	byName := map[string]ExitCode{
		"ExitOK":          ExitOK,
		"ExitGeneric":     ExitGeneric,
		"ExitNoInput":     ExitNoInput,
		"ExitNoAuth":      ExitNoAuth,
		"ExitForbidden":   ExitForbidden,
		"ExitNotFound":    ExitNotFound,
		"ExitConflict":    ExitConflict,
		"ExitSoftware":    ExitSoftware,
		"ExitData":        ExitData,
		"ExitConfig":      ExitConfig,
		"ExitInterrupted": ExitInterrupted,
	}

	if len(fixtures) != len(byName) {
		t.Fatalf("fixture has %d entries, package declares %d constants", len(fixtures), len(byName))
	}

	seen := make(map[string]bool, len(fixtures))
	for _, f := range fixtures {
		seen[f.Name] = true
		want, ok := byName[f.Name]
		if !ok {
			t.Errorf("fixture names %q, which has no matching ExitCode constant", f.Name)
			continue
		}
		if int(want) != f.Code {
			t.Errorf("%s = %d in package, fixture claims %d", f.Name, want, f.Code)
		}
	}

	for name := range byName {
		if !seen[name] {
			t.Errorf("constant %s has no entry in contracts/exit_codes.json", name)
		}
	}
}
