//nolint:gosec // G204: the exec hook re-execs the fixed test binary itself (os.Args[0]) for the helper-process pattern
package secretref

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestResolveValidation(t *testing.T) {
	if _, err := Resolve(context.Background(), "", ""); !errors.Is(err, ErrNoReference) {
		t.Fatalf("want ErrNoReference, got %v", err)
	}
	if _, err := Resolve(context.Background(), "env://SECRETREF_DEFINITELY_UNSET", ""); err == nil ||
		!strings.Contains(err.Error(), "not set") {
		t.Fatalf("want unset-env error, got %v", err)
	}
	if _, err := Resolve(context.Background(), "SECRETREF_DEFINITELY_UNSET", ""); err == nil {
		t.Fatalf("bare value must behave like env://, got %v", err)
	}
}

func TestResolveEnvPrecedence(t *testing.T) {
	t.Setenv("SECRETREF_TEST_ENV", "env-value")

	v, err := Resolve(context.Background(), "env://SECRETREF_TEST_ENV", "")
	if err != nil || v != "env-value" {
		t.Fatalf("env:// = (%q, %v)", v, err)
	}

	v, err = Resolve(context.Background(), "SECRETREF_TEST_ENV", "")
	if err != nil || v != "env-value" {
		t.Fatalf("bare name = (%q, %v)", v, err)
	}

	v, err = Resolve(context.Background(), "", "SECRETREF_TEST_ENV")
	if err != nil || v != "env-value" {
		t.Fatalf("empty ref falls back to envDefault = (%q, %v)", v, err)
	}
}

func TestResolveNilContext(t *testing.T) {
	t.Setenv("SECRETREF_TEST_ENV", "env-value")
	v, err := Resolve(nil, "env://SECRETREF_TEST_ENV", "") //nolint:staticcheck // exercising the nil-context fallback
	if err != nil || v != "env-value" {
		t.Fatalf("nil ctx = (%q, %v)", v, err)
	}
}

func TestResolveSymvaultPathValidationBeforeExec(t *testing.T) {
	cases := []struct {
		name string
		ref  string
	}{
		{name: "empty", ref: "symvault://"},
		{name: "leading dash", ref: "symvault://--config=/tmp/attacker.toml"},
		{name: "control character", ref: "symvault://secrets/\nkey"},
		{name: "null byte", ref: "symvault://secrets/\x00key"},
	}

	origExec, origLookup := execCommandContext, lookPath
	called := false
	execCommandContext = func(ctx context.Context, name string, args ...string) *exec.Cmd {
		called = true
		return exec.CommandContext(ctx, name, args...)
	}
	lookPath = func(string) (string, error) { return "/usr/bin/symvault", nil }
	defer func() { execCommandContext, lookPath = origExec, origLookup }()

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			called = false
			_, err := Resolve(context.Background(), tc.ref, "")
			if err == nil || !strings.Contains(err.Error(), "invalid symvault credential path") {
				t.Fatalf("want path-validation error, got %v", err)
			}
			if called {
				t.Error("exec must not run for an invalid path")
			}
		})
	}
}

func TestResolveSymvaultNotOnPath(t *testing.T) {
	origExec, origLookup := execCommandContext, lookPath
	called := false
	execCommandContext = func(ctx context.Context, name string, args ...string) *exec.Cmd {
		called = true
		return exec.CommandContext(ctx, name, args...)
	}
	lookPath = func(string) (string, error) { return "", exec.ErrNotFound }
	defer func() { execCommandContext, lookPath = origExec, origLookup }()

	_, err := Resolve(context.Background(), "symvault://secrets/x", "")
	if !errors.Is(err, ErrSymvaultNotFound) {
		t.Fatalf("want ErrSymvaultNotFound, got %v", err)
	}
	if called {
		t.Error("exec must not run when symvault is absent from PATH")
	}
}

// helperProcess re-executes the test binary in a fake-CLI mode so the real
// symvault/keychain exec path can be exercised platform-neutrally.
func TestHelperResolveSymvault(t *testing.T) {
	if os.Getenv("SECRETREF_HELPER_PROCESS") != "print" {
		t.Skip("helper subprocess target")
	}
	fmt.Println("secret-from-vault")
	os.Exit(0)
}

