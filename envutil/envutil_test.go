package envutil

import (
	"os"
	"testing"
)

func TestGetenv_PrimaryFound(t *testing.T) {
	t.Setenv("TEST_PRIMARY_KEY", "primary-val")
	got := Getenv("TEST_PRIMARY_KEY", "TEST_LEGACY_KEY")
	if got != "primary-val" {
		t.Errorf("Getenv() = %q, want %q", got, "primary-val")
	}
}

func TestGetenv_PrimaryMissing_LegacyFound(t *testing.T) {
	t.Setenv("TEST_LEGACY_KEY2", "legacy-val")
	got := Getenv("TEST_PRIMARY_MISSING", "TEST_LEGACY_KEY2")
	if got != "legacy-val" {
		t.Errorf("Getenv() = %q, want %q", got, "legacy-val")
	}
}

func TestGetenv_BothMissing(t *testing.T) {
	os.Unsetenv("TEST_NEITHER_A")
	os.Unsetenv("TEST_NEITHER_B")
	got := Getenv("TEST_NEITHER_A", "TEST_NEITHER_B")
	if got != "" {
		t.Errorf("Getenv() = %q, want empty string", got)
	}
}

func TestGetenv_NoLegacy(t *testing.T) {
	t.Setenv("TEST_NOLEGACY", "val")
	got := Getenv("TEST_NOLEGACY")
	if got != "val" {
		t.Errorf("Getenv() = %q, want %q", got, "val")
	}
}

func TestGetenv_NoLegacyMissing(t *testing.T) {
	os.Unsetenv("TEST_NOLEGACY_MISS")
	got := Getenv("TEST_NOLEGACY_MISS")
	if got != "" {
		t.Errorf("Getenv() = %q, want empty string", got)
	}
}
