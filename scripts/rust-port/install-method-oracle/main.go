// Command install-method-oracle records public installmethod API observations.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/danieljustus/symaira-corekit/updatecheck/installmethod"
)

type testCase struct {
	ID   string            `json:"id"`
	Path string            `json:"path"`
	Env  map[string]string `json:"env,omitempty"`
	Kind string            `json:"kind,omitempty"`
}

type observation struct {
	ID         string            `json:"id"`
	Path       string            `json:"path"`
	Env        map[string]string `json:"env,omitempty"`
	Method     string            `json:"method"`
	Error      string            `json:"error"`
	SelfUpdate bool              `json:"self_update"`
	Guidance   string            `json:"guidance"`
}

type fixture struct {
	GoSourceSHA256 string        `json:"go_source_sha256"`
	OracleSHA256   string        `json:"oracle_sha256"`
	Cases          []observation `json:"cases"`
}

func main() {
	tmp, err := os.MkdirTemp("", "upd008-")
	if err != nil {
		fatal(err)
	}
	defer os.RemoveAll(tmp)
	home := filepath.Join(tmp, "home")
	readOnly := filepath.Join(tmp, "readonly")
	if err := os.MkdirAll(home, 0755); err != nil { //nolint:gosec // fixture lives in an isolated temp dir
		fatal(err)
	}
	if err := os.MkdirAll(readOnly, 0555); err != nil { //nolint:gosec // read-only mode is the recorded observation
		fatal(err)
	}
	if err := os.Chmod(readOnly, 0555); err != nil { //nolint:gosec // read-only mode is the recorded observation
		fatal(err)
	}
	cellarBinary := filepath.Join(tmp, "Cellar", "tool", "1.0.0", "bin", "tool")
	if err := os.MkdirAll(filepath.Dir(cellarBinary), 0755); err != nil { //nolint:gosec // fixture lives in an isolated temp dir
		fatal(err)
	}
	if err := os.WriteFile(cellarBinary, []byte("fixture"), 0644); err != nil { //nolint:gosec // fixture mode is the recorded observation
		fatal(err)
	}
	link := filepath.Join(tmp, "link", "tool")
	if err := os.MkdirAll(filepath.Dir(link), 0755); err != nil { //nolint:gosec // fixture lives in an isolated temp dir
		fatal(err)
	}
	if err := os.Symlink(cellarBinary, link); err != nil {
		fatal(err)
	}

	path := func(value string) string {
		return strings.ReplaceAll(value, "${TMP}", tmp)
	}
	cases := []testCase{
		{ID: "empty", Path: ""},
		{ID: "homebrew-env", Path: "${TMP}/brew/bin/tool", Env: map[string]string{"HOMEBREW_PREFIX": "${TMP}/brew"}},
		{ID: "gopath-env", Path: "${TMP}/gopath/bin/tool", Env: map[string]string{"GOPATH": "${TMP}/gopath"}},
		{ID: "gomodcache-env", Path: "${TMP}/modcache/example/tool", Env: map[string]string{"GOMODCACHE": "${TMP}/modcache"}},
		{ID: "homebrew-path", Path: "/opt/homebrew/bin/tool"},
		{ID: "cellar-path", Path: "/usr/local/Cellar/tool/1.0.0/bin/tool"},
		{ID: "linuxbrew-path", Path: "/home/linuxbrew/.linuxbrew/bin/tool"},
		{ID: "package-path", Path: "/usr/bin/tool"},
		{ID: "direct-path", Path: "/usr/local/bin/tool"},
		{ID: "go-cache", Path: "/go/pkg/mod/example/tool@v1/bin/tool"},
		{ID: "home-local-bin", Path: "${TMP}/home/.local/bin/tool", Env: map[string]string{"HOME": "${TMP}/home"}},
		{ID: "layered-env-priority", Path: "/opt/homebrew/bin/tool", Env: map[string]string{"HOMEBREW_PREFIX": "/opt/homebrew"}},
		{ID: "resolved-symlink", Path: "${TMP}/link/tool"},
		{ID: "source-readonly", Path: "${TMP}/readonly/tool", Kind: "readonly"},
		{ID: "missing-parent", Path: "${TMP}/missing/tool"},
	}
	observations := make([]observation, 0, len(cases))
	for _, tc := range cases {
		for _, key := range []string{"HOMEBREW_PREFIX", "GOPATH", "GOMODCACHE", "HOME"} {
			if err := os.Unsetenv(key); err != nil {
				fatal(err)
			}
		}
		env := make(map[string]string, len(tc.Env))
		for key, value := range tc.Env {
			value = path(value)
			env[key] = value
			if err := os.Setenv(key, value); err != nil {
				fatal(err)
			}
		}
		input := path(tc.Path)
		method, detectErr := installmethod.Detect(input)
		errText := ""
		if detectErr != nil {
			errText = detectErr.Error()
		}
		observations = append(observations, observation{
			ID: tc.ID, Path: tc.Path, Env: tc.Env, Method: string(method), Error: errText,
			SelfUpdate: installmethod.IsSelfUpdateSupported(method),
			Guidance:   installmethod.Guidance(method, "symvault"),
		})
	}
	data, err := os.ReadFile(filepath.Join("updatecheck", "installmethod", "detect.go"))
	if err != nil {
		fatal(err)
	}
	oracle, err := os.ReadFile(filepath.Join("scripts", "rust-port", "install-method-oracle", "main.go"))
	if err != nil {
		fatal(err)
	}
	result := fixture{GoSourceSHA256: digest(data), OracleSHA256: digest(oracle), Cases: observations}
	if err := json.NewEncoder(os.Stdout).Encode(result); err != nil {
		fatal(err)
	}
}

func digest(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
