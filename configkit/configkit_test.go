package configkit

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type testConfig struct {
	Server  testServerConfig `json:"server"`
	Debug   bool             `json:"debug"`
	Name    string           `json:"name"`
	Timeout int              `json:"timeout"`
	Rate    float64          `json:"rate"`
	TTL     time.Duration    `json:"ttl"`
}

type testServerConfig struct {
	Port    int    `json:"port"`
	Host    string `json:"host"`
	Enabled *bool  `json:"enabled"`
}

func testDefaults() *testConfig {
	return &testConfig{
		Server:  testServerConfig{Port: 8080, Host: "localhost"},
		Debug:   false,
		Name:    "default-app",
		Timeout: 30,
		Rate:    1.5,
		TTL:     15 * time.Minute,
	}
}

func TestDefaultPath(t *testing.T) {
	path := DefaultPath("symfetch")
	if !strings.HasSuffix(path, filepath.Join(".config", "symfetch", "config.toml")) {
		t.Errorf("DefaultPath = %q, want suffix .config/symfetch/config.toml", path)
	}
	if !strings.HasPrefix(path, "/") {
		t.Errorf("DefaultPath = %q, want absolute path", path)
	}
}

func TestLoadDefaults(t *testing.T) {
	loader := NewLoader(Options{AppName: "configkit-test-nodir-xyz"}, testDefaults)
	cfg, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.Server.Port != 8080 {
		t.Errorf("Server.Port = %d, want 8080", cfg.Server.Port)
	}
	if cfg.Server.Host != "localhost" {
		t.Errorf("Server.Host = %q, want %q", cfg.Server.Host, "localhost")
	}
	if cfg.Name != "default-app" {
		t.Errorf("Name = %q, want %q", cfg.Name, "default-app")
	}
	if cfg.TTL != 15*time.Minute {
		t.Errorf("TTL = %v, want %v", cfg.TTL, 15*time.Minute)
	}
}

func TestLoadFromTOML(t *testing.T) {
	dir := t.TempDir()
	tomlPath := filepath.Join(dir, "config.toml")
	content := `
debug = true
name = "toml-app"
timeout = 60
rate = 2.5
ttl = "1h"

[server]
port = 9090
host = "0.0.0.0"
`
	if err := os.WriteFile(tomlPath, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	cfg := testDefaults()
	if err := mergeFile(cfg, tomlPath); err != nil {
		t.Fatalf("mergeFile() error = %v", err)
	}

	if cfg.Server.Port != 9090 {
		t.Errorf("Server.Port = %d, want 9090", cfg.Server.Port)
	}
	if cfg.Server.Host != "0.0.0.0" {
		t.Errorf("Server.Host = %q, want %q", cfg.Server.Host, "0.0.0.0")
	}
	if !cfg.Debug {
		t.Error("Debug = false, want true")
	}
	if cfg.Name != "toml-app" {
		t.Errorf("Name = %q, want %q", cfg.Name, "toml-app")
	}
	if cfg.Timeout != 60 {
		t.Errorf("Timeout = %d, want 60", cfg.Timeout)
	}
	if cfg.Rate != 2.5 {
		t.Errorf("Rate = %f, want 2.5", cfg.Rate)
	}
	if cfg.TTL != time.Hour {
		t.Errorf("TTL = %v, want %v", cfg.TTL, time.Hour)
	}
}

func TestProjectOverride(t *testing.T) {
	dir := t.TempDir()
	origDir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.Chdir(origDir) })

	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}

	projectFile := filepath.Join(dir, ".override-test.toml")
	content := `
name = "project-override"

[server]
port = 3000
`
	if err := os.WriteFile(projectFile, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	loader := NewLoader(Options{AppName: "override-test"}, testDefaults)
	cfg, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.Server.Port != 3000 {
		t.Errorf("Server.Port = %d, want 3000", cfg.Server.Port)
	}
	if cfg.Name != "project-override" {
		t.Errorf("Name = %q, want %q", cfg.Name, "project-override")
	}
	if cfg.Server.Host != "localhost" {
		t.Errorf("Server.Host = %q, want default %q (project file should not override unset)", cfg.Server.Host, "localhost")
	}
}

