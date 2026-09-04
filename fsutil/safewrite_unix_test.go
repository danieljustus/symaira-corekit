//go:build !windows

package fsutil

import (
	"errors"
	"os"
	"path/filepath"
	"syscall"
	"testing"
)

func TestSafeRemoveClosesValidatedDescriptorOnce(t *testing.T) {
	path := filepath.Join(t.TempDir(), "secret.txt")
	if err := os.WriteFile(path, []byte("secret"), 0o600); err != nil {
		t.Fatalf("write fixture: %v", err)
	}

	closeCalls := 0
	err := safeRemove(path, func(gotPath string) error {
		if closeCalls != 1 {
			t.Fatalf("close calls before remove = %d, want 1", closeCalls)
		}
		return os.Remove(gotPath)
	}, func(fd int) error {
		closeCalls++
		return syscall.Close(fd)
	})
	if err != nil {
		t.Fatalf("safeRemove: %v", err)
	}
	if closeCalls != 1 {
		t.Fatalf("close calls = %d, want 1", closeCalls)
	}
}

func TestSafeRemoveDoesNotRetryFailedClose(t *testing.T) {
	path := filepath.Join(t.TempDir(), "secret.txt")
	if err := os.WriteFile(path, []byte("secret"), 0o600); err != nil {
		t.Fatalf("write fixture: %v", err)
	}

	closeErr := errors.New("close failed")
	closeCalls := 0
	removeCalled := false
	err := safeRemove(path, func(string) error {
		removeCalled = true
		return nil
	}, func(fd int) error {
		closeCalls++
		if closeCalls == 1 {
			_ = syscall.Close(fd)
		}
		return closeErr
	})
	if !errors.Is(err, closeErr) {
		t.Fatalf("safeRemove error = %v, want %v", err, closeErr)
	}
	if closeCalls != 1 {
		t.Fatalf("close calls = %d, want 1", closeCalls)
	}
	if removeCalled {
		t.Fatal("remove called after descriptor close failed")
	}
}