func TestResolveSymvaultExecSuccess(t *testing.T) {
	origExec, origLookup := execCommandContext, lookPath
	lookPath = func(string) (string, error) { return "/usr/bin/symvault", nil }
	var gotName string
	var gotArgs []string
	execCommandContext = func(ctx context.Context, name string, args ...string) *exec.Cmd {
		gotName = name
		gotArgs = append([]string(nil), args...)
		c := exec.CommandContext(ctx, os.Args[0], "-test.run=TestHelperResolveSymvault")
		c.Env = append(os.Environ(), "SECRETREF_HELPER_PROCESS=print")
		return c
	}
	defer func() { execCommandContext, lookPath = origExec, origLookup }()

	v, err := Resolve(context.Background(), "symvault://secrets/ai_key", "")
	if err != nil || v != "secret-from-vault" {
		t.Fatalf("symvault resolution = (%q, %v)", v, err)
	}
	if gotName != "symvault" || !reflect.DeepEqual(gotArgs, []string{"get", "--", "secrets/ai_key", "--print"}) {
		t.Errorf("symvault invocation = %q %q", gotName, gotArgs)
	}
}

func TestHelperResolveSymvaultFail(t *testing.T) {
	if os.Getenv("SECRETREF_HELPER_PROCESS") != "fail" {
		t.Skip("helper subprocess target")
	}
	fmt.Fprintln(os.Stdout, "resolved-secret-should-not-leak")
	fmt.Fprintln(os.Stderr, "entry not found")
	os.Exit(1)
}

func TestResolveSymvaultExecFailure(t *testing.T) {
	origExec, origLookup := execCommandContext, lookPath
	lookPath = func(string) (string, error) { return "/usr/bin/symvault", nil }
	execCommandContext = func(ctx context.Context, name string, args ...string) *exec.Cmd {
		c := exec.CommandContext(ctx, os.Args[0], "-test.run=TestHelperResolveSymvaultFail")
		c.Env = append(os.Environ(), "SECRETREF_HELPER_PROCESS=fail")
		return c
	}
	defer func() { execCommandContext, lookPath = origExec, origLookup }()

	_, err := Resolve(context.Background(), "symvault://secrets/missing", "")
	if err == nil || !strings.Contains(err.Error(), "entry not found") {
		t.Fatalf("vault stderr missing from error: %v", err)
	}
	if strings.Contains(err.Error(), "resolved-secret-should-not-leak") {
		t.Fatal("vault stdout credential leaked into error")
	}
}

func TestHelperSleep(t *testing.T) {
	if os.Getenv("SECRETREF_HELPER_PROCESS") != "sleep" {
		t.Skip("helper subprocess target")
	}
	time.Sleep(2 * time.Second)
}

func TestResolveSymvaultTimeoutIsDistinguishable(t *testing.T) {
	origExec, origLookup := execCommandContext, lookPath
	lookPath = func(string) (string, error) { return "/usr/bin/symvault", nil }
	execCommandContext = func(ctx context.Context, name string, args ...string) *exec.Cmd {
		c := exec.CommandContext(ctx, os.Args[0], "-test.run=TestHelperSleep")
		c.Env = append(os.Environ(), "SECRETREF_HELPER_PROCESS=sleep")
		return c
	}
	defer func() { execCommandContext, lookPath = origExec, origLookup }()

	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()

	_, err := Resolve(ctx, "symvault://secrets/x", "")
	if !errors.Is(err, ErrTimeout) {
		t.Fatalf("want ErrTimeout, got %v", err)
	}
}

func TestResolveSymvaultDefaultTimeoutAppliedWithoutCallerDeadline(t *testing.T) {
	origExec, origLookup, origTimeout := execCommandContext, lookPath, DefaultTimeout
	lookPath = func(string) (string, error) { return "/usr/bin/symvault", nil }
	execCommandContext = func(ctx context.Context, name string, args ...string) *exec.Cmd {
		c := exec.CommandContext(ctx, os.Args[0], "-test.run=TestHelperSleep")
		c.Env = append(os.Environ(), "SECRETREF_HELPER_PROCESS=sleep")
		return c
	}
	DefaultTimeout = 5 * time.Millisecond
	defer func() { execCommandContext, lookPath, DefaultTimeout = origExec, origLookup, origTimeout }()

	_, err := Resolve(context.Background(), "symvault://secrets/x", "")
	if !errors.Is(err, ErrTimeout) {
		t.Fatalf("want ErrTimeout from the default deadline, got %v", err)
	}
}

func TestResolveInvalidKeychainReference(t *testing.T) {
	_, err := Resolve(context.Background(), "keychain://service-only", "")
	if err == nil || !strings.Contains(err.Error(), "invalid keychain reference") {
		t.Fatalf("want invalid-keychain-reference error, got %v", err)
	}
}
