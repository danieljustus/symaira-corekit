// Command foundation generates executable RUST-002 vectors from production Go APIs.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/danieljustus/symaira-corekit/configkit"
	"github.com/danieljustus/symaira-corekit/envutil"
	"github.com/danieljustus/symaira-corekit/exitcodes"
	"github.com/danieljustus/symaira-corekit/logkit"
	"github.com/danieljustus/symaira-corekit/versionkit"
)

type config struct {
	Server  server         `json:"server"`
	Debug   bool           `json:"debug"`
	Name    string         `json:"name"`
	Timeout int            `json:"timeout"`
	Rate    float64        `json:"rate"`
	TTL     time.Duration  `json:"ttl"`
	Tags    []string       `json:"tags"`
	Allowed map[string]int `json:"allowed"`
}
type server struct {
	Port int    `json:"port"`
	Host string `json:"host"`
}
type typedConfig struct {
	Optional *string `json:"optional"`
	Maximum  uint64  `json:"maximum"`
}

func typedDefaults() *typedConfig { return &typedConfig{} }

func defaults() *config {
	return &config{Server: server{Port: 8080, Host: "localhost"}, Name: "default-app", Timeout: 30, Rate: 1.5, TTL: 15 * time.Minute, Tags: []string{"default"}, Allowed: map[string]int{}}
}
func nonemptyMapDefaults() *config {
	value := defaults()
	value.Allowed = map[string]int{"existing": 1}
	return value
}

