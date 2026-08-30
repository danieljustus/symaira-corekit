//go:build darwin

package secretref

import (
	"bytes"
	"context"
	"fmt"
	"strings"
)

// resolveKeychain looks up service/account in the macOS login keychain via
// the `security` CLI, matching what symaira-desktop already does.
func resolveKeychain(ctx context.Context, service, account string) (string, error) {
	ctx, cancel := withDefaultTimeout(ctx)
	defer cancel()

	cmd := execCommandContext(ctx, "security", "find-generic-password", "-w", "-s", service, "-a", account)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return "", fmt.Errorf("%w: keychain lookup timed out after %s", ErrTimeout, DefaultTimeout)
		}
		if detail := strings.TrimSpace(stderr.String()); detail != "" {
			return "", fmt.Errorf("%w: %s", err, detail)
		}
		return "", err
	}
	return strings.TrimSpace(string(out)), nil
}
