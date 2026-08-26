package llmkit

import (
	"os/exec"
)

// execCommand is a small indirection over exec.Command so tests can replace
// the symvault resolution path.
//
//nolint:gosec // G204: the binary name is the fixed "symvault", only the vault path varies
var execCommand = func(name string, args ...string) *exec.Cmd {
	return exec.Command(name, args...)
}
