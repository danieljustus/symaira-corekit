package exitcodes

import (
	"encoding/json"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"testing"
)

type exitCodeFixture struct {
	Code    int    `json:"code"`
	Name    string `json:"name"`
	Meaning string `json:"meaning"`
}

func repositoryFile(t *testing.T, name string) string {
	t.Helper()

	_, source, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("locate contract test source")
	}
	return filepath.Join(filepath.Dir(source), "..", name)
}

func readRepositoryFile(t *testing.T, name string) []byte {
	t.Helper()

	raw, err := os.ReadFile(repositoryFile(t, name))
	if err != nil {
		t.Fatalf("read %s: %v", name, err)
	}
	return []byte(strings.ReplaceAll(string(raw), "\r\n", "\n"))
}

// TestExitCodesMatchContractFixture asserts that every entry in
// contracts/exit_codes.json matches the corresponding typed constant here.
// The fixture is the cross-language source of truth documented in
// docs/cross-language-conventions.md; a mismatch here means the doc or the
// Swift/Python consumers have drifted from what this package actually does.
func TestExitCodesMatchContractFixture(t *testing.T) {
	raw := readRepositoryFile(t, "contracts/exit_codes.json")

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

func TestREADMEExitCodesMatchExports(t *testing.T) {
	readme := string(readRepositoryFile(t, "README.md"))
	var row string
	for _, line := range strings.Split(readme, "\n") {
		if strings.HasPrefix(line, "| `exitcodes` |") {
			if row != "" {
				t.Fatal("README package table contains multiple exitcodes rows")
			}
			row = line
		}
	}
	if row == "" {
		t.Fatal("README package table has no exitcodes row")
	}

	names := regexp.MustCompile(`\bExit[A-Z][A-Za-z0-9]*\b`).FindAllString(row, -1)
	if len(names) == 0 {
		t.Fatal("README exitcodes row names no exit codes")
	}

	source, err := parser.ParseFile(token.NewFileSet(), repositoryFile(t, "exitcodes/exitcodes.go"), nil, 0)
	if err != nil {
		t.Fatalf("parse exitcodes source: %v", err)
	}

	exportedConstants := make(map[string]bool)
	for _, decl := range source.Decls {
		gen, ok := decl.(*ast.GenDecl)
		if !ok || gen.Tok != token.CONST {
			continue
		}
		for _, spec := range gen.Specs {
			values, ok := spec.(*ast.ValueSpec)
			if !ok {
				continue
			}
			for _, name := range values.Names {
				if ast.IsExported(name.Name) {
					exportedConstants[name.Name] = true
				}
			}
		}
	}

	for _, name := range names {
		if !exportedConstants[name] {
			t.Errorf("README exitcodes row names %s, but exitcodes/exitcodes.go does not export it", name)
		}
	}
}
