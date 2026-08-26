// Command gen regenerates llmkit/providers.json from the shared contract
// source of truth in contracts/llm_providers.json. Run it whenever the
// contract registry changes:
//
//	go generate ./llmkit/   (or: go run ./llmkit/gen)
package main

import (
	"encoding/json"
	"fmt"
	"os"
)

func main() {
	raw, err := os.ReadFile("../contracts/llm_providers.json")
	if err != nil {
		fmt.Fprintf(os.Stderr, "read contracts: %v\n", err)
		os.Exit(1)
	}
	var src struct {
		SchemaVersion int `json:"schema_version"`
		Providers     []struct {
			ID                      string `json:"id"`
			DisplayName             string `json:"display_name"`
			BaseURL                 any    `json:"base_url"`
			BaseURLOverridable      bool   `json:"base_url_overridable"`
			BaseURLRequiredOverride bool   `json:"base_url_required_override"`
			Auth                    struct {
				Scheme             string `json:"scheme"`
				Header             string `json:"header"`
				ConfigurableScheme bool   `json:"configurable_scheme"`
			} `json:"auth"`
			ExtraHeaders        map[string]string `json:"extra_headers"`
			Dialect             string            `json:"dialect"`
			DialectConfigurable bool              `json:"dialect_configurable"`
			Capabilities        struct {
				Streaming    bool `json:"streaming"`
				ToolUse      bool `json:"tool_use"`
				Embeddings   bool `json:"embeddings"`
				Vision       bool `json:"vision"`
				SystemPrompt bool `json:"system_prompt"`
			} `json:"capabilities"`
			Models struct {
				Mode          string `json:"mode"`
				DiscoveryPath string `json:"discovery_path"`
				Default       any    `json:"default"`
			} `json:"models"`
			CredentialRefEnvDefault any `json:"credential_ref_env_default"`
		} `json:"providers"`
	}
	if err := json.Unmarshal(raw, &src); err != nil {
		fmt.Fprintf(os.Stderr, "parse contracts: %v\n", err)
		os.Exit(1)
	}

	type modelsOut struct {
		Mode          string `json:"mode"`
		DiscoveryPath string `json:"discovery_path,omitempty"`
		Default       string `json:"default"`
	}
	type provOut struct {
		ID                      string            `json:"id"`
		DisplayName             string            `json:"display_name"`
		BaseURL                 *string           `json:"base_url"`
		BaseURLOverridable      bool              `json:"base_url_overridable"`
		BaseURLRequiredOverride bool              `json:"base_url_required_override,omitempty"`
		AuthScheme              string            `json:"auth_scheme"`
		AuthHeader              string            `json:"auth_header,omitempty"`
		ExtraHeaders            map[string]string `json:"extra_headers,omitempty"`
		Dialect                 string            `json:"dialect"`
		DialectConfigurable     bool              `json:"dialect_configurable,omitempty"`
		Capabilities            struct {
			Streaming    bool `json:"streaming"`
			ToolUse      bool `json:"tool_use"`
			Embeddings   bool `json:"embeddings"`
			Vision       bool `json:"vision"`
			SystemPrompt bool `json:"system_prompt"`
		} `json:"capabilities"`
		Models               modelsOut `json:"models"`
		CredentialEnvDefault string    `json:"credential_env_default,omitempty"`
	}
	out := struct {
		SchemaVersion int       `json:"schema_version"`
		Providers     []provOut `json:"providers"`
	}{SchemaVersion: src.SchemaVersion}

	for _, p := range src.Providers {
		q := provOut{
			ID:                      p.ID,
			DisplayName:             p.DisplayName,
			AuthScheme:              p.Auth.Scheme,
			Dialect:                 p.Dialect,
			Capabilities:            p.Capabilities,
			DialectConfigurable:     p.DialectConfigurable,
			ExtraHeaders:            p.ExtraHeaders,
			AuthHeader:              p.Auth.Header,
			BaseURLOverridable:      p.BaseURLOverridable,
			BaseURLRequiredOverride: p.BaseURLRequiredOverride,
			Models:                  modelsOut{Mode: p.Models.Mode, DiscoveryPath: p.Models.DiscoveryPath},
		}
		if s, ok := p.BaseURL.(string); ok {
			q.BaseURL = &s
		}
		if s, ok := p.Models.Default.(string); ok {
			q.Models.Default = s
		}
		if s, ok := p.CredentialRefEnvDefault.(string); ok {
			q.CredentialEnvDefault = s
		}
		out.Providers = append(out.Providers, q)
	}

	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(false)
	if err := enc.Encode(out); err != nil {
		fmt.Fprintf(os.Stderr, "encode: %v\n", err)
		os.Exit(1)
	}
}
