package fsutil

import (
	"os"
	"path/filepath"
	"testing"
)

func TestAtomicWriteFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.txt")
	data := []byte("hello world")

	if err := AtomicWriteFile(path, data, 0644); err != nil {
		t.Fatalf("AtomicWriteFile: %v", err)
	}

	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	if string(got) != string(data) {
		t.Errorf("content = %q, want %q", got, data)
	}

	info, err := os.Stat(path)
	if err != nil {
		t.Fatalf("Stat: %v", err)
	}
	if info.Mode().Perm() != 0644 {
		t.Errorf("mode = %v, want 0644", info.Mode().Perm())
	}
}

func TestAtomicWriteFile_Overwrite(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.txt")

	if err := AtomicWriteFile(path, []byte("first"), 0644); err != nil {
		t.Fatalf("first write: %v", err)
	}
	if err := AtomicWriteFile(path, []byte("second"), 0644); err != nil {
		t.Fatalf("second write: %v", err)
	}

	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("ReadFile: %v", err)
	}
	if string(got) != "second" {
		t.Errorf("content = %q, want %q", got, "second")
	}
}

func TestSafeRemove(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.txt")
	if err := os.WriteFile(path, []byte("data"), 0644); err != nil {
		t.Fatal(err)
	}

	if err := SafeRemove(path); err != nil {
		t.Fatalf("SafeRemove: %v", err)
	}

	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Errorf("file still exists after SafeRemove")
	}
}

func TestSafeRemove_Nonexistent(t *testing.T) {
	err := SafeRemove("/nonexistent/path/file.txt")
	if err == nil {
		t.Error("SafeRemove on nonexistent path = nil, want error")
	}
}

func TestSafeMkdirAll(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "a", "b", "c")

	if err := SafeMkdirAll(path, 0755); err != nil {
		t.Fatalf("SafeMkdirAll: %v", err)
	}

	info, err := os.Stat(path)
	if err != nil {
		t.Fatalf("Stat: %v", err)
	}
	if !info.IsDir() {
		t.Errorf("%v is not a directory", path)
	}
}

func TestSafeMkdirAll_Exists(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "existing")

	if err := os.MkdirAll(path, 0755); err != nil {
		t.Fatal(err)
	}

	if err := SafeMkdirAll(path, 0755); err != nil {
		t.Fatalf("SafeMkdirAll on existing dir: %v", err)
	}
}

func TestSafeMkdirAll_FileAsParent(t *testing.T) {
	dir := t.TempDir()
	blocker := filepath.Join(dir, "blocker")
	if err := os.WriteFile(blocker, []byte("x"), 0644); err != nil {
		t.Fatal(err)
	}

	path := filepath.Join(blocker, "child")
	err := SafeMkdirAll(path, 0755)
	if err == nil {
		t.Error("SafeMkdirAll through a file = nil, want error")
	}
}
