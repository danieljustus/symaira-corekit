//go:build !darwin

package secretref

import "context"

// resolveKeychain reports ErrKeychainUnsupported on every platform other
// than macOS; there is no cross-platform keychain CLI to shell out to.
func resolveKeychain(_ context.Context, _, _ string) (string, error) {
	return "", ErrKeychainUnsupported
}
