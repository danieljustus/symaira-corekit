// Contract tests for the shared LLM provider registry. The JSON files in
// contracts/ are the cross-language source of truth consumed by the Go
// (llmkit) and Swift (SymairaProviderKit) provider layers; these tests assert
// that the data itself stays internally consistent so a broken edit cannot
// silently desync both implementations.
package contracts

import (
	"encoding/json"
	"os"
	"strings"
	"testing"
)

type llmAuth struct {
	Scheme             string `json:"scheme"`
	Header             string `json:"header,omitempty"`
	ConfigurableScheme bool   `json:"configurable_scheme,omitempty"`
}

type llmCapabilities struct {
	Streaming    bool `json:"streaming"`
	ToolUse      bool `json:"tool_use"`
	Embeddings   bool `json:"embeddings"`
	Vision       bool `json:"vision"`
	SystemPrompt bool `json:"system_prompt"`
}

type llmModels struct {
	Mode          string  `json:"mode"`
	DiscoveryPath string  `json:"discovery_path,omitempty"`
	Default       *string `json:"default"`
}

type llmProvider struct {
	ID                      string            `json:"id"`
	DisplayName             string            `json:"display_name"`
	BaseURL                 *string           `json:"base_url"`
	BaseURLOverridable      bool              `json:"base_url_overridable"`
	BaseURLRequiredOverride bool              `json:"base_url_required_override,omitempty"`
	Auth                    llmAuth           `json:"auth"`
	ExtraHeaders            map[string]string `json:"extra_headers,omitempty"`
	Dialect                 string            `json:"dialect"`
	DialectConfigurable     bool              `json:"dialect_configurable,omitempty"`
	Capabilities            llmCapabilities   `json:"capabilities"`
	Models                  llmModels         `json:"models"`
	CredentialRefEnvDefault *string           `json:"credential_ref_env_default"`
}

type llmRegistry struct {
	SchemaVersion int           `json:"schema_version"`
	Providers     []llmProvider `json:"providers"`
}

type llmErrorDef struct {
	Code      string `json:"code"`
	Meaning   string `json:"meaning"`
	ExitCode  string `json:"exit_code"`
	Retryable bool   `json:"retryable"`
}

type llmErrorTaxonomy struct {
	SchemaVersion int           `json:"schema_version"`
	Errors        []llmErrorDef `json:"errors"`
}

func loadLLMProviders(t *testing.T) llmRegistry {
	t.Helper()
	raw, err := os.ReadFile("llm_providers.json")
	if err != nil {
		t.Fatalf("read llm_providers.json: %v", err)
	}
	var reg llmRegistry
	if err := json.Unmarshal(raw, &reg); err != nil {
		t.Fatalf("parse llm_providers.json: %v", err)
	}
	return reg
}

func loadLLMErrors(t *testing.T) llmErrorTaxonomy {
	t.Helper()
	raw, err := os.ReadFile("llm_errors.json")
	if err != nil {
		t.Fatalf("read llm_errors.json: %v", err)
	}
	var tax llmErrorTaxonomy
	if err := json.Unmarshal(raw, &tax); err != nil {
		t.Fatalf("parse llm_errors.json: %v", err)
	}
	return tax
}

func TestLLMProviderIDsUniqueAndSane(t *testing.T) {
	reg := loadLLMProviders(t)
	if len(reg.Providers) < 10 {
		t.Fatalf("expected at least 10 providers, got %d", len(reg.Providers))
	}
	seen := map[string]bool{}
	for _, p := range reg.Providers {
		if p.ID == "" || strings.Contains(p.ID, " ") {
			t.Errorf("provider id %q must be non-empty and space-free", p.ID)
		}
		if seen[p.ID] {
			t.Errorf("duplicate provider id %q", p.ID)
		}
		seen[p.ID] = true
		if p.DisplayName == "" {
			t.Errorf("provider %q missing display_name", p.ID)
		}
	}
	for _, want := range []string{"anthropic", "openai", "openrouter", "google", "ollama", "custom"} {
		if !seen[want] {
			t.Errorf("registry must contain provider %q (audit table in docs/llm-provider-contract.md)", want)
		}
	}
}

