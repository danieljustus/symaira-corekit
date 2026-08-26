//nolint:gosec // G204: the subprocess executes go build/run with fixed arguments, never user input
package main

// Generator coverage (issue #183): main() is exercised end-to-end as a real
// subprocess — success regenerates providers.json byte-identically, and each
// failure path exits 1 with a diagnostic. This keeps the generator honest
// without refactoring entry-point code around os.Exit.

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func repoRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("Getwd: %v", err)
	}
	// This package lives at <root>/llmkit/gen.
	root := filepath.Dir(filepath.Dir(dir))
	if _, err := os.Stat(filepath.Join(root, "llmkit", "providers.json")); err != nil {
		t.Fatalf("repo root not detected from %q: %v", dir, err)
	}
	return root
}

func runGen(t *testing.T, dir string, stdout *os.File) (string, error) {
	t.Helper()
	genMain := filepath.Join(repoRoot(t), "llmkit", "gen", "main.go")
	cmd := exec.Command("go", "run", genMain)
	cmd.Dir = dir
	if stdout != nil {
		cmd.Stdout = stdout
	}
	out, err := cmd.CombinedOutput()
	return string(out), err
}

func TestGenerateMatchesEmbeddedRegistry(t *testing.T) {
	root := repoRoot(t)
	got, err := runGen(t, filepath.Join(root, "llmkit"), nil)
	if err != nil {
		t.Fatalf("generator failed: %v\n%s", err, got)
	}
	want, err := os.ReadFile(filepath.Join(root, "llmkit", "providers.json"))
	if err != nil {
		t.Fatalf("read providers.json: %v", err)
	}
	if strings.TrimSpace(got) != strings.TrimSpace(string(want)) {
		t.Error("go run ./gen output differs from llmkit/providers.json — regenerate with `go generate ./llmkit/`")
	}
}

func TestGenerateFailsWhenContractMissing(t *testing.T) {
	dir := t.TempDir() // no ../contracts above this directory
	out, err := runGen(t, dir, nil)
	if err == nil {
		t.Fatal("generator must fail when ../contracts/llm_providers.json is missing")
	}
	if !strings.Contains(out, "read contracts") {
		t.Errorf("stderr = %q, want read-contracts diagnostic", out)
	}
}

func TestGenerateFailsOnMalformedContract(t *testing.T) {
	base := t.TempDir()
	contractsDir := filepath.Join(base, "contracts")
	if err := os.MkdirAll(contractsDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(contractsDir, "llm_providers.json"), []byte("{not json"), 0o644); err != nil {
		t.Fatalf("write fixture: %v", err)
	}
	workDir := filepath.Join(base, "run")
	if err := os.MkdirAll(workDir, 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	out, err := runGen(t, workDir, nil)
	if err == nil {
		t.Fatal("generator must fail on malformed contract")
	}
	if !strings.Contains(out, "parse contracts") {
		t.Errorf("stderr = %q, want parse-contracts diagnostic", out)
	}
}

// The encoder failure path (main.go "encode:") is defensive dead code on
// Unix: Go re-raises SIGPIPE when a stdout write hits a broken pipe, so the
// process dies before the error branch runs. It is only reachable on Windows
// (ERROR_BROKEN_PIPE surfaces as a regular write error).
