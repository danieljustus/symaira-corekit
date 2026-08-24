package mcpserver_test

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	"github.com/danieljustus/symaira-corekit/mcpserver"
)

func ExampleNew() {
	srv := mcpserver.New("my-tools", "1.0.0")
	srv.SetInstructions("Use these tools to help the user.")

	srv.RegisterTool(&mcpserver.Tool{
		Name:        "greet",
		Description: "Greet someone by name",
		InputSchema: json.RawMessage(`{"type":"object","properties":{"name":{"type":"string"}}}`),
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			return "Hello, world!", nil
		},
	})

	// In a real server you would call:
	// srv.ServeStdio(context.Background())
	fmt.Println("server ready")
	// Output: server ready
}

func ExampleServer_RegisterTool() {
	srv := mcpserver.New("demo", "1.0.0")
	srv.RegisterTool(&mcpserver.Tool{
		Name:        "echo",
		Description: "Echoes input back",
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			return fmt.Sprintf("echo: %s", string(input)), nil
		},
	})
	// The "echo" tool is now available to MCP clients.

	// To run a server on stdio:
	_ = os.Stdin
	_ = os.Stdout
	_ = srv
}
