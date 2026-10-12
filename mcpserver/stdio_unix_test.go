//go:build unix

package mcpserver

import (
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func TestServeStdioWriteFailureWithOpenInput(t *testing.T) {
	if root := os.Getenv("MCP_STDIO_FAILURE_HELPER"); root != "" {
		server := New("stdio-regression", "test")
		server.RegisterTool(&Tool{Name: "slow", Handler: func(ctx context.Context, _ json.RawMessage) (any, error) {
			// #nosec G703 -- helper env contains only the parent test's t.TempDir.
			if err := os.WriteFile(filepath.Join(root, "ready"), nil, 0o600); err != nil {
				os.Exit(3)
			}
			<-ctx.Done()
			// #nosec G703 -- helper env contains only the parent test's t.TempDir.
			if err := os.WriteFile(filepath.Join(root, "cancelled"), nil, 0o600); err != nil {
				os.Exit(3)
			}
			return nil, ctx.Err()
		}})
		server.RegisterTool(&Tool{Name: "fast", Handler: func(context.Context, json.RawMessage) (any, error) {
			return "done", nil
		}})
		if err := server.ServeStdio(context.Background()); err != nil {
			os.Exit(1)
		}
		os.Exit(0)
	}
	for _, followup := range []string{
		`{"jsonrpc":"2.0","id":2,"method":"ping"}`,
		`{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"fast","arguments":{}}}`,
	} {
		root := t.TempDir()
		output := filepath.Join(root, "stdout")
		if err := os.WriteFile(output, nil, 0o600); err != nil {
			t.Fatal(err)
		}
		// #nosec G304 -- output is a fixed file inside this test's t.TempDir.
		readonly, err := os.Open(output)
		if err != nil {
			t.Fatal(err)
		}
		defer readonly.Close()
		binary, err := os.Executable()
		if err != nil {
			t.Fatal(err)
		}
		// #nosec G204 -- binary is os.Executable, the current test executable.
		command := exec.Command(binary, "-test.run=^TestServeStdioWriteFailureWithOpenInput$")
		command.Env = []string{"MCP_STDIO_FAILURE_HELPER=" + root, "HOME=" + root, "PATH=" + root}
		command.Stdout = readonly
		command.Stderr = os.Stderr
		stdin, err := command.StdinPipe()
		if err != nil {
			t.Fatal(err)
		}
		if err := command.Start(); err != nil {
			t.Fatal(err)
		}
		wait := make(chan error, 1)
		go func() { wait <- command.Wait() }()
		t.Cleanup(func() {
			_ = stdin.Close()
			_ = command.Process.Kill()
		})
		if _, err := stdin.Write([]byte(`{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"slow","arguments":{}}}` + "\n")); err != nil {
			t.Fatal(err)
		}
		deadline := time.Now().Add(5 * time.Second)
		for {
			if _, err := os.Stat(filepath.Join(root, "ready")); err == nil {
				break
			}
			if time.Now().After(deadline) {
				_ = command.Process.Kill()
				<-wait
				t.Fatal("tool did not reach readiness")
			}
			time.Sleep(5 * time.Millisecond)
		}
		if _, err := stdin.Write([]byte(followup + "\n")); err != nil {
			t.Fatal(err)
		}
		select {
		case err := <-wait:
			if err == nil || command.ProcessState.ExitCode() != 1 {
				t.Fatalf("expected propagated write failure, got %v", err)
			}
		case <-time.After(5 * time.Second):
			_ = command.Process.Kill()
			<-wait
			t.Fatal("stdio abort required client EOF")
		}
		if _, err := os.Stat(filepath.Join(root, "cancelled")); err != nil {
			t.Fatal("in-flight tool was not cancelled:", err)
		}
		_ = stdin.Close()
	}
}
