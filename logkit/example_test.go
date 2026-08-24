package logkit_test

import (
	"os"

	"github.com/danieljustus/symaira-corekit/logkit"
)

func ExampleNew() {
	// Create a JSON logger writing to stderr at INFO level.
	logger := logkit.New(os.Stderr, 0, "json")
	logger.Info("server started", "addr", ":8080")
}
