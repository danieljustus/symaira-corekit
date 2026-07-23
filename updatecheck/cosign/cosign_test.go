package cosign

import (
	"context"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"testing"
)

type stubHTTPDoer struct {
	do func(req *http.Request) (*http.Response, error)
}

func (s stubHTTPDoer) Do(req *http.Request) (*http.Response, error) {
	return s.do(req)
}

func TestSignatureFileName(t *testing.T) {
	cfg := Config{BinaryName: "mytool"}
	tests := []struct {
		version  string
		expected string
	}{
		{"0.5.0", "mytool_0.5.0_checksums.txt.sig"},
		{"v1.2.0", "mytool_1.2.0_checksums.txt.sig"},
		{"v", "mytool__checksums.txt.sig"},
	}
	for _, tt := range tests {
		t.Run(tt.expected, func(t *testing.T) {
			got := cfg.signatureFileName(tt.version)
			if got != tt.expected {
				t.Fatalf("signatureFileName(%q) = %q, want %q",
					tt.version, got, tt.expected)
			}
		})
	}
}

func TestCertificateFileName(t *testing.T) {
	cfg := Config{BinaryName: "mytool"}
	tests := []struct {
		version  string
		expected string
	}{
		{"0.5.0", "mytool_0.5.0_checksums.txt.pem"},
		{"v1.2.0", "mytool_1.2.0_checksums.txt.pem"},
	}
	for _, tt := range tests {
		t.Run(tt.expected, func(t *testing.T) {
			got := cfg.certificateFileName(tt.version)
			if got != tt.expected {
				t.Fatalf("certificateFileName(%q) = %q, want %q",
					tt.version, got, tt.expected)
			}
		})
	}
}

func TestFetchSignature_Success(t *testing.T) {
	expectedBody := []byte("fake-cosign-signature")
	cfg := Config{
		BinaryName: "mytool",
		HTTPClient: &http.Client{
			Transport: stubRoundTripper(func(req *http.Request) (*http.Response, error) {
				return &http.Response{
					StatusCode: http.StatusOK,
					Body:       io.NopCloser(strings.NewReader(string(expectedBody))),
					Header:     make(http.Header),
				}, nil
			}),
		},
	}

	data, err := cfg.FetchSignature(context.Background(), "0.5.0")
	if err != nil {
		t.Fatalf("FetchSignature() error = %v", err)
	}
	if string(data) != string(expectedBody) {
		t.Fatalf("got body %q, want %q", string(data), string(expectedBody))
	}
}

