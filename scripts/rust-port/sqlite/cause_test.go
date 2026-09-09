package main

import (
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"testing"
)

func TestPrivateWindowsMkdirCauseIsNarrow(t *testing.T) {
	dir := t.TempDir()
	file := filepath.Join(dir, "file")
	if err := os.WriteFile(file, []byte("regular file"), 0600); err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct{ op, path, message, want string }{
		{"mkdir", file, "path is not a regular file", "NotADirectory"},
		{"open", file, "path is not a regular file", ""},
		{"mkdir", dir, "path is not a regular file", ""},
		{"mkdir", file, "different failure", ""},
		{"mkdir", filepath.Join(dir, "absent"), "path is not a regular file", ""},
	} {
		got := errorCause(&fs.PathError{Op: tc.op, Path: tc.path, Err: errors.New(tc.message)})
		if tc.want == "" {
			if got["type"] != "unclassified" {
				t.Fatalf("unexpected classification: %v", got)
			}
		} else if got["kind"] != tc.want {
			t.Fatalf("got %v, want %s", got, tc.want)
		}
	}
}
