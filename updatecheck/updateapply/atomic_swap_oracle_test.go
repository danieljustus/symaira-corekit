package updateapply

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sort"
	"testing"
)

// TestAtomicSwapOracle records the unexported swap seam for the Rust port.
// Ordinary package tests skip recording; the differential runner sets the path.
func TestAtomicSwapOracle(t *testing.T) {
	output := os.Getenv("COREKIT_SWAP_ORACLE_OUT")
	if output == "" {
		t.Skip("recorded by update-swap-differential.py")
	}
	type input struct {
		ID      string `json:"id"`
		Initial string `json:"initial"`
		Source  string `json:"source"`
		Backup  string `json:"backup"`
		Reject  bool   `json:"reject"`
	}
	type observation struct {
		Error               bool     `json:"error"`
		TargetExists        bool     `json:"target_exists"`
		TargetContent       string   `json:"target_content"`
		SourceExists        bool     `json:"source_exists"`
		BackupExists        bool     `json:"backup_exists"`
		ValidatorSawTarget  bool     `json:"validator_saw_target"`
		ValidatorSawBackup  bool     `json:"validator_saw_backup"`
		ValidatorSawContent string   `json:"validator_saw_content"`
		RemainingFileNames  []string `json:"remaining_file_names"`
	}
	cases := []input{
		{ID: "missing-source", Initial: "old-binary"},
		{ID: "validation-rollback", Initial: "old-binary", Source: "invalid-binary", Reject: true},
		{ID: "validation-first-install", Source: "invalid-binary", Reject: true},
		{ID: "preexisting-backup", Initial: "old-binary", Source: "new-binary", Backup: "stale-backup"},
	}
	results := make([]struct {
		Input       input       `json:"input"`
		Observation observation `json:"observation"`
	}, 0, len(cases))
	for _, test := range cases {
		root := t.TempDir()
		target, source := filepath.Join(root, "mytool"), filepath.Join(root, "staged")
		if test.Initial != "" {
			if err := os.WriteFile(target, []byte(test.Initial), 0o600); err != nil {
				t.Fatal(err)
			}
		}
		if test.Source != "" {
			if err := os.WriteFile(source, []byte(test.Source), 0o600); err != nil {
				t.Fatal(err)
			}
		}
		if test.Backup != "" {
			if err := os.WriteFile(target+".bak", []byte(test.Backup), 0o600); err != nil {
				t.Fatal(err)
			}
		}
		entry := observation{RemainingFileNames: []string{}}
		var validator BinaryValidator
		if test.Reject {
			validator = func(path string) error {
				entry.ValidatorSawTarget = path == target
				entry.ValidatorSawBackup = fileExists(target + ".bak")
				body, err := os.ReadFile(path) //nolint:gosec // private temp-root target
				if err != nil {
					t.Fatal(err)
				}
				entry.ValidatorSawContent = string(body)
				return errors.New("reject installed binary")
			}
		}
		err := atomicSwap(source, target, validator)
		entry.Error = err != nil
		if entry.Error != (test.Reject || test.Source == "") {
			t.Fatalf("%s: unexpected swap error: %v", test.ID, err)
		}
		if body, readErr := os.ReadFile(target); readErr == nil { //nolint:gosec // private temp-root target
			entry.TargetExists, entry.TargetContent = true, string(body)
		} else if !os.IsNotExist(readErr) {
			t.Fatal(readErr)
		}
		entry.SourceExists = fileExists(source)
		entry.BackupExists = fileExists(target + ".bak")
		entries, err := os.ReadDir(root)
		if err != nil {
			t.Fatal(err)
		}
		for _, file := range entries {
			entry.RemainingFileNames = append(entry.RemainingFileNames, file.Name())
		}
		sort.Strings(entry.RemainingFileNames)
		results = append(results, struct {
			Input       input       `json:"input"`
			Observation observation `json:"observation"`
		}{Input: test, Observation: entry})
	}
	data, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(output, append(data, '\n'), 0o600); err != nil { //nolint:gosec // runner-owned output path
		t.Fatal(err)
	}
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
