package llmkit

import (
	"os/exec"
)

// execCommand is a small indirection over exec.Command so tests can replace
// the symvault resolution path.
var execCommand = func(name string, args ...string) *exec.Cmd {
	return exec.Command(name, args...)
}
