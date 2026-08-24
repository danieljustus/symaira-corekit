//nolint:gosec
package ollamakit_test

import (
	"fmt"

	"github.com/danieljustus/symaira-corekit/ollamakit"
)

// ExampleNew demonstrates creating an Ollama client and inspecting its configuration.
func ExampleNew() {
	client := ollamakit.New(ollamakit.Config{
		BaseURL: "http://localhost:11434",
		Model:   "granite-embedding:30m",
	})

	fmt.Println(client.Model())
	// Output:
	// granite-embedding:30m
}

// ExampleNewFromEnv demonstrates creating an Ollama client from environment variables.
func ExampleNewFromEnv() {
	client := ollamakit.NewFromEnv("OLLAMA")
	_ = client
	fmt.Println("client created")
	// Output:
	// client created
}
