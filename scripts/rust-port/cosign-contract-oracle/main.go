// Command cosign-contract-oracle records updatecheck/cosign behavior through its public API.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"

	"github.com/danieljustus/symaira-corekit/updatecheck/cosign"
)

type observation struct {
	ID     string            `json:"id"`
	Input  map[string]string `json:"input,omitempty"`
	Result map[string]any    `json:"result"`
}

func main() {
	if captureStub() {
		return
	}
	cases := observe()
	if err := json.NewEncoder(os.Stdout).Encode(map[string]any{"goos": runtime.GOOS, "cases": cases}); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func observe() []observation {
	var requests []string
	base := "https://loopback:443/releases/download"
	client := &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		requests = append(requests, r.Method+" "+r.URL.EscapedPath())
		status, body := http.StatusOK, "signature-bytes\n"
		switch {
		case strings.Contains(r.URL.Path, "_404_"):
			status, body = http.StatusNotFound, "not found"
		case strings.Contains(r.URL.Path, "_large_"):
			body = strings.Repeat("x", (1<<20)+1)
		case strings.HasSuffix(r.URL.Path, ".pem"):
			body = "certificate-bytes\n"
		}
		return &http.Response{StatusCode: status, Body: io.NopCloser(strings.NewReader(body)), Header: make(http.Header), Request: r}, nil
	})}
	cfg := cosign.Config{Repo: "owner/repo", BinaryName: "tool", DownloadBaseURL: base, HTTPClient: client}
	results := make([]observation, 0, 10)
	for _, item := range []struct {
		id, artifact, version string
	}{
		{"fetch-signature", "signature", "v1.2.3"},
		{"fetch-certificate", "certificate", "1.2.3"},
		{"fetch-http-404", "signature", "404"},
		{"fetch-too-large", "signature", "large"},
		{"fetch-empty-version", "signature", ""},
	} {
		requests = nil
		var body []byte
		var err error
		if item.artifact == "signature" {
			body, err = cfg.FetchSignature(context.Background(), item.version)
		} else {
			body, err = cfg.FetchCertificate(context.Background(), item.version)
		}
		result := map[string]any{"body": string(body), "request": last(requests)}
		if err != nil {
			result["error_code"], result["error_message"] = classify(err), err.Error()
		}
		results = append(results, observation{ID: item.id, Input: map[string]string{"artifact": item.artifact, "base_url": "https://loopback/releases/download", "binary": "tool", "version": item.version}, Result: result})
	}
	plain := cosign.Config{BinaryName: "tool", DownloadBaseURL: "http://loopback/release"}
	_, insecureErr := plain.FetchSignature(context.Background(), "1.2.3")
	results = append(results, observation{ID: "fetch-http-url", Input: map[string]string{"artifact": "signature", "base_url": "http://loopback/release", "binary": "tool", "version": "1.2.3"}, Result: map[string]any{"error_code": "https_required", "error_message": insecureErr.Error()}})

	defaultConfig := cosign.Config{Repo: "owner/re.po", BinaryName: "tool"}
	pattern := defaultConfig.IdentityRegexpOrDefault()
	identities := []struct {
		id, identity string
	}{
		{"release", "https://github.com/owner/re.po/.github/workflows/release.yml@refs/tags/v1.2.3"},
		{"wrong-repo", "https://github.com/owner/reXpo/.github/workflows/release.yml@refs/tags/v1.2.3"},
		{"wrong-workflow", "https://github.com/owner/re.po/.github/workflows/ci.yml@refs/tags/v1.2.3"},
		{"branch-ref", "https://github.com/owner/re.po/.github/workflows/release.yml@refs/heads/main"},
		{"embedded", "https://evil.example/?u=https://github.com/owner/re.po/.github/workflows/release.yml@refs/tags/v1.2.3"},
	}
	for _, item := range identities {
		matches, _ := regexpMatch(pattern, item.identity)
		results = append(results, observation{ID: "identity-" + item.id, Input: map[string]string{"repo": "owner/re.po", "identity": item.identity}, Result: map[string]any{"pattern": pattern, "matches": matches}})
	}
	custom := `^custom/release@v.*$`
	verify := cosign.Config{Repo: "owner/repo", IdentityRegexp: custom}
	results = append(results, verifyCase(verify, "verify-custom-success", false))
	results = append(results, verifyCase(cosign.Config{Repo: "owner/repo"}, "verify-default-failure", true))
	return results
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func verifyCase(cfg cosign.Config, id string, fail bool) observation {
	dir, err := os.MkdirTemp("", "cosign-oracle-")
	if err != nil {
		panic(err)
	}
	defer os.RemoveAll(dir)
	exe, err := os.Executable()
	if err != nil {
		panic(err)
	}
	stub := filepath.Join(dir, "cosign")
	if runtime.GOOS == "windows" {
		stub += ".exe"
	}
	data, err := os.ReadFile(exe) //nolint:gosec // path comes from this oracle's own stub setup
	if err != nil {
		panic(err)
	}
	if err := os.WriteFile(stub, data, 0o700); err != nil { //nolint:gosec // stub must stay executable for the recorded exec observation
		panic(err)
	}
	capture := filepath.Join(dir, "capture.json")
	origPath := os.Getenv("PATH")
	_ = os.Setenv("PATH", dir+string(os.PathListSeparator)+origPath)
	_ = os.Setenv("COSIGN_ORACLE_CAPTURE", capture)
	_ = os.Setenv("COSIGN_ORACLE_FAIL", fmt.Sprint(fail))
	err = cfg.VerifySignature([]byte("checksums\n"), []byte("sig bytes\n"), []byte("cert bytes\n"))
	_ = os.Setenv("PATH", origPath)
	_ = os.Unsetenv("COSIGN_ORACLE_CAPTURE")
	_ = os.Unsetenv("COSIGN_ORACLE_FAIL")
	var captured struct {
		Args  []string          `json:"args"`
		Files map[string]string `json:"files"`
	}
	if err := readJSON(capture, &captured); err != nil {
		panic(err)
	}
	args := captured.Args
	for i, arg := range args {
		normalized := filepath.ToSlash(arg)
		if start := strings.Index(normalized, "cosign-verify-"); start >= 0 {
			if end := strings.Index(normalized[start:], "/"); end >= 0 {
				args[i] = "<temp>" + normalized[start+end:]
			}
		} else if strings.HasPrefix(arg, dir) {
			args[i] = strings.Replace(arg, dir, "<temp>", 1)
		}
	}
	result := map[string]any{"argv": append([]string{"cosign"}, args...), "content": captured.Files["content"], "signature": captured.Files["signature"], "certificate": captured.Files["certificate"], "error_code": "", "error_message": ""}
	if err != nil {
		result["error_code"], result["error_message"] = "verify_failed", err.Error()
	}
	return observation{ID: id, Input: map[string]string{"repo": cfg.Repo, "identity_regexp": cfg.IdentityRegexpOrDefault()}, Result: result}
}

