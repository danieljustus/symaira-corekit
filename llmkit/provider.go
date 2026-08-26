// Package llmkit provides the shared LLM provider layer for the Symaira Go
// tools, implementing docs/llm-provider-contract.md.
//
// The design is one HTTP transport plus a dialect table: almost every vendor
// speaks the OpenAI wire format, so adding a provider is a descriptor entry in
// contracts/llm_providers.json rather than new client code. Anthropic is the
// only genuine wire exception. Custom endpoints and local servers (Ollama,
// llama.cpp, LM Studio, vLLM) are ordinary descriptors with a base-URL
// override.
//
// Credentials are resolved through the shared reference format
// (symvault://, keychain://, env://NAME) — the client never takes a raw key
// from config files. Errors are classified into the six-category contract
// taxonomy and map onto corekit exitcodes values, so callers branch on codes
// instead of string-matching upstream text.
//
// This package has no cloud or tool-specific dependencies and imports no
// sibling Symaira tool beyond this module's own exitcodes package.
package llmkit

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
)

//go:embed providers.json
var registryJSON []byte

// AuthScheme identifies how a request carries credentials.
type AuthScheme string

const (
	// AuthBearer sends "Authorization: Bearer <key>".
	AuthBearer AuthScheme = "bearer"
	// AuthHeader sends the key in a named header (e.g. x-api-key).
	AuthHeader AuthScheme = "header"
	// AuthNone sends no credential (local servers).
	AuthNone AuthScheme = "none"
)

// WireDialect names a request/response wire format.
type WireDialect string

const (
	// DialectOpenAI is the OpenAI chat-completions wire format, spoken by
	// most vendors and local servers.
	DialectOpenAI WireDialect = "openai"
	// DialectAnthropic is the Anthropic messages wire format.
	DialectAnthropic WireDialect = "anthropic"
)

// Capabilities are the feature promises a descriptor makes. A consumer must
// not offer a feature the descriptor does not promise.
type Capabilities struct {
	Streaming    bool `json:"streaming"`
	ToolUse      bool `json:"tool_use"`
	Embeddings   bool `json:"embeddings"`
	Vision       bool `json:"vision"`
	SystemPrompt bool `json:"system_prompt"`
}

// ModelSource describes how the model list for a provider is obtained.
type ModelSource struct {
	// Mode is one of "static", "discovered", "deployment", "configured".
	Mode string `json:"mode"`
	// DiscoveryPath is the endpoint to query when Mode is "discovered",
	// interpreted against the provider root (see Descriptor.DiscoveryURL).
	DiscoveryPath string `json:"discovery_path,omitempty"`
	// Default is the fallback model ID, possibly empty.
	Default string `json:"default"`
}

// Descriptor is the declarative description of one LLM provider. It mirrors
// the entries in contracts/llm_providers.json; see the contract document for
// field semantics.
type Descriptor struct {
	ID          string `json:"id"`
	DisplayName string `json:"display_name"`

	BaseURL                 string `json:"base_url"`
	BaseURLOverridable      bool   `json:"base_url_overridable"`
	BaseURLRequiredOverride bool   `json:"base_url_required_override,omitempty"`

	AuthScheme   AuthScheme        `json:"auth_scheme"`
	AuthHeader   string            `json:"auth_header,omitempty"`
	ExtraHeaders map[string]string `json:"extra_headers,omitempty"`

	Dialect             WireDialect `json:"dialect"`
	DialectConfigurable bool        `json:"dialect_configurable,omitempty"`

	Capabilities Capabilities `json:"capabilities"`
	Models       ModelSource  `json:"models"`

	CredentialEnvDefault string `json:"credential_env_default,omitempty"`
}

// registry is the lazily-parsed embedded descriptor registry.
var (
	registryOnce sync.Once
	registryErr  error
	registryByID map[string]Descriptor
	registryList []Descriptor
)

func loadRegistry() error {
	registryOnce.Do(func() {
		var raw struct {
			SchemaVersion int          `json:"schema_version"`
			Providers     []Descriptor `json:"providers"`
		}
		if err := json.Unmarshal(registryJSON, &raw); err != nil {
			registryErr = fmt.Errorf("llmkit: parse embedded provider registry: %w", err)
			return
		}
		registryByID = make(map[string]Descriptor, len(raw.Providers))
		for _, p := range raw.Providers {
			// Normalize the JSON spelling of auth into the typed fields.
			p.AuthScheme = authSchemeOf(p)
			registryByID[p.ID] = p
			registryList = append(registryList, p)
		}
	})
	return registryErr
}

// authSchemeOf extracts the typed auth scheme. The raw JSON stores the scheme
// under "auth"; the embedded copy is pre-flattened by gen so this reads the
// flattened fields.
func authSchemeOf(p Descriptor) AuthScheme { return p.AuthScheme }

// Providers returns every descriptor in the shared registry.
func Providers() ([]Descriptor, error) {
	if err := loadRegistry(); err != nil {
		return nil, err
	}
	out := make([]Descriptor, len(registryList))
	copy(out, registryList)
	return out, nil
}

// Lookup returns the descriptor with the given id.
func Lookup(id string) (Descriptor, bool) {
	if err := loadRegistry(); err != nil {
		return Descriptor{}, false
	}
	d, ok := registryByID[strings.ToLower(id)]
	return d, ok
}

// DefaultModel returns the descriptor's fallback model, if any.
func (d Descriptor) DefaultModel() string { return d.Models.Default }

// Validate reports whether the descriptor is usable as configured: a base URL
// exists (or an override is supplied separately) and the dialect is known.
func (d Descriptor) Validate() error {
	switch d.Dialect {
	case DialectOpenAI, DialectAnthropic:
	default:
		return fmt.Errorf("llmkit: provider %q has unknown dialect %q", d.ID, d.Dialect)
	}
	if d.BaseURL == "" && !d.BaseURLRequiredOverride {
		return fmt.Errorf("llmkit: provider %q has no base URL and none was provided", d.ID)
	}
	return nil
}
