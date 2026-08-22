package mcpcfgkit

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

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

	// EnvKeys/EnvValues hold the environment variables split into keys and
	// values so callers can redact values while keeping key visibility.
	EnvKeys   []string `json:"-"`
	EnvValues []string `json:"-"`
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
			entries, err := parseConfigFile(data, normalizeKey(s.Key))
			if err != nil {
				notes = append(notes, fmt.Sprintf("%s: %s: %v", s.Client, s.Path, err))
				continue
			}
			for name, entry := range entries {
				servers = append(servers, serverFromEntry(name, string(s.Client), s.Path, entry))
			}
		}
	}
	return servers, notes
}

// serverFromEntry builds the public Server from a parsed Entry.
func serverFromEntry(name, client, configPath string, e Entry) Server {
	return Server{
		Name:       name,
		Client:     client,
		Transport:  e.TransportValue(),
		Command:    e.Command,
		Args:       e.Args,
		URL:        e.URL,
		ConfigPath: configPath,
		Env:        e.Env,
	}
}

// Entry is one raw server entry inside the config map.
type Entry struct {
	Command   string            `json:"command,omitempty"`
	Args      []string          `json:"args,omitempty"`
	URL       string            `json:"url,omitempty"`
	Type      string            `json:"type,omitempty"`
	Transport string            `json:"transport,omitempty"`
	Env       map[string]string `json:"env,omitempty"`

	// Environment is OpenCode's alternative env key ("environment").
	Environment map[string]string `json:"environment,omitempty"`
}

// TransportValue resolves the effective transport from URL/type/transport
// fields. OpenCode's "local"/"remote" types map to stdio/http.
func (e Entry) TransportValue() string {
	t := strings.ToLower(e.Type)
	switch t {
	case "local":
		return string(TransportStdio)
	case "remote":
		return string(TransportHTTP)
	}
	if e.URL != "" {
		if e.Type != "" {
			return e.Type
		}
		return string(TransportHTTP)
	}
	if e.Transport != "" {
		return e.Transport
	}
	return string(TransportStdio)
}

// CommandOrURL returns the launch command for stdio servers or the URL for
// remote ones — the single field guard's Server collapses both into Command.
func (e Entry) CommandOrURL() string {
	if e.Command != "" {
		return e.Command
	}
	return e.URL
}

// MergedEnv returns env merged with environment ("environment" wins on
// conflicts), mirroring OpenCode's dual-key layout.
func (e Entry) MergedEnv() map[string]string {
	if len(e.Env) == 0 && len(e.Environment) == 0 {
		return nil
	}
	out := make(map[string]string, len(e.Env)+len(e.Environment))
	for k, v := range e.Environment {
		out[k] = v
	}
	for k, v := range e.Env {
		out[k] = v
	}
	return out
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

// parseConfigFile parses JSONC/JSON/YAML data into entries using the first
// matching key candidate.
func parseConfigFile(data []byte, candidates []string) (map[string]Entry, error) {
	trimmed := strings.TrimSpace(string(data))
	if strings.HasPrefix(trimmed, "{") {
		entries, _, err := parseJSONConfig(data, candidates)
		if err == nil {
			return entries, nil
		}
		if !isKeyNotFound(err) {
			return nil, err
		}
	}
	entries, _, err := parseYAMLConfig(data, candidates)
	return entries, err
}

func parseJSONConfig(data []byte, candidates []string) (map[string]Entry, string, error) {
	stripped := JSONCStrip(string(data))
	var doc map[string]json.RawMessage
	if err := json.Unmarshal([]byte(stripped), &doc); err != nil {
		return nil, "", fmt.Errorf("parse JSON: %w", err)
	}
	key, found := lookupJSONKey(doc, candidates)
	if !found {
		return nil, "", fmt.Errorf("key not found: %q", candidates[0])
	}
	// The mcp key (OpenCode) uses type-based entries; both shapes unmarshal
	// into Entry since the field names overlap.
	var entries map[string]Entry
	if err := json.Unmarshal(doc[key], &entries); err != nil {
		return nil, "", fmt.Errorf("parse %q: %w", key, err)
	}
	return entries, key, nil
}

// isKeyNotFound reports whether err is a "key not found" parse failure.
func isKeyNotFound(err error) bool {
	return err != nil && strings.Contains(err.Error(), "key not found")
}

func lookupJSONKey(doc map[string]json.RawMessage, candidates []string) (string, bool) {
	for _, c := range candidates {
		if _, ok := doc[c]; ok {
			return c, true
		}
	}
	return "", false
}

func parseYAMLConfig(data []byte, candidates []string) (map[string]Entry, string, error) {
	var doc map[string]any
	if err := yamlUnmarshal(data, &doc); err != nil {
		return nil, "", fmt.Errorf("parse YAML: %w", err)
	}
	key, found := lookupYAMLKey(doc, candidates)
	if !found {
		return nil, "", fmt.Errorf("key not found: %q", candidates[0])
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