func TestEnvOverride(t *testing.T) {
	t.Setenv("ENVTEST_NAME", "env-name")
	t.Setenv("ENVTEST_TIMEOUT", "120")
	t.Setenv("ENVTEST_DEBUG", "true")
	t.Setenv("ENVTEST_RATE", "3.14")

	loader := NewLoader(Options{AppName: "envtest"}, testDefaults)
	cfg, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.Name != "env-name" {
		t.Errorf("Name = %q, want %q", cfg.Name, "env-name")
	}
	if cfg.Timeout != 120 {
		t.Errorf("Timeout = %d, want 120", cfg.Timeout)
	}
	if !cfg.Debug {
		t.Error("Debug = false, want true")
	}
	if cfg.Rate != 3.14 {
		t.Errorf("Rate = %f, want 3.14", cfg.Rate)
	}
}

func TestEnvOverrideNested(t *testing.T) {
	t.Setenv("NESTTEST_SERVER_PORT", "5555")
	t.Setenv("NESTTEST_SERVER_HOST", "remote-host")

	loader := NewLoader(Options{AppName: "nesttest"}, testDefaults)
	cfg, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.Server.Port != 5555 {
		t.Errorf("Server.Port = %d, want 5555", cfg.Server.Port)
	}
	if cfg.Server.Host != "remote-host" {
		t.Errorf("Server.Host = %q, want %q", cfg.Server.Host, "remote-host")
	}
}

func TestEnvOverrideCustomPrefix(t *testing.T) {
	t.Setenv("MY_APP_NAME", "custom-prefix-name")

	loader := NewLoader(Options{AppName: "foo", EnvPrefix: "MY_APP"}, testDefaults)
	cfg, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.Name != "custom-prefix-name" {
		t.Errorf("Name = %q, want %q", cfg.Name, "custom-prefix-name")
	}
}

func TestPointerFieldFromTOML(t *testing.T) {
	dir := t.TempDir()
	tomlPath := filepath.Join(dir, "config.toml")

_false := false
	content := `
[server]
port = 7777
enabled = false
`
	if err := os.WriteFile(tomlPath, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	cfg := testDefaults()
	if err := mergeFile(cfg, tomlPath); err != nil {
		t.Fatalf("mergeFile() error = %v", err)
	}

	if cfg.Server.Enabled == nil {
		t.Fatal("Server.Enabled is nil, want non-nil")
	}
	if *cfg.Server.Enabled != false {
		t.Errorf("Server.Enabled = true, want false")
	}
	_ = _false
}

func TestPointerFieldFromEnv(t *testing.T) {
	t.Setenv("PTRTEST_SERVER_ENABLED", "false")

	loader := NewLoader(Options{AppName: "ptrtest"}, testDefaults)
	cfg, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.Server.Enabled == nil {
		t.Fatal("Server.Enabled is nil after env override, want non-nil")
	}
	if *cfg.Server.Enabled != false {
		t.Errorf("Server.Enabled = true, want false")
	}
}

func TestPointerFieldTrueFromEnv(t *testing.T) {
	t.Setenv("PTRTRUE_SERVER_ENABLED", "true")

	loader := NewLoader(Options{AppName: "ptrtrue"}, testDefaults)
	cfg, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.Server.Enabled == nil {
		t.Fatal("Server.Enabled is nil, want non-nil")
	}
	if *cfg.Server.Enabled != true {
		t.Errorf("Server.Enabled = false, want true")
	}
}

func TestReload(t *testing.T) {
	dir := t.TempDir()

	tomlPath := filepath.Join(dir, "config.toml")
	if err := os.WriteFile(tomlPath, []byte(`
name = "version-1"
`), 0o644); err != nil {
		t.Fatal(err)
	}

	loader := NewLoader(Options{AppName: "reloadtest"}, testDefaults)

	cfg1, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	name1 := cfg1.Name

	loader.ResetCache()

	cfg2, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() after reset error = %v", err)
	}

	if cfg2.Name != "default-app" {
		t.Errorf("Name after reset = %q, want %q", cfg2.Name, "default-app")
	}
	_ = name1
}

func TestMissingFileSkipped(t *testing.T) {
	cfg := testDefaults()
	if err := mergeFile(cfg, "/nonexistent/path/config.toml"); err != nil {
		t.Fatalf("mergeFile() should skip missing files, got error = %v", err)
	}
	if cfg.Server.Port != 8080 {
		t.Errorf("Server.Port = %d, want 8080 (defaults preserved)", cfg.Server.Port)
	}
}

func TestBadTOMLError(t *testing.T) {
	dir := t.TempDir()
	tomlPath := filepath.Join(dir, "bad.toml")
	if err := os.WriteFile(tomlPath, []byte(`{{{{invalid toml`), 0o644); err != nil {
		t.Fatal(err)
	}

	cfg := testDefaults()
	err := mergeFile(cfg, tomlPath)
	if err == nil {
		t.Fatal("mergeFile() should return error for bad TOML")
	}
	if !strings.Contains(err.Error(), "failed to parse") {
		t.Errorf("error = %q, want it to contain %q", err.Error(), "failed to parse")
	}
}

