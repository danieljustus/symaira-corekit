package logkit

import (
	"bytes"
	"log/slog"
	"strings"
	"testing"
)

func TestParseLevel_Debug(t *testing.T) {
	if got := parseLevel("debug"); got != slog.LevelDebug {
		t.Errorf("parseLevel(%q) = %v, want %v", "debug", got, slog.LevelDebug)
	}
}

func TestParseLevel_Info(t *testing.T) {
	if got := parseLevel("info"); got != slog.LevelInfo {
		t.Errorf("parseLevel(%q) = %v, want %v", "info", got, slog.LevelInfo)
	}
}

func TestParseLevel_Warn(t *testing.T) {
	if got := parseLevel("warn"); got != slog.LevelWarn {
		t.Errorf("parseLevel(%q) = %v, want %v", "warn", got, slog.LevelWarn)
	}
}

func TestParseLevel_Warning(t *testing.T) {
	if got := parseLevel("warning"); got != slog.LevelWarn {
		t.Errorf("parseLevel(%q) = %v, want %v", "warning", got, slog.LevelWarn)
	}
}

func TestParseLevel_Error(t *testing.T) {
	if got := parseLevel("error"); got != slog.LevelError {
		t.Errorf("parseLevel(%q) = %v, want %v", "error", got, slog.LevelError)
	}
}

func TestParseLevel_Empty(t *testing.T) {
	if got := parseLevel(""); got != slog.LevelWarn {
		t.Errorf("parseLevel(%q) = %v, want %v", "", got, slog.LevelWarn)
	}
}

func TestParseLevel_Unknown(t *testing.T) {
	if got := parseLevel("bogus"); got != slog.LevelWarn {
		t.Errorf("parseLevel(%q) = %v, want %v", "bogus", got, slog.LevelWarn)
	}
}

func TestParseLevel_CaseInsensitive(t *testing.T) {
	if got := parseLevel("  DEBUG  "); got != slog.LevelDebug {
		t.Errorf("parseLevel(%q) = %v, want %v", "  DEBUG  ", got, slog.LevelDebug)
	}
}

func TestNew_TextFormat(t *testing.T) {
	var buf bytes.Buffer
	l := New(&buf, slog.LevelInfo, "text")
	l.Info("hello")

	out := buf.String()
	if !strings.Contains(out, "hello") {
		t.Errorf("expected output to contain %q, got %q", "hello", out)
	}
	if !strings.Contains(out, "level=INFO") {
		t.Errorf("expected level=INFO in output, got %q", out)
	}
}

func TestNew_JSONFormat(t *testing.T) {
	var buf bytes.Buffer
	l := New(&buf, slog.LevelDebug, "json")
	l.Debug("test msg")

	out := buf.String()
	if !strings.Contains(out, "test msg") {
		t.Errorf("expected output to contain %q, got %q", "test msg", out)
	}
	if !strings.Contains(out, `"level"`) {
		t.Errorf("expected JSON level key in output, got %q", out)
	}
}

func TestNew_FilterBelowLevel(t *testing.T) {
	var buf bytes.Buffer
	l := New(&buf, slog.LevelError, "text")
	l.Info("should not appear")

	if buf.Len() != 0 {
		t.Errorf("expected no output for filtered message, got %q", buf.String())
	}
}

func TestNewFromEnv(t *testing.T) {
	t.Setenv("TESTAPP_LOG_LEVEL", "debug")
	t.Setenv("TESTAPP_LOG_FORMAT", "json")

	var buf bytes.Buffer
	l := NewFromEnv("testapp")
	_ = l

	l2 := New(&buf, slog.LevelDebug, "json")
	l2.Debug("env test")

	if !strings.Contains(buf.String(), "env test") {
		t.Errorf("expected output, got %q", buf.String())
	}
}

func TestNewFromEnv_Defaults(t *testing.T) {
	var buf bytes.Buffer
	l := New(&buf, slog.LevelWarn, "text")
	l.Info("should not appear")

	if buf.Len() != 0 {
		t.Errorf("expected no output at warn level for info message, got %q", buf.String())
	}
}

func TestReplaceLogger(t *testing.T) {
	var buf bytes.Buffer
	original := defaultLogger

	custom := New(&buf, slog.LevelInfo, "text")
	restore := ReplaceLogger(custom)
	defaultLogger.Info("replaced")

	if !strings.Contains(buf.String(), "replaced") {
		t.Errorf("expected replaced logger to write, got %q", buf.String())
	}

	restore()
	if defaultLogger != original {
		t.Error("restore did not restore original logger")
	}
}

func TestInitDefaultUsesAppPrefix(t *testing.T) {
	t.Setenv("SYMFETCH_LOG_LEVEL", "debug")

	restore := ReplaceLogger(nil) // park current default so we can rebuild it
	defer restore()

	InitDefault("symfetch")
	got := Default()
	if got == nil {
		t.Fatal("Default() returned nil after InitDefault")
	}
	if !got.Enabled(nil, slog.LevelDebug) {
		t.Error("expected debug level from SYMFETCH_LOG_LEVEL, but debug is disabled")
	}

	// Reset to avoid leaking the configured app into other tests.
	InitDefault("")
}

func TestDefaultFallbackPrefixIsNeutral(t *testing.T) {
	t.Setenv("SYM_LOG_LEVEL", "error")

	InitDefault("") // no app configured -> neutral "SYM" prefix
	got := Default()
	if got.Enabled(nil, slog.LevelWarn) {
		t.Error("expected error level from SYM_LOG_LEVEL, but warn is enabled")
	}
	InitDefault("")
	ReplaceLogger(nil)()
}
