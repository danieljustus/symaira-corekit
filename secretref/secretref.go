// Package secretref resolves the shared secret-reference format used across
// the Symaira Go tools:
//
//	symvault://path         -> `symvault get -- path --print`
//	keychain://svc/account  -> macOS Keychain via the `security` CLI
//	env://NAME              -> os.Getenv("NAME")
//	NAME                    -> bare value, treated as an env var name
//
// See contracts/secret_refs.json for the cross-language contract this
// package implements.
package secretref

import (
	"context"
	"fmt"
	"os"
	"strings"
)

// Resolve resolves ref (falling back to envDefault when ref is empty)
// according to the shared precedence chain documented on the package.
//
// Every symvault/keychain subprocess call runs under ctx; when ctx carries
// no deadline, DefaultTimeout applies instead. The resolved value is never
// included in a returned error.
func Resolve(ctx context.Context, ref, envDefault string) (string, error) {
	target := ref
	if target == "" {
		target = envDefault
	}
	if target == "" {
		return "", ErrNoReference
	}
	if ctx == nil {
		ctx = context.Background()
	}

	switch {
	case strings.HasPrefix(target, "symvault://"):
		path := strings.TrimPrefix(target, "symvault://")
		out, err := resolveSymvault(ctx, path)
		if err != nil {
			return "", fmt.Errorf("resolve %s: %w", refLabel(ref), err)
		}
		return out, nil
	case strings.HasPrefix(target, "keychain://"):
		service, account, ok := strings.Cut(strings.TrimPrefix(target, "keychain://"), "/")
		if !ok || service == "" || account == "" {
			return "", fmt.Errorf("resolve %s: invalid keychain reference, expected keychain://service/account", refLabel(ref))
		}
		out, err := resolveKeychain(ctx, service, account)
		if err != nil {
			return "", fmt.Errorf("resolve %s: %w", refLabel(ref), err)
		}
		return out, nil
	case strings.HasPrefix(target, "env://"):
		name := strings.TrimPrefix(target, "env://")
		v, ok := os.LookupEnv(name)
		if !ok || v == "" {
			return "", fmt.Errorf("environment variable %s is not set (reference %s)", name, refLabel(ref))
		}
		return v, nil
	default:
		v, ok := os.LookupEnv(target)
		if !ok || v == "" {
			return "", fmt.Errorf("environment variable %s is not set (reference %s)", target, refLabel(ref))
		}
		return v, nil
	}
}

// refLabel keeps error messages pointing at the reference the caller
// configured, never at any resolved value.
func refLabel(ref string) string {
	if ref == "" {
		return "<default>"
	}
	return ref
}
