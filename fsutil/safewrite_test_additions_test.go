//go:build !windows

//nolint:gosec
package fsutil

import (
	"errors"
	"os"
	"path/filepath"
	"syscall"
	"testing"
)

func TestSafeWriteFile_Success(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "out.txt")
	if err := SafeWriteFile(path, []byte("payload"), 0600); err != nil {
		t.Fatalf("SafeWriteFile: %v", err)
	}
	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != "payload" {
		t.Fatalf("content = %q, want payload", got)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0600 {
		t.Fatalf("mode = %v, want 0600", info.Mode().Perm())
	}
}

func TestSafeWriteFile_NonexistentDir(t *testing.T) {
	path := filepath.Join(t.TempDir(), "missing", "out.txt")
	err := SafeWriteFile(path, []byte("x"), 0600)
	if err == nil {
		t.Fatal("SafeWriteFile in a missing directory = nil, want error")
	}
	var pathErr *os.PathError
	if !errors.As(err, &pathErr) || pathErr.Op != "open" {
		t.Fatalf("error = %v, want open PathError", err)
	}
}

func TestSafeWriteFile_DirectoryTarget(t *testing.T) {
	dir := t.TempDir()
	err := SafeWriteFile(dir, []byte("x"), 0600)
	if err == nil {
		t.Fatal("SafeWriteFile on a directory = nil, want error")
	}
}

func TestSafeWriteFile_NonRegularFile(t *testing.T) {
	// A FIFO opens successfully O_WRONLY but is not a regular file; the
	// hardening must reject it with ENOTDIR before writing.
	fifo := filepath.Join(t.TempDir(), "pipe")
	if err := syscall.Mkfifo(fifo, 0600); err != nil {
		t.Fatalf("mkfifo: %v", err)
	}
	reader, err := os.OpenFile(fifo, os.O_RDONLY|syscall.O_NONBLOCK, 0)
	if err != nil {
		t.Fatalf("open fifo reader: %v", err)
	}
	defer reader.Close()

	err = SafeWriteFile(fifo, []byte("x"), 0600)
	if err == nil {
		t.Fatal("SafeWriteFile on a FIFO = nil, want error")
	}
	var pathErr *os.PathError
	if !errors.As(err, &pathErr) || !errors.Is(pathErr.Err, syscall.ENOTDIR) {
		t.Fatalf("error = %v, want ENOTDIR PathError", err)
	}
}

func TestSafeRemove_NonRegularFile(t *testing.T) {
	fifo := filepath.Join(t.TempDir(), "pipe")
	if err := syscall.Mkfifo(fifo, 0600); err != nil {
		t.Fatalf("mkfifo: %v", err)
	}
	// SafeRemove opens O_RDONLY without O_NONBLOCK, which blocks on a
	// FIFO until a writer exists; hold a reader and a writer open so
	// both the blocking open and the nonblocking writer open succeed.
	reader, err := os.OpenFile(fifo, os.O_RDONLY|syscall.O_NONBLOCK, 0)
	if err != nil {
		t.Fatalf("open fifo reader: %v", err)
	}
	defer reader.Close()
	writer, err := os.OpenFile(fifo, os.O_WRONLY|syscall.O_NONBLOCK, 0)
	if err != nil {
		t.Fatalf("open fifo writer: %v", err)
	}
	defer writer.Close()

	err = SafeRemove(fifo)
	if err == nil {
		t.Fatal("SafeRemove on a FIFO = nil, want error")
	}
	var pathErr *os.PathError
	if !errors.As(err, &pathErr) || !errors.Is(pathErr.Err, syscall.ENOTDIR) {
		t.Fatalf("error = %v, want ENOTDIR PathError", err)
	}
}

func TestSafeMkdirAll_RejectsUserSymlink(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "real")
	if err := os.MkdirAll(target, 0755); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(dir, "link")
	if err := os.Symlink(target, link); err != nil {
		t.Fatalf("symlink: %v", err)
	}

	err := SafeMkdirAll(filepath.Join(link, "child"), 0755)
	if err == nil {
		t.Fatal("SafeMkdirAll through a user-owned symlink = nil, want error")
	}
	var pathErr *os.PathError
	if !errors.As(err, &pathErr) || !errors.Is(pathErr.Err, syscall.ELOOP) {
		t.Fatalf("error = %v, want ELOOP PathError", err)
	}
}

func TestSafeMkdirAll_ReadOnlyParent(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("running as root; permission checks are meaningless")
	}
	parent := t.TempDir()
	if err := os.Chmod(parent, 0500); err != nil {
		t.Fatal(err)
	}
	defer os.Chmod(parent, 0700)

	err := SafeMkdirAll(filepath.Join(parent, "child"), 0755)
	if err == nil {
		t.Fatal("SafeMkdirAll under a read-only parent = nil, want error")
	}
}

func TestAtomicWriteFile_RenameToExistingDir(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "target")
	if err := os.Mkdir(target, 0755); err != nil {
		t.Fatal(err)
	}

	err := AtomicWriteFile(target, []byte("x"), 0644)
	if err == nil {
		t.Fatal("AtomicWriteFile onto a directory = nil, want error")
	}

	// The temporary file must have been cleaned up.
	leftovers, globErr := filepath.Glob(filepath.Join(dir, "target.tmp-*"))
	if globErr != nil {
		t.Fatal(globErr)
	}
	if len(leftovers) != 0 {
		t.Fatalf("leftover temp files: %v", leftovers)
	}
}

func TestWriteTempThenRename_CreateTempError(t *testing.T) {
	path := filepath.Join(t.TempDir(), "missing", "out.txt")
	err := writeTempThenRename(path, []byte("x"), 0644, os.Rename)
	if err == nil {
		t.Fatal("writeTempThenRename in a missing directory = nil, want error")
	}
}

func TestWriteTempThenRename_FailingRename(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "out.txt")
	boom := errors.New("rename boom")
	err := writeTempThenRename(path, []byte("x"), 0644, func(_, _ string) error { return boom })
	if !errors.Is(err, boom) {
		t.Fatalf("error = %v, want the rename error", err)
	}
	leftovers, globErr := filepath.Glob(filepath.Join(dir, "out.txt.tmp-*"))
	if globErr != nil {
		t.Fatal(globErr)
	}
	if len(leftovers) != 0 {
		t.Fatalf("temp file not cleaned up after failed rename: %v", leftovers)
	}
}
