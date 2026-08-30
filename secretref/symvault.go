package secretref

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"strings"
	"time"
	"unicode"
)

// DefaultTimeout bounds every symvault/keychain subprocess call when the
// caller's context carries no deadline of its own. It is a var (not a
// const) so tests can shrink it instead of sleeping for the real duration.
var DefaultTimeout = 5 * time.Second

// execCommandContext and lookPath are small indirections so tests can
// replace the subprocess path without touching the real symvault/security
// binaries.
var (
	//nolint:gosec // G204: name is always the fixed "symvault"/"security" binary; only the trailing args vary
	execCommandContext = func(ctx context.Context, name string, args ...string) *exec.Cmd {
		return exec.CommandContext(ctx, name, args...)
	}
	lookPath = exec.LookPath
)

func resolveSymvault(ctx context.Context, path string) (string, error) {
	if err := validateVaultPath(path); err != nil {
		return "", err
	}
	if _, err := lookPath("symvault"); err != nil {
		return "", ErrSymvaultNotFound
	}

	ctx, cancel := withDefaultTimeout(ctx)
	defer cancel()

	cmd := execCommandContext(ctx, "symvault", "get", "--", path, "--print")
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return "", fmt.Errorf("%w: symvault get timed out after %s", ErrTimeout, DefaultTimeout)
		}
		if detail := strings.TrimSpace(stderr.String()); detail != "" {
			return "", fmt.Errorf("%w: %s", err, detail)
		}
		return "", err
	}
	return strings.TrimSpace(string(out)), nil
}

func validateVaultPath(path string) error {
	switch {
	case path == "":
		return fmt.Errorf("invalid symvault credential path: empty")
	case strings.HasPrefix(path, "-"):
		return fmt.Errorf("invalid symvault credential path: must not start with '-'")
	case strings.IndexByte(path, 0) >= 0:
		return fmt.Errorf("invalid symvault credential path: contains a null byte")
	}
	for _, r := range path {
		if unicode.IsControl(r) {
			return fmt.Errorf("invalid symvault credential path: contains control characters")
		}
	}
	return nil
}

// withDefaultTimeout applies DefaultTimeout only when ctx has no deadline of
// its own — a caller-supplied deadline always wins.
func withDefaultTimeout(ctx context.Context) (context.Context, context.CancelFunc) {
	if _, ok := ctx.Deadline(); ok {
		return ctx, func() {}
	}
	return context.WithTimeout(ctx, DefaultTimeout)
}
