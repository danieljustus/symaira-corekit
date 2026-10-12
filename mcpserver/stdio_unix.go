//go:build unix

package mcpserver

import (
	"context"
	"errors"
	"os"

	"golang.org/x/sys/unix"
)

func (s *Server) serveStdio(ctx context.Context) (retErr error) {
	original := int(os.Stdin.Fd())
	flags, err := unix.FcntlInt(uintptr(original), unix.F_GETFL, 0)
	if err != nil {
		return err
	}
	fd, err := unix.Dup(original)
	if err != nil {
		return err
	}
	unix.CloseOnExec(fd)
	if err := unix.SetNonblock(fd, true); err != nil {
		_ = unix.Close(fd)
		return err
	}
	// NewFile registers an already nonblocking pipe with the runtime poller.
	// Closing this owned handle can then interrupt Read and join the reader.
	input := os.NewFile(uintptr(fd), "stdin")
	defer func() {
		// ServeIO closes input and joins its reader before flags are restored.
		retErr = errors.Join(retErr, unix.SetNonblock(original, flags&unix.O_NONBLOCK != 0))
	}()
	return s.ServeIO(ctx, input, os.Stdout)
}
