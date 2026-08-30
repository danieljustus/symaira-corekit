//go:build !darwin

package secretref

import (
	"context"
	"errors"
	"testing"
)

func TestResolveKeychainUnsupportedOnNonDarwin(t *testing.T) {
	_, err := Resolve(context.Background(), "keychain://symaira/api_key", "")
	if !errors.Is(err, ErrKeychainUnsupported) {
		t.Fatalf("want ErrKeychainUnsupported, got %v", err)
	}
}
