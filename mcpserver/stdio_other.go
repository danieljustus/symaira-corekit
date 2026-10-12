//go:build !unix

package mcpserver

import (
	"context"
	"os"
)

func (s *Server) serveStdio(ctx context.Context) error {
	return s.ServeIO(ctx, os.Stdin, os.Stdout)
}
