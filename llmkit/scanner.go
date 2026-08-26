package llmkit

import (
	"bufio"
	"io"
)

// newLineScanner returns a scanner sized for LLM stream lines (some local
// servers emit very long single-line JSON chunks).
func newLineScanner(r io.Reader) *bufio.Scanner {
	s := bufio.NewScanner(r)
	s.Buffer(make([]byte, 0, 64*1024), 4*1024*1024)
	return s
}
