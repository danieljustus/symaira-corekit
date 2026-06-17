// Package logkit provides structured logging helpers for CLI applications.
package logkit

import (
	"io"
	"log/slog"
	"os"
	"strings"
	"sync"

	"github.com/danieljustus/symaira-corekit/envutil"
)

var (
	defaultLogger *slog.Logger
	initOnce      sync.Once
)

// Default returns the package-default structured logger configured via
// environment variables. It is safe for concurrent use.
//
// Environment variables (using "symvault" as example appName):
//   - SYMVAULT_LOG_LEVEL: debug, info, warn, error (default: warn)
//   - SYMVAULT_LOG_FORMAT: text (default), json
func Default() *slog.Logger {
	initOnce.Do(func() {
		defaultLogger = NewFromEnv("symvault")
	})
	return defaultLogger
}

// NewFromEnv creates a fresh slog.Logger by reading environment variables
// prefixed with the given appName. For example, NewFromEnv("symfetch")
// reads SYMFETCH_LOG_LEVEL and SYMFETCH_LOG_FORMAT.
func NewFromEnv(appName string) *slog.Logger {
	prefix := strings.ToUpper(appName)
	level := parseLevel(envutil.Getenv(prefix + "_LOG_LEVEL"))
	format := strings.ToLower(envutil.Getenv(prefix + "_LOG_FORMAT"))
	if format == "" {
		format = "text"
	}

	return New(os.Stderr, level, format)
}

// New creates a slog.Logger with the specified writer, level and format.
// Format must be "text" or "json".
func New(w io.Writer, level slog.Level, format string) *slog.Logger {
	opts := &slog.HandlerOptions{
		Level: level,
	}

	var handler slog.Handler
	switch format {
	case "json":
		handler = slog.NewJSONHandler(w, opts)
	default:
		handler = slog.NewTextHandler(w, opts)
	}

	return slog.New(handler)
}

func parseLevel(s string) slog.Level {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "debug":
		return slog.LevelDebug
	case "info":
		return slog.LevelInfo
	case "error":
		return slog.LevelError
	case "warn", "warning":
		return slog.LevelWarn
	default:
		return slog.LevelWarn
	}
}

// ReplaceLogger allows tests to swap the default logger.
// The returned function restores the previous logger.
func ReplaceLogger(l *slog.Logger) func() {
	old := defaultLogger
	defaultLogger = l
	return func() { defaultLogger = old }
}
