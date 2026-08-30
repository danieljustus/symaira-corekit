// Contract test for the shared secret-reference format. secret_refs.json is
// the cross-language source of truth the Go (secretref) and eventually the
// Swift (SymairaProviderKit) resolvers are specified against; this test
// asserts the Go implementation's default timeout and recognized prefixes
// stay in sync with the documented contract.
package contracts

import (
	"encoding/json"
	"os"
	"testing"
	"time"

	"github.com/danieljustus/symaira-corekit/secretref"
)

type secretRefForm struct {
	Prefix   string `json:"prefix"`
	Example  string `json:"example"`
	Resolver string `json:"resolver"`
	Platform string `json:"platform"`
}

type secretRefContract struct {
	SchemaVersion           int             `json:"schema_version"`
	Forms                   []secretRefForm `json:"forms"`
	PrecedenceNote          string          `json:"precedence_note"`
	DefaultTimeoutSeconds   float64         `json:"default_timeout_seconds"`
	CanonicalImplementation string          `json:"canonical_implementation"`
}

func loadSecretRefs(t *testing.T) secretRefContract {
	t.Helper()
	raw, err := os.ReadFile("secret_refs.json")
	if err != nil {
		t.Fatalf("read secret_refs.json: %v", err)
	}
	var c secretRefContract
	if err := json.Unmarshal(raw, &c); err != nil {
		t.Fatalf("parse secret_refs.json: %v", err)
	}
	return c
}

func TestSecretRefFormsAreWellFormedAndUnique(t *testing.T) {
	c := loadSecretRefs(t)
	if len(c.Forms) == 0 {
		t.Fatal("secret_refs.json declares no forms")
	}
	seen := map[string]bool{}
	sawBare := false
	for _, f := range c.Forms {
		if seen[f.Prefix] {
			t.Errorf("duplicate prefix %q", f.Prefix)
		}
		seen[f.Prefix] = true
		if f.Prefix == "" {
			sawBare = true
		}
		if f.Example == "" || f.Resolver == "" || f.Platform == "" {
			t.Errorf("form %q is missing example/resolver/platform", f.Prefix)
		}
	}
	if !sawBare {
		t.Error("contract must document the bare-value (no-prefix) form")
	}
	for _, want := range []string{"symvault://", "keychain://", "env://"} {
		if !seen[want] {
			t.Errorf("contract missing required prefix %q", want)
		}
	}
}

func TestSecretRefDefaultTimeoutMatchesImplementation(t *testing.T) {
	c := loadSecretRefs(t)
	want := time.Duration(c.DefaultTimeoutSeconds * float64(time.Second))
	if secretref.DefaultTimeout != want {
		t.Errorf("secretref.DefaultTimeout = %s, contract declares %s", secretref.DefaultTimeout, want)
	}
}

func TestSecretRefCanonicalImplementationNamed(t *testing.T) {
	c := loadSecretRefs(t)
	if c.CanonicalImplementation != "corekit/secretref" {
		t.Errorf("canonical_implementation = %q, want %q", c.CanonicalImplementation, "corekit/secretref")
	}
}
