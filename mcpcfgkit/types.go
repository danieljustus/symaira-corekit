package mcpcfgkit

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
)

// Status describes how completely a client's MCP configuration source was
// mapped during a scan.
type Status string

const (
	// StatusExact means the source was fully mapped to server entries.
	StatusExact Status = "exact"
	// StatusApproximate means the source was mapped with assumptions.
	StatusApproximate Status = "approximate"
	// StatusManual means the source requires manual review.
	StatusManual Status = "manual"
	// StatusUnsupported means the source could not be mapped at all.
	StatusUnsupported Status = "unsupported"
)

// Finding reports a client config source (or an entry within it) that could
// not be mapped exactly. It names the client, the source path, a status, and
// a human-readable message.
type Finding struct {
	Client  Client
	Path    string
	Status  Status
	Message string
}

func (f Finding) String() string {
	return fmt.Sprintf("%s (%s): [%s] %s", f.Client, f.Path, f.Status, f.Message)
}

// Client identifies a supported AI client application.
type Client string

const (
	ClientHermes        Client = "hermes"
	ClientClaudeDesktop Client = "claude-desktop"
	ClientCursor        Client = "cursor"
	ClientVSCode        Client = "vscode"
	ClientOpenCode      Client = "opencode"
)

// Transport describes how a server is reached.
type Transport string

const (
	TransportStdio Transport = "stdio"
	TransportHTTP  Transport = "http"
)

// ScanSource pairs a client identifier with its config path and the top-level
// key holding the servers map (empty Key means "mcpServers").
type ScanSource struct {
	Client Client
	Path   string
	Key    string
}

// Source is the simpler V1 alias of ScanSource (plain-string client field)
// kept for the Discover convenience API. It shares the same layout so both
// APIs can share internals.
type Source = ScanSource

// DefaultSources returns the well-known client config locations for the
// current platform and user. Missing files are tolerated by scan/discover.
func DefaultSources() []ScanSource {
	return defaultSourcesFor(runtime.GOOS, homeDir())
}

func defaultSourcesFor(goos, home string) []ScanSource {
	sources := []ScanSource{
		{Client: ClientHermes, Path: filepath.Join(home, ".config", "hermes", "config.json"), Key: "mcpServers"},
		{Client: ClientCursor, Path: filepath.Join(home, ".cursor", "mcp.json"), Key: "mcpServers"},
		{Client: ClientVSCode, Path: filepath.Join(home, ".vscode", "mcp.json"), Key: "mcpServers"},
		{Client: ClientOpenCode, Path: filepath.Join(home, ".config", "opencode", "config.json"), Key: "mcp"},
	}
	if goos == "darwin" {
		sources = append(sources, ScanSource{
			Client: ClientClaudeDesktop,
			Path:   filepath.Join(home, "Library", "Application Support", "Claude", "claude_desktop_config.json"),
			Key:    "mcpServers",
		})
	} else {
		xdg := os.Getenv("XDG_CONFIG_HOME")
		if xdg == "" {
			xdg = filepath.Join(home, ".config")
		}
		sources = append(sources, ScanSource{
			Client: ClientClaudeDesktop,
			Path:   filepath.Join(xdg, "claude", "claude_desktop_config.json"),
			Key:    "mcpServers",
		})
	}
	return sources
}

// homeDir returns the user's home directory using a best-effort approach.
func homeDir() string {
	if h, err := os.UserHomeDir(); err == nil {
		return h
	}
	if h := os.Getenv("HOME"); h != "" {
		return h
	}
	return "."
}
