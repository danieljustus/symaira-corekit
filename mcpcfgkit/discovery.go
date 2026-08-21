package mcpcfgkit

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Source is one AI-client config location to probe.
type Source struct {
	Client string // claude-desktop, cursor, windsurf, ...
	Path   string // absolute path to the config file
	Key    string // top-level key holding the servers map (default "mcpServers")
}

// Server is one configured MCP server entry. Consumers enrich this with
// tool-specific fields (credential warnings, secret-backed flags, …).
type Server struct {
	Name       string            `json:"name"`
	Client     string            `json:"client"`
	Transport  string            `json:"transport"` // stdio | http | sse
	Command    string            `json:"command,omitempty"`
	Args       []string          `json:"args,omitempty"`
	URL        string            `json:"url,omitempty"`
	ConfigPath string            `json:"config_path,omitempty"`
	Env        map[string]string `json:"env,omitempty"`
}

// FS abstracts filesystem access so tests can inject fixtures without
// touching real client configs.
type FS interface {
	ReadFile(path string) ([]byte, error)
	Glob(pattern string) ([]string, error)
}

// OSFS is the real filesystem implementation.
type OSFS struct{}

func (OSFS) ReadFile(path string) ([]byte, error)  { return os.ReadFile(path) }
func (OSFS) Glob(pattern string) ([]string, error) { return filepath.Glob(pattern) }

// DefaultSources returns the well-known client config locations for the
// current user. Missing files are tolerated by Discover (skipped silently).
func DefaultSources() []Source {
	home, err := os.UserHomeDir()
	if err != nil {
		home = "~"
	}
	return []Source{
		{Client: "claude-desktop", Path: filepath.Join(home, "Library", "Application Support", "Claude", "claude_desktop_config.json")},
		{Client: "cursor", Path: filepath.Join(home, ".cursor", "mcp.json")},
		{Client: "windsurf", Path: filepath.Join(home, ".codeium", "windsurf", "mcp_config.json")},
		{Client: "vscode", Path: filepath.Join(home, ".vscode", "mcp.json")},
	}
}

// Discover scans the given sources and returns the configured servers plus
// non-fatal notes (unreadable files, missing keys, parse errors).
func Discover(sources []Source) ([]Server, []string) {
	return discoverWith(OSFS{}, sources)
}

func discoverWith(fsys FS, sources []Source) ([]Server, []string) {
	var servers []Server
	var notes []string
	for _, src := range sources {
		expanded := expandGlob(fsys, src)
		for _, s := range expanded {
			data, err := fsys.ReadFile(s.Path)
			if err != nil {
				continue // missing file — tolerated
			}
			entries, key, err := parseConfigAutoDetect(data, s.Key)
			if err != nil {
				notes = append(notes, fmt.Sprintf("%s: %s: %v", s.Client, s.Path, err))
				continue
			}
			for name, entry := range entries {
				servers = append(servers, Server{
					Name:       name,
					Client:     s.Client,
					Transport:  entry.TransportValue(),
					Command:    entry.Command,
					Args:       entry.Args,
					URL:        entry.URL,
					ConfigPath: s.Path,
					Env:        entry.Env,
				})
			}
			if key != s.Key {
				notes = append(notes, fmt.Sprintf("%s: %s uses key %q (expected %q)", s.Client, s.Path, key, s.Key))
			}
		}
	}
	return servers, notes
}

// Entry is one raw server entry inside the config map.
type Entry struct {
	Command   string            `json:"command,omitempty"`
	Args      []string          `json:"args,omitempty"`
	URL       string            `json:"url,omitempty"`
	Type      string            `json:"type,omitempty"`
	Transport string            `json:"transport,omitempty"`
	Env       map[string]string `json:"env,omitempty"`
}

// Transport resolves the effective transport from URL/type/transport fields.
func (e Entry) TransportValue() string {
	if e.URL != "" {
		if e.Type != "" {
			return e.Type
		}
		return "http"
	}
	if e.Transport != "" {
		return e.Transport
	}
	return "stdio"
}

func expandGlob(fsys FS, src Source) []Source {
	if !strings.ContainsAny(src.Path, "*?[") {
		return []Source{src}
	}
	matches, err := fsys.Glob(src.Path)
	if err != nil || len(matches) == 0 {
		return nil
	}
	out := make([]Source, 0, len(matches))
	for _, m := range matches {
		c := src
		c.Path = m
		out = append(out, c)
	}
	return out
}

// parseConfigAutoDetect parses JSONC/JSON/YAML, returning the server map and
// the key that was actually found.
func parseConfigAutoDetect(data []byte, preferredKey string) (map[string]Entry, string, error) {
	// Try JSONC/JSON first (most client configs are JSON with comments).
	trimmed := strings.TrimSpace(string(data))
	if strings.HasPrefix(trimmed, "{") {
		entries, key, err := parseJSONConfig(data, preferredKey)
		if err == nil {
			return entries, key, nil
		}
		// Fall through to YAML only if the JSON parse clearly failed on syntax,
		// not because the key is missing.
		if !strings.Contains(err.Error(), "key not found") {
			return nil, "", err
		}
	}
	return parseYAMLConfig(data, preferredKey)
}

func parseJSONConfig(data []byte, preferredKey string) (map[string]Entry, string, error) {
	stripped := JSONCStrip(string(data))
	var doc map[string]json.RawMessage
	if err := json.Unmarshal([]byte(stripped), &doc); err != nil {
		return nil, "", fmt.Errorf("parse JSON: %w", err)
	}
	key, found := lookupJSONKey(doc, []string{preferredKey, "mcpServers", "mcp_servers"})
	if !found {
		return nil, "", fmt.Errorf("key not found: %q", preferredKey)
	}
	var entries map[string]Entry
	if err := json.Unmarshal(doc[key], &entries); err != nil {
		return nil, "", fmt.Errorf("parse %q: %w", key, err)
	}
	return entries, key, nil
}

func lookupJSONKey(doc map[string]json.RawMessage, candidates []string) (string, bool) {
	for _, c := range candidates {
		if _, ok := doc[c]; ok {
			return c, true
		}
	}
	return "", false
}

func parseYAMLConfig(data []byte, preferredKey string) (map[string]Entry, string, error) {
	var doc map[string]any
	if err := yamlUnmarshal(data, &doc); err != nil {
		return nil, "", fmt.Errorf("parse YAML: %w", err)
	}
	key, found := lookupYAMLKey(doc, []string{preferredKey, "mcpServers", "mcp_servers"})
	if !found {
		return nil, "", fmt.Errorf("key not found: %q", preferredKey)
	}
	raw, ok := doc[key].(map[string]any)
	if !ok {
		return nil, "", fmt.Errorf("key %q is not an object", key)
	}
	entries := make(map[string]Entry, len(raw))
	for name, v := range raw {
		entry, err := entryFromYAML(v)
		if err != nil {
			continue // skip malformed entries
		}
		entries[name] = entry
	}
	return entries, key, nil
}

func lookupYAMLKey(doc map[string]any, candidates []string) (string, bool) {
	for _, c := range candidates {
		if _, ok := doc[c]; ok {
			return c, true
		}
	}
	return "", false
}
