package mcpcfgkit

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestJSONCStripLineComments(t *testing.T) {
	input := "{\n  // comment\n  \"a\": 1 // trailing\n}"
	out := JSONCStrip(input)
	if strings.Contains(out, "comment") || strings.Contains(out, "trailing") {
		t.Errorf("comments not stripped: %q", out)
	}
	if !strings.Contains(out, "\"a\": 1") {
		t.Errorf("content lost: %q", out)
	}
}

func TestJSONCStripBlockComments(t *testing.T) {
	input := "{ /* block */ \"a\": 1 /* mid */ , \"b\": 2 }"
	out := JSONCStrip(input)
	if strings.Contains(out, "block") || strings.Contains(out, "mid") {
		t.Errorf("block comments not stripped: %q", out)
	}
}

func TestJSONCStripPreservesURLInString(t *testing.T) {
	input := `{ "url": "https://example.com/path" }`
	out := JSONCStrip(input)
	if !strings.Contains(out, "https://example.com/path") {
		t.Errorf("URL mangled: %q", out)
	}
}

func TestJSONCStripPreservesEscapedQuote(t *testing.T) {
	input := `{ "s": "a\"//b" }`
	out := JSONCStrip(input)
	if !strings.Contains(out, `a\"//b`) {
		t.Errorf("escaped quote content lost: %q", out)
	}
}

// fakeFS is a minimal in-memory FS for discovery tests.
type fakeFS struct {
	files map[string]string
}

func (f fakeFS) ReadFile(path string) ([]byte, error) {
	if data, ok := f.files[path]; ok {
		return []byte(data), nil
	}
	return nil, errNotExist(path)
}

func (f fakeFS) Glob(pattern string) ([]string, error) {
	var out []string
	for p := range f.files {
		if ok, _ := filepath.Match(pattern, p); ok {
			out = append(out, p)
		}
	}
	return out, nil
}

func errNotExist(path string) error { return &notExistError{path} }

type notExistError struct{ path string }

func (e *notExistError) Error() string { return "no such file: " + e.path }

func TestDiscoverJSONConfig(t *testing.T) {
	fsys := fakeFS{files: map[string]string{
		"/cfg/claude.json": `{
			// comment
			"mcpServers": {
				"github": { "command": "gh", "args": ["mcp"], "env": {"GITHUB_TOKEN": "abc"} },
				"filesystem": { "command": "/usr/bin/npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"] }
			}
		}`,
	}}
	servers, notes := discoverWith(fsys, []Source{{Client: "claude-desktop", Path: "/cfg/claude.json"}})
	if len(servers) != 2 {
		t.Fatalf("want 2 servers, got %d (notes: %v)", len(servers), notes)
	}
	// Map iteration order is unspecified — find by name.
	var gh *Server
	for i := range servers {
		if servers[i].Name == "github" {
			gh = &servers[i]
			break
		}
	}
	if gh == nil {
		t.Fatalf("github server not found: %+v", servers)
	}
	if gh.Client != "claude-desktop" || gh.Transport != "stdio" {
		t.Errorf("unexpected github server: %+v", gh)
	}
	if gh.Command != "gh" || len(gh.Args) != 1 || gh.Args[0] != "mcp" {
		t.Errorf("unexpected command/args: %+v", gh)
	}
	if gh.Env["GITHUB_TOKEN"] != "abc" {
		t.Errorf("env not parsed: %+v", gh.Env)
	}
}

func TestDiscoverHTTPServer(t *testing.T) {
	fsys := fakeFS{files: map[string]string{
		"/cfg/cursor.json": `{"mcpServers": {"remote": {"url": "https://mcp.example.com/sse", "type": "sse"}}}`,
	}}
	servers, _ := discoverWith(fsys, []Source{{Client: "cursor", Path: "/cfg/cursor.json"}})
	if len(servers) != 1 {
		t.Fatalf("want 1 server, got %d", len(servers))
	}
	if servers[0].Transport != "sse" || servers[0].URL != "https://mcp.example.com/sse" {
		t.Errorf("unexpected remote server: %+v", servers[0])
	}
}

func TestDiscoverYAMLConfig(t *testing.T) {
	fsys := fakeFS{files: map[string]string{
		"/cfg/yaml.json": "mcpServers:\n  github:\n    command: gh\n    args: [mcp]\n",
	}}
	servers, notes := discoverWith(fsys, []Source{{Client: "vscode", Path: "/cfg/yaml.json"}})
	if len(servers) != 1 {
		t.Fatalf("want 1 server, got %d (notes: %v)", len(servers), notes)
	}
	if servers[0].Name != "github" || servers[0].Command != "gh" {
		t.Errorf("unexpected yaml server: %+v", servers[0])
	}
}

func TestDiscoverMissingFileTolerated(t *testing.T) {
	fsys := fakeFS{files: map[string]string{}}
	servers, notes := discoverWith(fsys, []Source{{Client: "cursor", Path: "/nonexistent.json"}})
	if len(servers) != 0 || len(notes) != 0 {
		t.Errorf("missing file should be silent, got servers=%d notes=%d", len(servers), len(notes))
	}
}

func TestDiscoverInvalidJSONNotes(t *testing.T) {
	fsys := fakeFS{files: map[string]string{
		"/cfg/bad.json": `{ "mcpServers": {`,
	}}
	servers, notes := discoverWith(fsys, []Source{{Client: "cursor", Path: "/cfg/bad.json"}})
	if len(servers) != 0 || len(notes) != 1 {
		t.Errorf("want 0 servers + 1 note, got servers=%d notes=%d", len(servers), len(notes))
	}
}

func TestDiscoverGlobExpansion(t *testing.T) {
	fsys := fakeFS{files: map[string]string{
		"/cfg/a.json": `{"mcpServers": {"s1": {"command": "a"}}}`,
		"/cfg/b.json": `{"mcpServers": {"s2": {"command": "b"}}}`,
	}}
	servers, _ := discoverWith(fsys, []Source{{Client: "multi", Path: "/cfg/*.json"}})
	if len(servers) != 2 {
		t.Fatalf("want 2 servers from glob, got %d", len(servers))
	}
}

func TestEntryTransportValue(t *testing.T) {
	tests := []struct {
		name string
		e    Entry
		want string
	}{
		{"stdio default", Entry{Command: "gh"}, "stdio"},
		{"http from url", Entry{URL: "https://x"}, "http"},
		{"sse from type", Entry{URL: "https://x", Type: "sse"}, "sse"},
		{"explicit transport", Entry{Transport: "http"}, "http"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := tt.e.TransportValue(); got != tt.want {
				t.Errorf("TransportValue() = %q, want %q", got, tt.want)
			}
		})
	}
}
