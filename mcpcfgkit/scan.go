package mcpcfgkit

import (
	"fmt"
	"strings"
)

// ScanResult is the outcome of a discovery scan: the normalised servers that
// could be mapped, plus findings for every source or entry that could not.
type ScanResult struct {
	Servers  []Server
	Findings []Finding
}

// ScanAll scans all well-known clients and returns a ScanResult. Every
// client source that cannot be scanned — missing file, unreadable file, or
// parse failure — is reported as a Finding; nothing is skipped silently.
func ScanAll() ScanResult {
	return ScanAllWithFS(OSFS{}, DefaultSources())
}

// ScanAllWithFS is like ScanAll but uses the provided FS and sources, making
// it straightforward to test.
func ScanAllWithFS(fsys FS, sources []ScanSource) ScanResult {
	var res ScanResult
	for _, src := range sources {
		servers, findings := scanSourceWithFS(fsys, src)
		res.Servers = append(res.Servers, servers...)
		res.Findings = append(res.Findings, findings...)
	}
	return res
}

func scanSourceWithFS(fsys FS, src ScanSource) ([]Server, []Finding) {
	data, err := fsys.ReadFile(src.Path)
	if err != nil {
		return nil, []Finding{{
			Client:  src.Client,
			Path:    src.Path,
			Status:  StatusUnsupported,
			Message: fmt.Sprintf("read failed: %v", err),
		}}
	}
	candidates := normalizeKey(src.Key)
	isOpenCode := src.Client == ClientOpenCode

	entries, err := parseConfigFile(data, candidates)
	if err != nil {
		return nil, []Finding{{
			Client:  src.Client,
			Path:    src.Path,
			Status:  StatusUnsupported,
			Message: err.Error(),
		}}
	}

	var (
		servers  []Server
		findings []Finding
	)
	for name, entry := range entries {
		command := entry.CommandOrURL()
		transport := entry.TransportValue()

		// An entry with neither command nor url cannot be launched or
		// connected — report it instead of silently skipping.
		if command == "" {
			findings = append(findings, Finding{
				Client:  src.Client,
				Path:    src.Path,
				Status:  StatusUnsupported,
				Message: fmt.Sprintf("server %q is missing both command and url", name),
			})
			continue
		}
		if isOpenCode && !strings.EqualFold(entry.Type, "local") && !strings.EqualFold(entry.Type, "remote") && entry.Type != "" {
			findings = append(findings, Finding{
				Client:  src.Client,
				Path:    src.Path,
				Status:  StatusApproximate,
				Message: fmt.Sprintf("server %q has unknown type %q, treated as local", name, entry.Type),
			})
		}

		env := entry.MergedEnv()
		s := Server{
			Name:       name,
			Client:     string(src.Client),
			Transport:  transport,
			Command:    command,
			Args:       entry.Args,
			URL:        entry.URL,
			ConfigPath: src.Path,
			Env:        env,
		}
		for k, v := range env {
			s.EnvKeys = append(s.EnvKeys, k)
			s.EnvValues = append(s.EnvValues, v)
		}
		servers = append(servers, s)
	}
	return servers, findings
}

// normalizeKey returns the fallback candidate list for a source key:
// the explicit key (or "mcpServers") first, then the known alternates.
func normalizeKey(key string) []string {
	k := key
	if k == "" {
		k = "mcpServers"
	}
	candidates := []string{k}
	for _, alt := range []string{"mcpServers", "mcp_servers", "mcp"} {
		if alt != k {
			candidates = append(candidates, alt)
		}
	}
	return candidates
}