func captureStub() bool {
	path := os.Getenv("COSIGN_ORACLE_CAPTURE")
	if path == "" {
		return false
	}
	args := os.Args[1:]
	files := map[string]string{}
	for i := 0; i+1 < len(args); i++ {
		key := map[string]string{"--certificate": "certificate", "--signature": "signature"}[args[i]]
		if key != "" {
			body, err := os.ReadFile(args[i+1]) //nolint:gosec // G703: path comes from this oracle's own argument table
			if err != nil {
				fmt.Fprintln(os.Stderr, err)
				os.Exit(2)
			}
			files[key] = string(body)
		}
	}
	if len(args) > 0 {
		body, err := os.ReadFile(args[len(args)-1]) //nolint:gosec // G703: path comes from this oracle's own argument table
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
		files["content"] = string(body)
	}
	if err := os.WriteFile(path, mustJSON(map[string]any{"args": args, "files": files}), 0o600); err != nil { //nolint:gosec // G703: path is built by this oracle
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if os.Getenv("COSIGN_ORACLE_FAIL") == "true" {
		fmt.Fprintln(os.Stderr, "fixture cosign rejected signature")
		os.Exit(1)
	}
	os.Exit(0)
	return true
}

func classify(err error) string {
	switch {
	case strings.Contains(err.Error(), "version must not be empty"):
		return "empty_version"
	case strings.Contains(err.Error(), "must use HTTPS"):
		return "https_required"
	case strings.Contains(err.Error(), "HTTP 404"):
		return "http_404"
	case strings.Contains(err.Error(), "exceeds maximum size"):
		return "too_large"
	default:
		return "error"
	}
}

func last(values []string) string {
	if len(values) == 0 {
		return ""
	}
	return values[len(values)-1]
}
func regexpMatch(pattern, value string) (bool, error) { return regexp.MatchString(pattern, value) }
func mustJSON(value any) []byte {
	data, err := json.Marshal(value)
	if err != nil {
		panic(err)
	}
	return data
}
func readJSON(path string, target any) error {
	data, err := os.ReadFile(path) //nolint:gosec // path comes from this oracle's own recording dir
	if err != nil {
		return err
	}
	return json.Unmarshal(data, target)
}
