// Package versionkit provides the standardized `version --json` payload for
// Symaira CLI tools. GUI clients (symaira-appkit's SymairaToolKit) perform a
// schema handshake against this payload: they call `<tool> version --json`
// and compare schema_version against the contract version they understand.
//
// Tools without this payload are detected with schema_version 0 (usable, no
// contract guarantees). Bump SchemaVersion whenever a tool's machine-readable
// JSON output changes incompatibly.
package versionkit

import (
	"encoding/json"
	"fmt"
	"io"
)

// Info is the handshake payload. Field names are part of the GUI↔core
// contract — do not rename (snake_case per ecosystem convention).
type Info struct {
	Tool          string `json:"tool"`
	Version       string `json:"version"`
	SchemaVersion int    `json:"schema_version"`
}

// New builds the payload for a tool. version is passed through as-is
// (with or without leading "v").
func New(tool, version string, schemaVersion int) Info {
	return Info{Tool: tool, Version: version, SchemaVersion: schemaVersion}
}

// JSON returns the compact single-line encoding.
func (i Info) JSON() ([]byte, error) {
	return json.Marshal(i)
}

// Write emits the compact JSON followed by a newline — the exact bytes a
// `version --json` subcommand should print to stdout.
func (i Info) Write(w io.Writer) error {
	data, err := i.JSON()
	if err != nil {
		return err
	}
	_, err = fmt.Fprintf(w, "%s\n", data)
	return err
}

// String is the human-readable form for the plain `version` subcommand
// (e.g. "symprint v0.1.0"). appkit's fallback parser extracts the version
// token from exactly this shape.
func (i Info) String() string {
	return fmt.Sprintf("%s %s", i.Tool, i.Version)
}