func TestFetchSignature_HTTPError(t *testing.T) {
	cfg := Config{
		BinaryName: "mytool",
		HTTPClient: &http.Client{
			Transport: stubRoundTripper(func(req *http.Request) (*http.Response, error) {
				return &http.Response{
					StatusCode: http.StatusNotFound,
					Body:       io.NopCloser(strings.NewReader("not found")),
					Header:     make(http.Header),
				}, nil
			}),
		},
	}

	_, err := cfg.FetchSignature(context.Background(), "0.5.0")
	if err == nil {
		t.Fatal("expected HTTP error")
	}
	if !strings.Contains(err.Error(), "HTTP 404") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestFetchSignature_EmptyVersion(t *testing.T) {
	cfg := Config{BinaryName: "mytool"}
	_, err := cfg.FetchSignature(context.Background(), "")
	if err == nil {
		t.Fatal("expected empty version error")
	}
	if !strings.Contains(err.Error(), "version must not be empty") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestFetchSignature_URLScheme(t *testing.T) {
	cfg := Config{
		BinaryName:      "mytool",
		DownloadBaseURL: "http://example.com/fake",
	}

	_, err := cfg.FetchSignature(context.Background(), "0.5.0")
	if err == nil {
		t.Fatal("expected HTTPS enforcement error")
	}
	if !strings.Contains(err.Error(), "must use HTTPS") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestFetchCertificate_Success(t *testing.T) {
	expectedBody := []byte("fake-cosign-certificate")
	cfg := Config{
		BinaryName: "mytool",
		HTTPClient: &http.Client{
			Transport: stubRoundTripper(func(req *http.Request) (*http.Response, error) {
				return &http.Response{
					StatusCode: http.StatusOK,
					Body:       io.NopCloser(strings.NewReader(string(expectedBody))),
					Header:     make(http.Header),
				}, nil
			}),
		},
	}

	data, err := cfg.FetchCertificate(context.Background(), "0.5.0")
	if err != nil {
		t.Fatalf("FetchCertificate() error = %v", err)
	}
	if string(data) != string(expectedBody) {
		t.Fatalf("got body %q, want %q", string(data), string(expectedBody))
	}
}

func TestFetchCertificate_HTTPError(t *testing.T) {
	cfg := Config{
		BinaryName: "mytool",
		HTTPClient: &http.Client{
			Transport: stubRoundTripper(func(req *http.Request) (*http.Response, error) {
				return &http.Response{
					StatusCode: http.StatusForbidden,
					Body:       io.NopCloser(strings.NewReader("forbidden")),
					Header:     make(http.Header),
				}, nil
			}),
		},
	}

	_, err := cfg.FetchCertificate(context.Background(), "0.5.0")
	if err == nil {
		t.Fatal("expected HTTP error")
	}
	if !strings.Contains(err.Error(), "HTTP 403") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestFetchCertificate_EmptyVersion(t *testing.T) {
	cfg := Config{BinaryName: "mytool"}
	_, err := cfg.FetchCertificate(context.Background(), "")
	if err == nil {
		t.Fatal("expected empty version error")
	}
	if !strings.Contains(err.Error(), "version must not be empty") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestFetchCertificate_URLScheme(t *testing.T) {
	cfg := Config{
		BinaryName:      "mytool",
		DownloadBaseURL: "http://example.com/fake",
	}

	_, err := cfg.FetchCertificate(context.Background(), "0.5.0")
	if err == nil {
		t.Fatal("expected HTTPS enforcement error")
	}
	if !strings.Contains(err.Error(), "must use HTTPS") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestVerifySignature_CosignNotFound(t *testing.T) {
	origPath := os.Getenv("PATH")
	t.Cleanup(func() { os.Setenv("PATH", origPath) })
	os.Setenv("PATH", "")

	cfg := Config{BinaryName: "mytool"}
	err := cfg.VerifySignature(
		[]byte("test-content"),
		[]byte("fake-signature"),
		[]byte("fake-certificate"),
	)
	if err == nil {
		t.Fatal("expected error when cosign is not on PATH")
	}
	if !strings.Contains(err.Error(), "cosign CLI not found") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestVerifySignature_InvalidArgs(t *testing.T) {
	if _, err := exec.LookPath("cosign"); err == nil {
		t.Skip("cosign is installed — this test is for the binary-not-found path")
	}

	origPath := os.Getenv("PATH")
	t.Cleanup(func() { os.Setenv("PATH", origPath) })
	os.Setenv("PATH", "")

	cfg := Config{BinaryName: "mytool"}
	err := cfg.VerifySignature(
		[]byte("random-content"),
		[]byte("random-sig"),
		[]byte("random-cert"),
	)
	if err == nil {
		t.Fatal("expected error")
	}
	if !strings.Contains(err.Error(), "install cosign") {
		t.Fatalf("error should instruct user to install cosign: %v", err)
	}
}

func TestVerifySignature_ExecFailure(t *testing.T) {
	if _, err := exec.LookPath("cosign"); err != nil {
		t.Skip("cosign not on PATH — exec failure test requires cosign to pass LookPath")
	}

	origExec := execCommand
	t.Cleanup(func() { execCommand = origExec })

	execCommand = func(name string, arg ...string) *exec.Cmd {
		if name == "cosign" {
			return exec.Command("false")
		}
		return exec.Command(name, arg...)
	}

	cfg := Config{BinaryName: "mytool"}
	err := cfg.VerifySignature(
		[]byte("content"),
		[]byte("sig"),
		[]byte("cert"),
	)
	if err == nil {
		t.Fatal("expected error from cosign exec failure")
	}
	if !strings.Contains(err.Error(), "cosign verify-blob failed") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestVerifySignature_CorrectArgs(t *testing.T) {
	if _, err := exec.LookPath("cosign"); err != nil {
		t.Skip("cosign not on PATH — argv assertion test requires cosign to pass LookPath")
	}

	origExec := execCommand
	t.Cleanup(func() { execCommand = origExec })

	var capturedName string
	var capturedArgs []string
	execCommand = func(name string, arg ...string) *exec.Cmd {
		capturedName = name
		capturedArgs = arg
		return exec.Command("true")
	}

	cfg := Config{
		BinaryName:     "mytool",
		Repo:           "testowner/testrepo",
		IdentityRegexp: `https://github\\.com/testowner/testrepo/\\.github/workflows/release\\.yml@refs/tags/v.*`,
	}
	err := cfg.VerifySignature(
		[]byte("content"),
		[]byte("sig"),
		[]byte("cert"),
	)
	if err != nil {
		t.Fatalf("VerifySignature() error = %v", err)
	}

	if capturedName != "cosign" {
		t.Fatalf("expected cosign command, got %q", capturedName)
	}

	identityFlagIdx := -1
	for i, arg := range capturedArgs {
		if arg == "--certificate-identity-regexp" {
			identityFlagIdx = i
			break
		}
	}
	if identityFlagIdx == -1 || identityFlagIdx+1 >= len(capturedArgs) {
		t.Fatalf("expected --certificate-identity-regexp flag in args: %s", strings.Join(capturedArgs, " "))
	}
	identityValue := capturedArgs[identityFlagIdx+1]
	if identityValue != cfg.IdentityRegexp {
		t.Fatalf("--certificate-identity-regexp = %q, want %q", identityValue, cfg.IdentityRegexp)
	}

	issuerFlagIdx := -1
	for i, arg := range capturedArgs {
		if arg == "--certificate-oidc-issuer" {
			issuerFlagIdx = i
			break
		}
	}
	if issuerFlagIdx == -1 || issuerFlagIdx+1 >= len(capturedArgs) {
		t.Fatalf("expected --certificate-oidc-issuer flag in args: %s", strings.Join(capturedArgs, " "))
	}
	issuerValue := capturedArgs[issuerFlagIdx+1]
	if issuerValue != OIDCIssuer {
		t.Fatalf("--certificate-oidc-issuer = %q, want %q", issuerValue, OIDCIssuer)
	}
}

func TestIdentityRegexpOrDefault(t *testing.T) {
	cfg := Config{
		Repo:       "danieljustus/symaira-vault",
		BinaryName: "symvault",
	}
	got := cfg.IdentityRegexpOrDefault()
	if !strings.Contains(got, "danieljustus/symaira-vault") {
		t.Fatalf("IdentityRegexpOrDefault() = %q, should contain repo slug", got)
	}
}

func TestDownloadBaseURLOrDefault(t *testing.T) {
	cfg := Config{
		Repo:       "danieljustus/symaira-vault",
		BinaryName: "symvault",
	}
	got := cfg.DownloadBaseURLOrDefault()
	want := "https://github.com/danieljustus/symaira-vault/releases/download"
	if got != want {
		t.Fatalf("DownloadBaseURLOrDefault() = %q, want %q", got, want)
	}

	cfg2 := Config{DownloadBaseURL: "https://custom.example.com/dl"}
	got2 := cfg2.DownloadBaseURLOrDefault()
	if got2 != "https://custom.example.com/dl" {
		t.Fatalf("DownloadBaseURLOrDefault() = %q, want custom URL", got2)
	}
}

// stubRoundTripper implements http.RoundTripper for testing.
type stubRoundTripper func(req *http.Request) (*http.Response, error)

func (f stubRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	return f(req)
}
