package mcpserver

import (
	"bufio"
	"bytes"
	"fmt"
	"testing"
)

func FuzzReadRequest(f *testing.F) {
	framedBody := []byte(`{"jsonrpc":"2.0","id":1,"method":"ping"}`)
	f.Add([]byte(fmt.Sprintf("Content-Length: %d\r\n\r\n%s", len(framedBody), framedBody)))
	f.Add([]byte(`{"jsonrpc":"2.0","id":1,"method":"ping"}` + "\n"))
	f.Add([]byte("Content-Length: 100\r\n\r\n{}"))
	f.Add([]byte("Content-Length: 1\r\n\r\n"))
	f.Add([]byte("Content-Length: 1048577\r\n\r\n"))
	f.Add([]byte{'{', '"', 'm', 'e', 't', 'h', 'o', 'd', '"', ':', ' ', 0xff, '}'})

	f.Fuzz(func(t *testing.T, input []byte) {
		br := bufio.NewReader(bytes.NewReader(input))
		_, _, _ = readRequest(br)
	})
}
