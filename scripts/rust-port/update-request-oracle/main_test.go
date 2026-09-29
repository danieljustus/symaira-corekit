package main

import (
	"context"
	"fmt"
	"net"
	"os"
	"runtime"
	"syscall"
	"testing"
)

func TestClassifyNativeRefusalAndDeadline(t *testing.T) {
	refusalErrno := syscall.ECONNREFUSED
	if runtime.GOOS == "windows" {
		refusalErrno = syscall.Errno(10061)
	}
	refused := fmt.Errorf("request latest release: %w", &net.OpError{
		Op: "dial", Net: "tcp", Err: os.NewSyscallError("connectex", refusalErrno),
	})
	for _, tc := range []struct {
		err  error
		code string
	}{
		{refused, "connection_refused"},
		{fmt.Errorf("request latest release: %w", context.DeadlineExceeded), "timeout"},
	} {
		code, message := classify(tc.err)
		if code != tc.code || message != "request latest release" {
			t.Fatalf("classify: got %q/%q, want %q/request latest release", code, message, tc.code)
		}
	}
}
