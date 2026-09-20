// Command mcpcfg-oracle prints the canonical observation for one corpus case
// using the pinned Go implementation, so
// scripts/rust-port/mcpcfg-differential.py can compare it with the Rust port.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/danieljustus/symaira-corekit/mcpcfgkit"
)

type caseSource struct {
	Client string `json:"client"`
	Path   string `json:"path"`
	Key    string `json:"key"`
}

type fixtureCase struct {
	ID                string            `json:"id"`
	Mode              string            `json:"mode"`
	Goos              string            `json:"goos"`
	Home              string            `json:"home"`
	Sources           []caseSource      `json:"sources"`
	UseDefaultSources bool              `json:"use_default_sources"`
	Files             map[string]string `json:"files"`
}

type memFS struct {
	files map[string]string
}

func (m memFS) ReadFile(path string) ([]byte, error) {
	contents, ok := m.files[path]
	if !ok {
		return nil, os.ErrNotExist
	}
	return []byte(contents), nil
}

func (m memFS) Glob(_ string) ([]string, error) {
	// ScanAllWithFS never expands globs; real globbing is exercised through OSFS.
	return nil, nil
}

type sourceObs struct {
	Client string `json:"client"`
	Path   string `json:"path"`
	Key    string `json:"key"`
}

type serverObs struct {
	Name       string            `json:"name"`
	Client     string            `json:"client"`
	Transport  string            `json:"transport"`
	Command    string            `json:"command"`
	Args       []string          `json:"args"`
	URL        string            `json:"url"`
	ConfigPath string            `json:"config_path"`
	Env        map[string]string `json:"env"`
	EnvKeys    []string          `json:"env_keys"`
	EnvValues  []string          `json:"env_values"`
}

type noteObs struct {
	Client  string `json:"client"`
	Path    string `json:"path"`
	Kind    string `json:"kind"`
	Message string `json:"message"`
}

type findingObs struct {
	Client  string `json:"client"`
	Path    string `json:"path"`
	Status  string `json:"status"`
	Kind    string `json:"kind"`
	Message string `json:"message"`
}

type observation struct {
	Mode           string       `json:"mode"`
	DefaultSources []sourceObs  `json:"default_sources"`
	Servers        []serverObs  `json:"servers"`
	Notes          []noteObs    `json:"notes"`
	Findings       []findingObs `json:"findings"`
}

func main() {
	raw, err := io.ReadAll(os.Stdin)
	if err != nil {
		fmt.Fprintf(os.Stderr, "mcpcfg oracle: %v\n", err)
		os.Exit(1)
	}
	var fixture fixtureCase
	if err := json.Unmarshal(raw, &fixture); err != nil {
		fmt.Fprintf(os.Stderr, "mcpcfg oracle: invalid case: %v\n", err)
		os.Exit(1)
	}
	document, err := observe(fixture)
	if err != nil {
		fmt.Fprintf(os.Stderr, "mcpcfg oracle: %s: %v\n", fixture.ID, err)
		os.Exit(1)
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(document); err != nil {
		fmt.Fprintf(os.Stderr, "mcpcfg oracle: %v\n", err)
		os.Exit(1)
	}
}

func observe(fixture fixtureCase) (observation, error) {
	out := observation{
		Mode:           fixture.Mode,
		DefaultSources: []sourceObs{},
		Servers:        []serverObs{},
		Notes:          []noteObs{},
		Findings:       []findingObs{},
	}
	sources, err := declaredSources(fixture)
	if err != nil {
		return out, err
	}
	if fixture.Mode == "defaults" {
		for _, source := range defaultSources(fixture) {
			out.DefaultSources = append(out.DefaultSources, sourceObs{
				Client: string(source.Client), Path: cleanPath(source.Path), Key: source.Key,
			})
		}
		return out, nil
	}
	if fixture.UseDefaultSources {
		sources = defaultSources(fixture)
	}
	switch fixture.Mode {
	case "scan":
		result := mcpcfgkit.ScanAllWithFS(memFS{files: fixture.Files}, sources)
		servers := append([]mcpcfgkit.Server(nil), result.Servers...)
		sortServers(servers)
		for _, server := range servers {
			keys, values := sortedEnvPairs(server.EnvKeys, server.EnvValues)
			out.Servers = append(out.Servers, serverObs{
				Name:       server.Name,
				Client:     server.Client,
				Transport:  server.Transport,
				Command:    server.Command,
				Args:       nonNil(server.Args),
				URL:        server.URL,
				ConfigPath: cleanPath(server.ConfigPath),
				Env:        server.Env,
				EnvKeys:    keys,
				EnvValues:  values,
			})
		}
		findings := append([]mcpcfgkit.Finding(nil), result.Findings...)
		sortFindings(findings)
		for _, finding := range findings {
			out.Findings = append(out.Findings, findingObs{
				Client:  string(finding.Client),
				Path:    cleanPath(finding.Path),
				Status:  string(finding.Status),
				Kind:    findingKind(finding.Message),
				Message: normalizedMessage(finding.Message),
			})
		}
	case "discover":
		root, err := os.MkdirTemp(os.TempDir(), "corekit-mcpcfg-")
		if err != nil {
			return out, err
		}
		defer func() { _ = os.RemoveAll(root) }()
		rewritten := make([]mcpcfgkit.ScanSource, 0, len(sources))
		for path, contents := range fixture.Files {
			target := filepath.Join(root, path)
			if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
				return out, err
			}
			if err := os.WriteFile(target, []byte(contents), 0o600); err != nil {
				return out, err
			}
		}
		for _, source := range sources {
			rewritten = append(rewritten, mcpcfgkit.ScanSource{
				Client: source.Client, Path: filepath.Join(root, source.Path), Key: source.Key,
			})
		}
		servers, notes := mcpcfgkit.Discover(rewritten)
		sortServers(servers)
		for _, server := range servers {
			out.Servers = append(out.Servers, serverObs{
				Name:       server.Name,
				Client:     server.Client,
				Transport:  server.Transport,
				Command:    server.Command,
				Args:       nonNil(server.Args),
				URL:        server.URL,
				ConfigPath: stripRoot(root, server.ConfigPath),
				Env:        server.Env,
				EnvKeys:    nil,
				EnvValues:  nil,
			})
		}
		noteObsList := make([]noteObs, 0, len(notes))
		for _, note := range notes {
			client, path, detail := splitNote(note, rewritten)
			noteObsList = append(noteObsList, noteObs{
				Client:  client,
				Path:    stripRoot(root, path),
				Kind:    errorKind(detail),
				Message: normalizedMessage(detail),
			})
		}
		sortNotes(noteObsList)
		out.Notes = noteObsList
	default:
		return out, fmt.Errorf("unknown mode %s", fixture.Mode)
	}
	return out, nil
}

