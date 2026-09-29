package main

import (
	"context"
	"fmt"
	"net"
	"os"
	"syscall"
	"testing"
)

func TestClassifyNativeRefusalAndDeadline(t *testing.T) {
	refused := fmt.Errorf("request latest release: %w", &net.OpError{
		Op: "dial", Net: "tcp", Err: os.NewSyscallError("connectex", syscall.ECONNREFUSED),
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
