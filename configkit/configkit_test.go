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

type testSliceConfig struct {
	Tags    []string       `json:"tags"`
	Ports   []int          `json:"ports"`
	Rates   []float64      `json:"rates"`
	Flags   []bool         `json:"flags"`
	Allowed map[string]int `json:"allowed"`
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

func TestTypeMismatchReturnsError(t *testing.T) {
	dir := t.TempDir()
	origDir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.Chdir(origDir) })
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}

	// Timeout is an int field, but the TOML provides a string.
	projectFile := filepath.Join(dir, ".mismatch-test.toml")
	if err := os.WriteFile(projectFile, []byte(`timeout = "not-a-number"`), 0o644); err != nil {
		t.Fatal(err)
	}

	loader := NewLoader(Options{AppName: "mismatch-test"}, testDefaults)
	if _, err := loader.Load(); err == nil {
		t.Fatal("expected error for type-mismatched TOML value, got nil")
	} else if !strings.Contains(err.Error(), "timeout") {
		t.Errorf("expected error to mention the field, got %v", err)
	}
}

func TestSliceFromTOML(t *testing.T) {
	dir := t.TempDir()
	tomlPath := filepath.Join(dir, "config.toml")
	content := `
tags = ["web", "api", "production"]
ports = [80, 443, 8080]
rates = [1.5, 2.7, 3.14]
flags = [true, false, true]
`
	if err := os.WriteFile(tomlPath, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	cfg := &testSliceConfig{}
	if err := mergeFile(cfg, tomlPath); err != nil {
		t.Fatalf("mergeFile() error = %v", err)
	}

	wantTags := []string{"web", "api", "production"}
	if len(cfg.Tags) != len(wantTags) {
		t.Fatalf("Tags len = %d, want %d", len(cfg.Tags), len(wantTags))
	}
	for i, v := range cfg.Tags {
		if v != wantTags[i] {
			t.Errorf("Tags[%d] = %q, want %q", i, v, wantTags[i])
		}
	}

	wantPorts := []int{80, 443, 8080}
	if len(cfg.Ports) != len(wantPorts) {
		t.Fatalf("Ports len = %d, want %d", len(cfg.Ports), len(wantPorts))
	}
	for i, v := range cfg.Ports {
		if v != wantPorts[i] {
			t.Errorf("Ports[%d] = %d, want %d", i, v, wantPorts[i])
		}
	}

	wantRates := []float64{1.5, 2.7, 3.14}
	if len(cfg.Rates) != len(wantRates) {
		t.Fatalf("Rates len = %d, want %d", len(cfg.Rates), len(wantRates))
	}
	for i, v := range cfg.Rates {
		if v != wantRates[i] {
			t.Errorf("Rates[%d] = %f, want %f", i, v, wantRates[i])
		}
	}

	wantFlags := []bool{true, false, true}
	if len(cfg.Flags) != len(wantFlags) {
		t.Fatalf("Flags len = %d, want %d", len(cfg.Flags), len(wantFlags))
	}
	for i, v := range cfg.Flags {
		if v != wantFlags[i] {
			t.Errorf("Flags[%d] = %v, want %v", i, v, wantFlags[i])
		}
	}
}

func TestMapFieldReturnsError(t *testing.T) {
	dir := t.TempDir()
	tomlPath := filepath.Join(dir, "config.toml")
	content := `
[allowed]
admin = 3
user = 1
`
	if err := os.WriteFile(tomlPath, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	cfg := &testSliceConfig{}
	err := mergeFile(cfg, tomlPath)
	if err == nil {
		t.Fatal("mergeFile() should return error for map field, got nil")
	}
	if !strings.Contains(err.Error(), "allowed") {
		t.Errorf("error = %q, want it to mention the field name 'allowed'", err.Error())
	}
}

func TestSliceMismatchReturnsError(t *testing.T) {
	dir := t.TempDir()
	tomlPath := filepath.Join(dir, "config.toml")
	// tags is []string, but TOML provides int elements.
	content := `
tags = [1, 2, 3]
`
	if err := os.WriteFile(tomlPath, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	cfg := &testSliceConfig{}
	err := mergeFile(cfg, tomlPath)
	if err == nil {
		t.Fatal("mergeFile() should return error for type-mismatched slice elements, got nil")
	}
	if !strings.Contains(err.Error(), "tags") {
		t.Errorf("error = %q, want it to mention the field name 'tags'", err.Error())
	}
}

// Parity tests verify that TOML and env paths produce identical results
// when setting the same logical field. This ensures the unified setFieldValue
// converter works correctly for both source types.

func TestParityStringTOMLAndEnv(t *testing.T) {
	tomlDir := t.TempDir()
	tomlPath := filepath.Join(tomlDir, "config.toml")
	if err := os.WriteFile(tomlPath, []byte(`name = "parity-test"`), 0o644); err != nil {
		t.Fatal(err)
	}
	tomlCfg := testDefaults()
	if err := mergeFile(tomlCfg, tomlPath); err != nil {
		t.Fatalf("mergeFile() error = %v", err)
	}

	t.Setenv("PARSTR_NAME", "parity-test")
	envCfg := testDefaults()
	loader := NewLoader(Options{AppName: "parstr"}, testDefaults)
	envCfg, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if tomlCfg.Name != envCfg.Name {
		t.Errorf("string parity: TOML=%q, env=%q, want equal", tomlCfg.Name, envCfg.Name)
	}
}

func TestParityIntTOMLAndEnv(t *testing.T) {
	tomlDir := t.TempDir()
	tomlPath := filepath.Join(tomlDir, "config.toml")
	if err := os.WriteFile(tomlPath, []byte(`timeout = 42`), 0o644); err != nil {
		t.Fatal(err)
	}
	tomlCfg := testDefaults()
	if err := mergeFile(tomlCfg, tomlPath); err != nil {
		t.Fatalf("mergeFile() error = %v", err)
	}

	t.Setenv("PARINT_TIMEOUT", "42")
	loader := NewLoader(Options{AppName: "parint"}, testDefaults)
	envCfg, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if tomlCfg.Timeout != envCfg.Timeout {
		t.Errorf("int parity: TOML=%d, env=%d, want equal", tomlCfg.Timeout, envCfg.Timeout)
	}
}

func TestParityFloatTOMLAndEnv(t *testing.T) {
	tomlDir := t.TempDir()
	tomlPath := filepath.Join(tomlDir, "config.toml")
	if err := os.WriteFile(tomlPath, []byte(`rate = 2.718`), 0o644); err != nil {
		t.Fatal(err)
	}
	tomlCfg := testDefaults()
	if err := mergeFile(tomlCfg, tomlPath); err != nil {
		t.Fatalf("mergeFile() error = %v", err)
	}

	t.Setenv("PARFLOAT_RATE", "2.718")
	loader := NewLoader(Options{AppName: "parfloat"}, testDefaults)
	envCfg, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if tomlCfg.Rate != envCfg.Rate {
		t.Errorf("float parity: TOML=%f, env=%f, want equal", tomlCfg.Rate, envCfg.Rate)
	}
}

func TestParityBoolTOMLAndEnv(t *testing.T) {
	tomlDir := t.TempDir()
	tomlPath := filepath.Join(tomlDir, "config.toml")
	if err := os.WriteFile(tomlPath, []byte(`debug = true`), 0o644); err != nil {
		t.Fatal(err)
	}
	tomlCfg := testDefaults()
	if err := mergeFile(tomlCfg, tomlPath); err != nil {
		t.Fatalf("mergeFile() error = %v", err)
	}

	t.Setenv("PARBOOL_DEBUG", "true")
	loader := NewLoader(Options{AppName: "parbool"}, testDefaults)
	envCfg, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if tomlCfg.Debug != envCfg.Debug {
		t.Errorf("bool parity: TOML=%v, env=%v, want equal", tomlCfg.Debug, envCfg.Debug)
	}
}

func TestParityDurationTOMLAndEnv(t *testing.T) {
	tomlDir := t.TempDir()
	tomlPath := filepath.Join(tomlDir, "config.toml")
	if err := os.WriteFile(tomlPath, []byte(`ttl = "2h30m"`), 0o644); err != nil {
		t.Fatal(err)
	}
	tomlCfg := testDefaults()
	if err := mergeFile(tomlCfg, tomlPath); err != nil {
		t.Fatalf("mergeFile() error = %v", err)
	}

	t.Setenv("PARDUR_TTL", "2h30m")
	loader := NewLoader(Options{AppName: "pardur"}, testDefaults)
	envCfg, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	want := 2*time.Hour + 30*time.Minute
	if tomlCfg.TTL != want {
		t.Errorf("duration parity TOML: TTL = %v, want %v", tomlCfg.TTL, want)
	}
	if envCfg.TTL != want {
		t.Errorf("duration parity env: TTL = %v, want %v", envCfg.TTL, want)
	}
	if tomlCfg.TTL != envCfg.TTL {
		t.Errorf("duration parity: TOML=%v, env=%v, want equal", tomlCfg.TTL, envCfg.TTL)
	}
}

func TestSliceFromEnv(t *testing.T) {
	t.Setenv("ENVSLICE_TAGS", "web,api,production")
	t.Setenv("ENVSLICE_PORTS", "80,443,8080")

	cfg := &testSliceConfig{}
	loader := NewLoader(Options{AppName: "envslice"}, func() *testSliceConfig { return cfg })
	_, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	wantTags := []string{"web", "api", "production"}
	if len(cfg.Tags) != len(wantTags) {
		t.Fatalf("Tags len = %d, want %d", len(cfg.Tags), len(wantTags))
	}
	for i, v := range cfg.Tags {
		if v != wantTags[i] {
			t.Errorf("Tags[%d] = %q, want %q", i, v, wantTags[i])
		}
	}

	wantPorts := []int{80, 443, 8080}
	if len(cfg.Ports) != len(wantPorts) {
		t.Fatalf("Ports len = %d, want %d", len(cfg.Ports), len(wantPorts))
	}
	for i, v := range cfg.Ports {
		if v != wantPorts[i] {
			t.Errorf("Ports[%d] = %d, want %d", i, v, wantPorts[i])
		}
	}
}

func TestParitySliceTOMLAndEnv(t *testing.T) {
	tomlDir := t.TempDir()
	tomlPath := filepath.Join(tomlDir, "config.toml")
	if err := os.WriteFile(tomlPath, []byte(`tags = ["alpha","beta"]`), 0o644); err != nil {
		t.Fatal(err)
	}
	tomlCfg := &testSliceConfig{}
	if err := mergeFile(tomlCfg, tomlPath); err != nil {
		t.Fatalf("mergeFile() error = %v", err)
	}

	t.Setenv("PARSLICE_TAGS", "alpha,beta")
	envCfg := &testSliceConfig{}
	loader := NewLoader(Options{AppName: "parslice"}, func() *testSliceConfig { return envCfg })
	if _, err := loader.Load(); err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if len(tomlCfg.Tags) != len(envCfg.Tags) {
		t.Fatalf("slice parity: TOML len=%d, env len=%d, want equal", len(tomlCfg.Tags), len(envCfg.Tags))
	}
	for i := range tomlCfg.Tags {
		if tomlCfg.Tags[i] != envCfg.Tags[i] {
			t.Errorf("slice parity: Tags[%d] TOML=%q env=%q, want equal", i, tomlCfg.Tags[i], envCfg.Tags[i])
		}
	}
}

func TestTypeErrorConsistency(t *testing.T) {
	tomlDir := t.TempDir()
	tomlPath := filepath.Join(tomlDir, "config.toml")
	if err := os.WriteFile(tomlPath, []byte(`timeout = "not-a-number"`), 0o644); err != nil {
		t.Fatal(err)
	}
	tomlErr := mergeFile(testDefaults(), tomlPath)
	if tomlErr == nil {
		t.Fatal("TOML type mismatch should error")
	}

	t.Setenv("TYPCHECK_TIMEOUT", "not-a-number")
	_, envErr := NewLoader(Options{AppName: "typcheck"}, testDefaults).Load()
	if envErr == nil {
		t.Fatal("env type mismatch should error")
	}

	if !strings.Contains(tomlErr.Error(), "timeout") {
		t.Errorf("TOML error = %q, want it to mention 'timeout'", tomlErr.Error())
	}
	if !strings.Contains(envErr.Error(), "TIMEOUT") {
		t.Errorf("env error = %q, want it to mention 'TIMEOUT'", envErr.Error())
	}
}
