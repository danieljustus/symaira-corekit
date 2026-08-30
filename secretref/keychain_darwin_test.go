//go:build darwin

//nolint:gosec // G104/G204: ignored write errors and the fixed-binary exec re-exec are intentional in this helper-process test pattern
package secretref

import (
	"context"
	"errors"
	"os"
	"os/exec"
	"reflect"
	"strings"
	"testing"
)

func TestHelperResolveKeychain(t *testing.T) {
	if os.Getenv("SECRETREF_HELPER_PROCESS") != "print" {
		t.Skip("helper subprocess target")
	}
	os.Stdout.WriteString("secret-from-keychain\n")
	os.Exit(0)
}

func TestResolveKeychainExecSuccess(t *testing.T) {
	orig := execCommandContext
	var gotName string
	var gotArgs []string
	execCommandContext = func(ctx context.Context, name string, args ...string) *exec.Cmd {
		gotName = name
		gotArgs = append([]string(nil), args...)
		c := exec.CommandContext(ctx, os.Args[0], "-test.run=TestHelperResolveKeychain")
		c.Env = append(os.Environ(), "SECRETREF_HELPER_PROCESS=print")
		return c
	}
	defer func() { execCommandContext = orig }()

	v, err := Resolve(context.Background(), "keychain://symaira/api_key", "")
	if err != nil || v != "secret-from-keychain" {
		t.Fatalf("keychain resolution = (%q, %v)", v, err)
	}
	want := []string{"find-generic-password", "-w", "-s", "symaira", "-a", "api_key"}
	if gotName != "security" || !reflect.DeepEqual(gotArgs, want) {
		t.Errorf("keychain invocation = %q %q", gotName, gotArgs)
	}
}

func TestHelperResolveKeychainFail(t *testing.T) {
	if os.Getenv("SECRETREF_HELPER_PROCESS") != "fail" {
		t.Skip("helper subprocess target")
	}
	os.Stdout.WriteString("resolved-secret-should-not-leak\n")
	os.Stderr.WriteString("The specified item could not be found in the keychain.\n")
	os.Exit(44)
}

func TestResolveKeychainExecFailure(t *testing.T) {
	orig := execCommandContext
	execCommandContext = func(ctx context.Context, name string, args ...string) *exec.Cmd {
		c := exec.CommandContext(ctx, os.Args[0], "-test.run=TestHelperResolveKeychainFail")
		c.Env = append(os.Environ(), "SECRETREF_HELPER_PROCESS=fail")
		return c
	}
	defer func() { execCommandContext = orig }()

	_, err := Resolve(context.Background(), "keychain://symaira/missing", "")
	if err == nil || !strings.Contains(err.Error(), "could not be found") {
		t.Fatalf("keychain stderr missing from error: %v", err)
	}
	if strings.Contains(err.Error(), "resolved-secret-should-not-leak") {
		t.Fatal("keychain stdout credential leaked into error")
	}
}

func TestResolveKeychainUnsupportedNotReturnedOnDarwin(t *testing.T) {
	orig := execCommandContext
	execCommandContext = func(ctx context.Context, name string, args ...string) *exec.Cmd {
		c := exec.CommandContext(ctx, os.Args[0], "-test.run=TestHelperResolveKeychain")
		c.Env = append(os.Environ(), "SECRETREF_HELPER_PROCESS=print")
		return c
	}
	defer func() { execCommandContext = orig }()

	_, err := Resolve(context.Background(), "keychain://symaira/api_key", "")
	if errors.Is(err, ErrKeychainUnsupported) {
		t.Fatal("keychain must be supported on darwin")
	}
}