func TestLLMDialectsValid(t *testing.T) {
	reg := loadLLMProviders(t)
	valid := map[string]bool{"openai": true, "anthropic": true}
	for _, p := range reg.Providers {
		if !valid[p.Dialect] {
			t.Errorf("provider %q has unknown dialect %q", p.ID, p.Dialect)
		}
	}
	anthropicDialects := 0
	for _, p := range reg.Providers {
		if p.Dialect == "anthropic" {
			anthropicDialects++
		}
	}
	if anthropicDialects != 1 {
		t.Errorf("exactly one provider may use the anthropic dialect, found %d", anthropicDialects)
	}
}

func TestLLMAuthSchemeValid(t *testing.T) {
	reg := loadLLMProviders(t)
	valid := map[string]bool{"bearer": true, "header": true, "none": true}
	for _, p := range reg.Providers {
		if !valid[p.Auth.Scheme] {
			t.Errorf("provider %q has unknown auth scheme %q", p.ID, p.Auth.Scheme)
		}
		if p.Auth.Scheme == "header" && p.Auth.Header == "" && !p.Auth.ConfigurableScheme {
			t.Errorf("provider %q uses header auth without naming the header", p.ID)
		}
	}
}

func TestLLMBaseURLInvariants(t *testing.T) {
	reg := loadLLMProviders(t)
	for _, p := range reg.Providers {
		switch {
		case p.BaseURLRequiredOverride:
			if p.BaseURL != nil {
				t.Errorf("provider %q sets base_url but declares base_url_required_override", p.ID)
			}
		case p.BaseURL == nil:
			t.Errorf("provider %q has neither base_url nor base_url_required_override", p.ID)
		default:
			u := *p.BaseURL
			isLocal := strings.Contains(u, "localhost") || strings.Contains(u, "127.0.0.1")
			if !isLocal && !strings.HasPrefix(u, "https://") {
				t.Errorf("provider %q base_url %q must be https:// (or localhost)", p.ID, u)
			}
		}
	}
}

func TestLLMModelModesValid(t *testing.T) {
	reg := loadLLMProviders(t)
	valid := map[string]bool{"static": true, "discovered": true, "deployment": true, "configured": true}
	for _, p := range reg.Providers {
		if !valid[p.Models.Mode] {
			t.Errorf("provider %q has unknown model mode %q", p.ID, p.Models.Mode)
		}
		if p.Models.Mode == "discovered" && p.Models.DiscoveryPath == "" {
			t.Errorf("provider %q is discovered but lacks discovery_path", p.ID)
		}
	}
}

func TestLLMCredentialEnvDefaults(t *testing.T) {
	reg := loadLLMProviders(t)
	for _, p := range reg.Providers {
		switch {
		case p.CredentialRefEnvDefault == nil:
		case strings.HasPrefix(*p.CredentialRefEnvDefault, "env://"):
			t.Errorf("provider %q env default should be the bare name, got env:// form", p.ID)
		case strings.ContainsAny(*p.CredentialRefEnvDefault, ":/"):
			t.Errorf("provider %q env default %q looks like a URI reference, not an env name", p.ID, *p.CredentialRefEnvDefault)
		}
	}
	// Providers with no credential at all must say so explicitly.
	for _, p := range reg.Providers {
		if p.Auth.Scheme == "none" && p.CredentialRefEnvDefault != nil {
			t.Errorf("provider %q is auth-none but names a credential env default", p.ID)
		}
	}
}

func TestLLMErrorTaxonomy(t *testing.T) {
	tax := loadLLMErrors(t)
	wantCodes := map[string]string{
		"auth_failure":     "ExitNoAuth",
		"rate_limited":     "ExitConflict",
		"context_overflow": "ExitData",
		"model_not_found":  "ExitNotFound",
		"transport_error":  "ExitGeneric",
		"provider_error":   "ExitGeneric",
	}
	got := map[string]bool{}
	for _, e := range tax.Errors {
		if want, ok := wantCodes[e.Code]; !ok {
			t.Errorf("unknown taxonomy entry %q", e.Code)
		} else if want != e.ExitCode {
			t.Errorf("error %q maps to %s, contract requires %s", e.Code, e.ExitCode, want)
		}
		got[e.Code] = true
	}
	for code := range wantCodes {
		if !got[code] {
			t.Errorf("taxonomy missing required error code %q", code)
		}
	}
}