func main() {
	vectors := map[string]any{
		"VER-001": versionVectors()[0], "VER-002": versionVectors()[1],
		"EXIT-001": exitVectors()[0], "EXIT-002": exitVectors()[1], "EXIT-003": exitVectors()[2], "EXIT-004": exitVectors()[3],
		"ENV-001": envVectors()[0], "ENV-002": envVectors()[1],
	}
	for key, value := range logVectors() {
		vectors[key] = value
	}
	for key, value := range configVectors() {
		vectors[key] = value
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(vectors); err != nil {
		fatal("encode vectors: %v", err)
	}
}

func versionVectors() []map[string]any {
	info := versionkit.New("symx", "v1.2.3", 7)
	jsonBytes, err := info.JSON()
	if err != nil {
		fatal("version JSON: %v", err)
	}
	htmlBytes, err := versionkit.New("<&>", "v<1>&", 7).JSON()
	if err != nil {
		fatal("version HTML JSON: %v", err)
	}
	var written bytes.Buffer
	if err := info.Write(&written); err != nil {
		fatal("version write: %v", err)
	}
	return []map[string]any{{"json": string(jsonBytes), "html_json": string(htmlBytes)}, {"text": info.String(), "write": written.String()}}
}
func exitVectors() []map[string]any {
	codes := map[string]int{"ok": int(exitcodes.ExitOK), "generic": int(exitcodes.ExitGeneric), "no_input": int(exitcodes.ExitNoInput), "no_auth": int(exitcodes.ExitNoAuth), "forbidden": int(exitcodes.ExitForbidden), "not_found": int(exitcodes.ExitNotFound), "conflict": int(exitcodes.ExitConflict), "software": int(exitcodes.ExitSoftware), "data": int(exitcodes.ExitData), "config": int(exitcodes.ExitConfig), "interrupted": int(exitcodes.ExitInterrupted)}
	cause := fmt.Errorf("underlying issue")
	wrapped := exitcodes.Wrap(cause, exitcodes.ExitGeneric, exitcodes.KindInternal, "operation failed")
	inner := &exitcodes.CLIError{Code: exitcodes.ExitNotFound, Kind: exitcodes.KindNotFound, Message: "entry missing", Hint: "list entries"}
	outer := exitcodes.Wrap(inner, exitcodes.ExitGeneric, exitcodes.KindInternal, "read failed")
	nonCLIOuter := fmt.Errorf("context: %w", inner)
	return []map[string]any{
		{"codes": codes, "invalid": int(exitcodes.ExitCode(255))},
		{"error": wrapped.Error(), "cause": wrapped.Unwrap().Error()},
		{"nil": int(exitcodes.ExitCodeFromError(nil)), "plain": int(exitcodes.ExitCodeFromError(fmt.Errorf("plain"))), "typed": int(exitcodes.ExitCodeFromError(inner)), "wrapped": int(exitcodes.ExitCodeFromError(outer))},
		{"nil": exitcodes.FormatCLIError(nil), "plain": exitcodes.FormatCLIError(fmt.Errorf("plain")), "nested_hint": exitcodes.FormatCLIError(outer), "non_cli_wrapper": exitcodes.FormatCLIError(nonCLIOuter)},
	}
}
func envVectors() []map[string]any {
	_ = os.Setenv("RUST002_PRIMARY", "primary")
	_ = os.Setenv("RUST002_ALIAS_ONE", "alias-one")
	_ = os.Setenv("RUST002_TARGET", "gone")
	_ = os.Setenv("RUST002_OTHER", "kept")
	alias := envutil.Getenv("RUST002_PRIMARY", "RUST002_ALIAS_ONE")
	missing := envutil.Getenv("RUST002_MISSING", "RUST002_ALIAS_ONE")
	if err := envutil.Unsetenv("RUST002_TARGET"); err != nil {
		fatal("unsetenv: %v", err)
	}
	return []map[string]any{{"primary": alias, "alias": envutil.Getenv("RUST002_MISSING", "RUST002_ALIAS_ONE"), "missing": missing}, {"target": os.Getenv("RUST002_TARGET"), "other": os.Getenv("RUST002_OTHER")}}
}
func logVectors() map[string]map[string]any {
	levels := map[string]string{}
	for _, input := range []string{"debug", "info", "warn", "warning", "error", "bogus", ""} {
		_ = os.Setenv("RUST002_LEVEL_LOG_LEVEL", input)
		logger := logkit.NewFromEnv("rust002_level")
		switch {
		case logger.Enabled(context.Background(), slog.LevelDebug):
			levels[input] = slog.LevelDebug.String()
		case logger.Enabled(context.Background(), slog.LevelInfo):
			levels[input] = slog.LevelInfo.String()
		case logger.Enabled(context.Background(), slog.LevelWarn):
			levels[input] = slog.LevelWarn.String()
		default:
			levels[input] = slog.LevelError.String()
		}
	}
	fixed := time.Date(2024, 1, 2, 3, 4, 5, 678901234, time.UTC)
	var text bytes.Buffer
	textHandler := logkit.New(&text, slog.LevelInfo, "text").Handler()
	if textHandler.Enabled(context.Background(), slog.LevelDebug) {
		_ = textHandler.Handle(context.Background(), slog.NewRecord(fixed, slog.LevelDebug, "hidden", 0))
	}
	record := slog.NewRecord(fixed, slog.LevelInfo, "hello", 0)
	record.AddAttrs(slog.String("path", "a\nb"), slog.Group("request", slog.String("id", "x"), slog.Bool("ok", true)))
	_ = textHandler.Handle(context.Background(), record)
	var jsonOut bytes.Buffer
	jsonHandler := logkit.New(&jsonOut, slog.LevelDebug, "json").Handler()
	jsonRecord := slog.NewRecord(fixed, slog.LevelDebug, "quoted \"message\"", 0)
	jsonRecord.AddAttrs(slog.Int("count", 3), slog.String("newline", "a\nb"), slog.Group("request", slog.String("id", "x")))
	_ = jsonHandler.Handle(context.Background(), jsonRecord)
	var unicodeJSON bytes.Buffer
	unicodeHandler := logkit.New(&unicodeJSON, slog.LevelInfo, "json").Handler()
	unicodeRecord := slog.NewRecord(fixed, slog.LevelInfo, "line\u2028paragraph\u2029", 0)
	unicodeRecord.AddAttrs(
		slog.String("key\u2028", "value\u2029"),
		slog.Any("nested", map[string]any{"value": "nested\u2028"}),
	)
	_ = unicodeHandler.Handle(context.Background(), unicodeRecord)
	var control bytes.Buffer
	controlHandler := logkit.New(&control, slog.LevelDebug, "text").Handler()
	controlRecord := slog.NewRecord(fixed, slog.LevelInfo, "nul\x00message", 0)
	controlRecord.AddAttrs(
		slog.String("value", "nul\x00value"),
		slog.String("bad key=", "quoted"),
	)
	_ = controlHandler.Handle(context.Background(), controlRecord)
	_ = os.Setenv("RUST002_LOG_LEVEL", "debug")
	_ = os.Setenv("RUST002_LOG_FORMAT", "json")
	logger := logkit.NewFromEnv("rust002")
	return map[string]map[string]any{
		"LOG-001": {"levels": levels}, "LOG-002": {"output": text.String(), "control_output": control.String()}, "LOG-003": {"output": jsonOut.String(), "unicode_output": unicodeJSON.String()},
		"LOG-004": {"enabled_debug": logger.Enabled(context.Background(), slog.LevelDebug), "format": "json"},
	}
}
func configVectors() map[string]map[string]any {
	root, err := os.MkdirTemp("", "rust002-config-")
	if err != nil {
		fatal("temp config: %v", err)
	}
	defer os.RemoveAll(root)
	home, xdg := filepath.Join(root, "home"), filepath.Join(root, "xdg")
	if err := os.MkdirAll(home, 0o700); err != nil {
		fatal("home dir: %v", err)
	}
	_ = os.Setenv("HOME", home)
	_ = os.Setenv("USERPROFILE", home)
	_ = os.Setenv("XDG_CONFIG_HOME", xdg)
	path := configkit.DefaultPath("symx")
	_ = os.Setenv("XDG_CONFIG_HOME", "relative")
	legacyFallback := configkit.DefaultPath("symx")
	_ = os.Setenv("XDG_CONFIG_HOME", xdg)
	missing := defaults()
	missingLoader := configkit.NewLoader(configkit.Options{AppName: "rust002-missing"}, defaults)
	loaded, missingErr := missingLoader.Load()
	if missingErr == nil {
		missing = loaded
	}
	oldCwd, _ := os.Getwd()
	defer os.Chdir(oldCwd)
	if err := os.Chdir(root); err != nil {
		fatal("cwd: %v", err)
	}
	globalDir := filepath.Join(xdg, "rust002_cfg")
	if err := os.MkdirAll(globalDir, 0o700); err != nil {
		fatal("global dir: %v", err)
	}
	if err := os.WriteFile(filepath.Join(globalDir, "config.toml"), []byte("name=\"global\"\ntimeout=40\n[server]\nport=9000\n"), 0o600); err != nil {
		fatal("global: %v", err)
	}
	if err := os.WriteFile(".rust002_cfg.toml", []byte("name=\"project\"\n[server]\nhost=\"remote\"\n"), 0o600); err != nil {
		fatal("project: %v", err)
	}
	_ = os.Setenv("RUST002_CFG_NAME", "environment")
	precedence, precedenceErr := configkit.NewLoader(configkit.Options{AppName: "rust002_cfg"}, defaults).Load()
	if precedenceErr != nil {
		fatal("precedence: %v", precedenceErr)
	}
	bools := map[string]bool{}
	for _, value := range []string{"t", "T", "true", "TRUE", "True", "1", "f", "F", "false", "FALSE", "False", "0"} {
		_ = os.Setenv("RUST002_BOOL_DEBUG", value)
		cfg, err := configkit.NewLoader(configkit.Options{AppName: "rust002_bool"}, defaults).Load()
		if err != nil {
			fatal("bool %s: %v", value, err)
		}
		bools[value] = cfg.Debug
	}
	_ = os.Setenv("RUST002_DUR_TTL", "-1.5s")
	negative, negativeErr := configkit.NewLoader(configkit.Options{AppName: "rust002_dur"}, defaults).Load()
	_ = os.Setenv("RUST002_DUR_OVERFLOW_TTL", "999999999999999999999h")
	_, overflowErr := configkit.NewLoader(configkit.Options{AppName: "rust002_dur_overflow"}, defaults).Load()
	durationStrings := map[string]string{
		"1500ns":    time.Duration(1500).String(),
		"1500000ns": time.Duration(1_500_000).String(),
		"-1500ns":   time.Duration(-1500).String(),
	}
	_ = os.Setenv("RUST002_TYPED_OPTIONAL", "123")
	_ = os.Setenv("RUST002_TYPED_MAXIMUM", "18446744073709551615")
	typed, typedErr := configkit.NewLoader(configkit.Options{AppName: "rust002_typed"}, typedDefaults).Load()
	if typedErr != nil {
		fatal("typed env: %v", typedErr)
	}
	if err := os.WriteFile(".rust002-map.toml", []byte("[allowed]\nadmin=3\n"), 0o600); err != nil {
		fatal("map: %v", err)
	}
	_, mapErr := configkit.NewLoader(configkit.Options{AppName: "rust002-map"}, nonemptyMapDefaults).Load()
	_ = os.Setenv("RUST002_MAP_ENV_ALLOWED_EXISTING", "4")
	mapEnv, mapEnvErr := configkit.NewLoader(configkit.Options{AppName: "rust002_map_env"}, nonemptyMapDefaults).Load()
	firstLoader := configkit.NewLoader(configkit.Options{AppName: "rust002_cache"}, defaults)
	first, firstErr := firstLoader.Load()
	second, secondErr := firstLoader.Load()
	reloaded, reloadErr := firstLoader.Reload()
	firstLoader.ResetCache()
	reset, resetErr := firstLoader.Load()
	cacheOK := firstErr == nil && secondErr == nil && reloadErr == nil && resetErr == nil
	cacheValues := map[string]any{"load_same": cacheOK && first == second, "reload_new": cacheOK && first != reloaded, "reset_new": cacheOK && reloaded != reset}
	return map[string]map[string]any{
		"CFG-001": {"xdg": normalizeFixturePath(path, root), "relative_xdg": normalizeFixturePath(legacyFallback, root), "legacy": normalizeFixturePath(filepath.Join(home, ".config", "symx", "config.toml"), root), "windows_home_env": "USERPROFILE"},
		"CFG-002": {"defaults": missing, "missing_file_error": missingErr == nil},
		"CFG-003": {"name": precedence.Name, "timeout": precedence.Timeout, "port": precedence.Server.Port, "host": precedence.Server.Host},
		"CFG-004": {"bools": bools, "negative_duration": durationString(negative, negativeErr), "overflow_error": overflowErr != nil, "duration_strings": durationStrings, "optional_string": *typed.Optional, "maximum_u64": typed.Maximum},
		"CFG-005": {"zero_preserved": true},
		"CFG-006": {"map_error": mapErr != nil, "map_mentions_field": mapErr != nil && strings.Contains(mapErr.Error(), "allowed"), "env_map_unchanged": mapEnvErr == nil && mapEnv.Allowed["existing"] == 1},
		"CFG-007": cacheValues,
	}
}
func normalizeFixturePath(path, root string) string {
	normalized := filepath.ToSlash(path)
	return strings.Replace(normalized, filepath.ToSlash(root), "/fixture", 1)
}
func durationString(value *config, err error) string {
	if err != nil {
		return "error: " + err.Error()
	}
	return value.TTL.String()
}
func errorString(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}
func fatal(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "foundation: "+format+"\n", args...)
	os.Exit(1)
}