func TestTOMLDoesNotOverrideZeroDefaults(t *testing.T) {
	dir := t.TempDir()
	tomlPath := filepath.Join(dir, "config.toml")
	content := `
[server]
host = "toml-host"
`
	if err := os.WriteFile(tomlPath, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	cfg := testDefaults()
	if err := mergeFile(cfg, tomlPath); err != nil {
		t.Fatalf("mergeFile() error = %v", err)
	}

	if cfg.Server.Host != "toml-host" {
		t.Errorf("Server.Host = %q, want %q", cfg.Server.Host, "toml-host")
	}
	// Port was not in TOML, so default should be preserved.
	if cfg.Server.Port != 8080 {
		t.Errorf("Server.Port = %d, want 8080 (default preserved)", cfg.Server.Port)
	}
}

func TestEnvOverridesTOML(t *testing.T) {
	dir := t.TempDir()
	tomlPath := filepath.Join(dir, "config.toml")
	content := `
name = "from-toml"
timeout = 45
`
	if err := os.WriteFile(tomlPath, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	t.Setenv("ENVPREVV_NAME", "from-env")

	cfg := testDefaults()
	if err := mergeFile(cfg, tomlPath); err != nil {
		t.Fatalf("mergeFile() error = %v", err)
	}
	if err := applyEnvOverrides(cfg, "ENVPREVV"); err != nil {
		t.Fatalf("applyEnvOverrides() error = %v", err)
	}

	if cfg.Name != "from-env" {
		t.Errorf("Name = %q, want %q (env should override TOML)", cfg.Name, "from-env")
	}
	if cfg.Timeout != 45 {
		t.Errorf("Timeout = %d, want 45 (TOML value preserved)", cfg.Timeout)
	}
}

func TestBoolParsing(t *testing.T) {
	tests := []struct {
		value string
		want  bool
	}{
		{"true", true},
		{"false", false},
		{"1", true},
		{"0", false},
		{"TRUE", true},
		{"FALSE", false},
	}

	for _, tt := range tests {
		t.Run(tt.value, func(t *testing.T) {
			t.Setenv("BOOLPARSE_DEBUG", tt.value)
			loader := NewLoader(Options{AppName: "boolparse"}, testDefaults)
			cfg, err := loader.Load()
			if err != nil {
				t.Fatalf("Load() error = %v", err)
			}
			if cfg.Debug != tt.want {
				t.Errorf("Debug = %v for input %q, want %v", cfg.Debug, tt.value, tt.want)
			}
			loader.ResetCache()
		})
	}
}

func TestDurationFromEnv(t *testing.T) {
	t.Setenv("DURTEST_TTL", "2h30m")

	loader := NewLoader(Options{AppName: "durtest"}, testDefaults)
	cfg, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	want := 2*time.Hour + 30*time.Minute
	if cfg.TTL != want {
		t.Errorf("TTL = %v, want %v", cfg.TTL, want)
	}
}

func TestZeroValuesNotOverridden(t *testing.T) {
	dir := t.TempDir()
	tomlPath := filepath.Join(dir, "config.toml")
	content := `
[server]
port = 0
host = ""
`
	if err := os.WriteFile(tomlPath, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	cfg := testDefaults()
	if err := mergeFile(cfg, tomlPath); err != nil {
		t.Fatalf("mergeFile() error = %v", err)
	}

	// Zero values in TOML should NOT override non-zero defaults.
	if cfg.Server.Port != 8080 {
		t.Errorf("Server.Port = %d, want 8080 (zero TOML should not override)", cfg.Server.Port)
	}
	if cfg.Server.Host != "localhost" {
		t.Errorf("Server.Host = %q, want %q (zero TOML should not override)", cfg.Server.Host, "localhost")
	}
}

func TestConfigNameOverride(t *testing.T) {
	loader := NewLoader(Options{AppName: "myapp", ConfigName: "custom"}, testDefaults)
	if loader.opts.ConfigName != "custom" {
		t.Errorf("ConfigName = %q, want %q", loader.opts.ConfigName, "custom")
	}
}

func TestConfigNameDefaultsToAppName(t *testing.T) {
	loader := NewLoader(Options{AppName: "myapp"}, testDefaults)
	if loader.opts.ConfigName != "myapp" {
		t.Errorf("ConfigName = %q, want %q", loader.opts.ConfigName, "myapp")
	}
}