func declaredSources(fixture fixtureCase) ([]mcpcfgkit.ScanSource, error) {
	sources := make([]mcpcfgkit.ScanSource, 0, len(fixture.Sources))
	for _, source := range fixture.Sources {
		sources = append(sources, mcpcfgkit.ScanSource{
			Client: mcpcfgkit.Client(source.Client), Path: source.Path, Key: source.Key,
		})
	}
	return sources, nil
}

func defaultSources(fixture fixtureCase) []mcpcfgkit.ScanSource {
	return mcpcfgkit.DefaultSourcesForPlatform(fixture.Goos, fixture.Home)
}

func sortServers(servers []mcpcfgkit.Server) {
	sort.SliceStable(servers, func(i, j int) bool {
		left, right := servers[i], servers[j]
		if left.ConfigPath != right.ConfigPath {
			return left.ConfigPath < right.ConfigPath
		}
		if left.Client != right.Client {
			return left.Client < right.Client
		}
		return left.Name < right.Name
	})
}

func sortFindings(findings []mcpcfgkit.Finding) {
	sort.SliceStable(findings, func(i, j int) bool {
		left, right := findings[i], findings[j]
		if left.Path != right.Path {
			return left.Path < right.Path
		}
		if string(left.Status) != string(right.Status) {
			return string(left.Status) < string(right.Status)
		}
		return left.Message < right.Message
	})
}

func sortNotes(notes []noteObs) {
	sort.SliceStable(notes, func(i, j int) bool {
		if notes[i].Path != notes[j].Path {
			return notes[i].Path < notes[j].Path
		}
		return notes[i].Kind < notes[j].Kind
	})
}

// splitNote recovers the client, path and error text from a Discover note,
// which Go formats as "<client>: <path>: <error>".
func splitNote(note string, sources []mcpcfgkit.ScanSource) (string, string, string) {
	for _, source := range sources {
		prefix := fmt.Sprintf("%s: %s: ", source.Client, source.Path)
		if strings.HasPrefix(note, prefix) {
			return string(source.Client), source.Path, note[len(prefix):]
		}
	}
	if parts := strings.SplitN(note, ": ", 3); len(parts) == 3 {
		return parts[0], parts[1], parts[2]
	}
	return "", "", note
}

func findingKind(message string) string {
	if strings.HasPrefix(message, "server ") && strings.HasSuffix(message, "is missing both command and url") {
		return "missing_command_and_url"
	}
	if strings.HasPrefix(message, "server ") && strings.Contains(message, "has unknown type ") {
		return "unknown_type"
	}
	return errorKind(message)
}

func errorKind(message string) string {
	switch {
	case strings.HasPrefix(message, "parse JSON"):
		return "parse_json"
	case strings.HasPrefix(message, "parse YAML"):
		return "parse_yaml"
	case strings.HasPrefix(message, "key not found: "):
		return "key_not_found"
	case strings.HasPrefix(message, "read failed"):
		return "read_failed"
	case strings.HasPrefix(message, "parse \""):
		return "parse_entries"
	case strings.HasPrefix(message, "key \"") && strings.HasSuffix(message, "is not an object"):
		return "key_not_object"
	}
	return "unknown"
}

func normalizedMessage(message string) string {
	switch errorKind(message) {
	case "parse_json":
		return "parse JSON"
	case "parse_yaml":
		return "parse YAML"
	case "read_failed":
		return "read failed"
	case "parse_entries":
		return strings.SplitN(message, ":", 2)[0]
	}
	return message
}

// sortedEnvPairs re-pairs Go's EnvKeys/EnvValues and sorts by key: Go builds them
// by iterating a map, so their order is unspecified and must not be compared.
func sortedEnvPairs(keys, values []string) ([]string, []string) {
	type pair struct{ key, value string }
	pairs := make([]pair, 0, len(keys))
	for index, key := range keys {
		value := ""
		if index < len(values) {
			value = values[index]
		}
		pairs = append(pairs, pair{key: key, value: value})
	}
	sort.Slice(pairs, func(i, j int) bool { return pairs[i].key < pairs[j].key })
	outKeys := make([]string, 0, len(pairs))
	outValues := make([]string, 0, len(pairs))
	for _, item := range pairs {
		outKeys = append(outKeys, item.key)
		outValues = append(outValues, item.value)
	}
	return outKeys, outValues
}

func nonNil(values []string) []string {
	if values == nil {
		return []string{}
	}
	return values
}

func cleanPath(path string) string {
	return filepath.Clean(path)
}

func stripRoot(root, path string) string {
	return cleanPath(strings.TrimPrefix(path, root))
}
