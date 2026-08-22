package mcpcfgkit

import (
	"strings"
	"testing"
)

func TestScanAllReportsMissingSourceAsFinding(t *testing.T) {
	fsys := fakeFS{files: map[string]string{}}
	res := ScanAllWithFS(fsys, []ScanSource{
		{Client: ClientCursor, Path: "/cfg/missing.json", Key: "mcpServers"},
	})
	if len(res.Servers) != 0 {
		t.Fatalf("want 0 servers, got %d", len(res.Servers))
	}
	if len(res.Findings) != 1 {
		t.Fatalf("want 1 finding, got %d", len(res.Findings))
	}
	if res.Findings[0].Status != StatusUnsupported {
		t.Errorf("unexpected status: %q", res.Findings[0].Status)
	}
}

func TestScanAllParsesOpenCodeMCPKey(t *testing.T) {
	fsys := fakeFS{files: map[string]string{
		"/cfg/opencode.json": `{"mcp": {"gh": {"type": "local", "command": "gh", "args": ["mcp"], "environment": {"GITHUB_TOKEN": "t"}}}}`,
	}}
	res := ScanAllWithFS(fsys, []ScanSource{{Client: ClientOpenCode, Path: "/cfg/opencode.json", Key: "mcp"}})
	if len(res.Findings) != 0 {
		t.Fatalf("unexpected findings: %v", res.Findings)
	}
	if len(res.Servers) != 1 {
		t.Fatalf("want 1 server, got %d", len(res.Servers))
	}
	s := res.Servers[0]
	if s.Transport != "stdio" || s.Command != "gh" {
		t.Errorf("unexpected server: %+v", s)
	}
	// OpenCode merges "environment" and "env".
	if s.Env["GITHUB_TOKEN"] != "t" {
		t.Errorf("environment not merged: %+v", s.Env)
	}
	if len(s.EnvKeys) == 0 || len(s.EnvValues) == 0 {
		t.Errorf("EnvKeys/EnvValues not populated: %+v", s)
	}
}

func TestScanAllOpenCodeRemoteType(t *testing.T) {
	fsys := fakeFS{files: map[string]string{
		"/cfg/oc.json": `{"mcp": {"remote1": {"type": "remote", "url": "https://x.example/sse"}}}`,
	}}
	res := ScanAllWithFS(fsys, []ScanSource{{Client: ClientOpenCode, Path: "/cfg/oc.json"}})
	if len(res.Findings) != 0 {
		t.Fatalf("unexpected findings: %v", res.Findings)
	}
	if len(res.Servers) != 1 || res.Servers[0].Transport != "http" {
		t.Fatalf("unexpected servers: %+v", res.Servers)
	}
	if res.Servers[0].Command != "https://x.example/sse" {
		t.Errorf("Command should carry URL for remote servers: %+v", res.Servers[0])
	}
}

func TestScanAllOpenCodeUnknownTypeApproximate(t *testing.T) {
	fsys := fakeFS{files: map[string]string{
		"/cfg/oc2.json": `{"mcp": {"odd": {"type": "weird", "command": "cmd1"}}}`,
	}}
	res := ScanAllWithFS(fsys, []ScanSource{{Client: ClientOpenCode, Path: "/cfg/oc2.json"}})
	var approx bool
	for _, f := range res.Findings {
		if f.Status == StatusApproximate && strings.Contains(f.Message, "unknown type") {
			approx = true
		}
	}
	if !approx {
		t.Errorf("expected approximate finding for unknown type, got %v", res.Findings)
	}
	if len(res.Servers) != 1 {
		t.Errorf("server should still map as local: %+v", res.Servers)
	}
}

func TestScanAllEntryWithoutCommandOrURL(t *testing.T) {
	fsys := fakeFS{files: map[string]string{
		"/cfg/broken.json": `{"mcpServers": {"empty": {}}}`,
	}}
	res := ScanAllWithFS(fsys, []ScanSource{{Client: ClientCursor, Path: "/cfg/broken.json"}})
	if len(res.Servers) != 0 {
		t.Fatalf("broken entry must not become a server: %+v", res.Servers)
	}
	found := false
	for _, f := range res.Findings {
		if f.Status == StatusUnsupported && strings.Contains(f.Message, "missing both command and url") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected unsupported finding, got %v", res.Findings)
	}
}

func TestDefaultSourcesContainKnownClients(t *testing.T) {
	srcs := DefaultSources()
	clients := map[Client]bool{}
	for _, s := range srcs {
		clients[s.Client] = true
	}
	for _, want := range []Client{ClientHermes, ClientClaudeDesktop, ClientCursor, ClientVSCode, ClientOpenCode} {
		if !clients[want] {
			t.Errorf("client %q missing from DefaultSources: %v", want, srcs)
		}
	}
}

func TestNormalizeKeyFallbacks(t *testing.T) {
	got := normalizeKey("")
	if got[0] != "mcpServers" {
		t.Errorf("default key wrong: %v", got)
	}
	got = normalizeKey("mcp")
	found := false
	for _, k := range got {
		if k == "mcpServers" {
			found = true
		}
	}
	if !found {
		t.Errorf("mcp fallback candidates missing mcpServers: %v", got)
	}
}

func TestFindingString(t *testing.T) {
	f := Finding{Client: ClientCursor, Path: "/p", Status: StatusManual, Message: "check me"}
	out := f.String()
	for _, want := range []string{"cursor", "/p", "manual", "check me"} {
		if !strings.Contains(out, want) {
			t.Errorf("Finding.String() missing %q: %s", want, out)
		}
	}
}
