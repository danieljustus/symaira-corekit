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

// fallbackApp is the neutral env prefix used by Default() when InitDefault has
// not been called. It is intentionally product-agnostic ("SYM_LOG_LEVEL" /
// "SYM_LOG_FORMAT") so a shared consumer never silently inherits another tool's
// configuration. Call InitDefault(appName) at startup to use the app's own prefix.
const fallbackApp = "sym"

var (
	defaultMu     sync.Mutex
	defaultApp    string
	defaultLogger *slog.Logger
)

// InitDefault sets the application name that Default() uses to read its
// environment configuration. Call it once at program startup, before the first
// Default() call. It resets any previously constructed default logger so the
// next Default() call rebuilds it with the new prefix.
//
// For example, InitDefault("symfetch") makes Default() read SYMFETCH_LOG_LEVEL
// and SYMFETCH_LOG_FORMAT.
func InitDefault(appName string) {
	defaultMu.Lock()
	defer defaultMu.Unlock()
	defaultApp = appName
	defaultLogger = nil
}

// Default returns the package-default structured logger configured via
// environment variables. It is safe for concurrent use.
//
// The env prefix is the app name passed to InitDefault (uppercased); if
// InitDefault was not called it falls back to the neutral "SYM" prefix:
//   - {PREFIX}_LOG_LEVEL: debug, info, warn, error (default: warn)
//   - {PREFIX}_LOG_FORMAT: text (default), json
func Default() *slog.Logger {
	defaultMu.Lock()
	defer defaultMu.Unlock()
	if defaultLogger == nil {
		app := defaultApp
		if app == "" {
			app = fallbackApp
		}
		defaultLogger = NewFromEnv(app)
	}
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
	defaultMu.Lock()
	old := defaultLogger
	defaultLogger = l
	defaultMu.Unlock()
	return func() {
		defaultMu.Lock()
		defaultLogger = old
		defaultMu.Unlock()
	}
}
