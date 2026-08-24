//nolint:gosec
package cosign

import (
	"context"
	"crypto/tls"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"regexp"
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
		IdentityRegexp: `^https://github\.com/testowner/testrepo/\.github/workflows/release\.yml@refs/tags/v.*$`,
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

// TestIdentityRegexpOrDefaultMatchesRealIdentity is the assertion that matters:
// the default pattern must actually match the certificate identity Sigstore
// reports for a release built by the repo's release workflow. Asserting only
// that the pattern contains the repo slug would still pass with escaping that
// can never match anything.
func TestIdentityRegexpOrDefaultMatchesRealIdentity(t *testing.T) {
	cfg := Config{
		Repo:       "danieljustus/symaira-vault",
		BinaryName: "symvault",
	}

	re, err := regexp.Compile(cfg.IdentityRegexpOrDefault())
	if err != nil {
		t.Fatalf("IdentityRegexpOrDefault() did not compile: %v", err)
	}

	tests := []struct {
		name     string
		identity string
		want     bool
	}{
		{
			name:     "release tag of the configured repo",
			identity: "https://github.com/danieljustus/symaira-vault/.github/workflows/release.yml@refs/tags/v1.0.0",
			want:     true,
		},
		{
			name:     "prerelease tag of the configured repo",
			identity: "https://github.com/danieljustus/symaira-vault/.github/workflows/release.yml@refs/tags/v0.9.1",
			want:     true,
		},
		{
			name:     "different repo must not match",
			identity: "https://github.com/attacker/evil/.github/workflows/release.yml@refs/tags/v1.0.0",
			want:     false,
		},
		{
			name:     "different workflow of the same repo must not match",
			identity: "https://github.com/danieljustus/symaira-vault/.github/workflows/ci.yml@refs/tags/v1.0.0",
			want:     false,
		},
		{
			name:     "branch ref instead of a tag must not match",
			identity: "https://github.com/danieljustus/symaira-vault/.github/workflows/release.yml@refs/heads/main",
			want:     false,
		},
		{
			name:     "valid identity embedded in a longer string must not match",
			identity: "https://evil.example/?u=https://github.com/danieljustus/symaira-vault/.github/workflows/release.yml@refs/tags/v1.0.0",
			want:     false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := re.MatchString(tt.identity); got != tt.want {
				t.Fatalf("MatchString(%q) = %v, want %v (pattern %q)",
					tt.identity, got, tt.want, cfg.IdentityRegexpOrDefault())
			}
		})
	}
}

// TestIdentityRegexpOrDefaultEscapesRepoSlug ensures a repo slug carrying
// regexp metacharacters cannot widen the pattern beyond the intended repo.
func TestIdentityRegexpOrDefaultEscapesRepoSlug(t *testing.T) {
	cfg := Config{
		Repo:       "owner/re.po",
		BinaryName: "tool",
	}

	re, err := regexp.Compile(cfg.IdentityRegexpOrDefault())
	if err != nil {
		t.Fatalf("IdentityRegexpOrDefault() did not compile: %v", err)
	}

	if !re.MatchString("https://github.com/owner/re.po/.github/workflows/release.yml@refs/tags/v1.0.0") {
		t.Fatal("pattern must match the literal repo slug it was built from")
	}
	// The unescaped '.' would make this match too.
	if re.MatchString("https://github.com/owner/reXpo/.github/workflows/release.yml@refs/tags/v1.0.0") {
		t.Fatal("'.' in the repo slug was not escaped — the pattern matches a foreign repo")
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

// TestClientDefaultIsHardened asserts the cosign artefact fetch no longer
// falls back to http.DefaultClient. The signature and certificate are what
// authorise replacing the running binary, so the transport that fetches them
// must carry the same guarantees as the rest of the update path.
func TestClientDefaultIsHardened(t *testing.T) {
	c := Config{Repo: "owner/repo", BinaryName: "tool"}.client()

	if c == http.DefaultClient {
		t.Fatal("default client must not be http.DefaultClient")
	}
	if c.Timeout <= 0 {
		t.Error("default client must set a timeout")
	}
	if c.CheckRedirect == nil {
		t.Fatal("default client must set CheckRedirect")
	}
	if err := c.CheckRedirect(
		&http.Request{URL: mustParseURL(t, "https://evil.example/sig")},
		[]*http.Request{{URL: mustParseURL(t, "https://github.com/owner/repo/releases/download/v1/x.sig")}},
	); err == nil {
		t.Error("default client must refuse redirects to non-GitHub hosts")
	}

	tr, ok := c.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("Transport = %T, want *http.Transport", c.Transport)
	}
	if tr.TLSClientConfig == nil || tr.TLSClientConfig.MinVersion != tls.VersionTLS13 {
		t.Error("default client must enforce a TLS 1.3 minimum")
	}
}

// TestClientExplicitOverrideWins keeps the documented escape hatch working for
// consumers on a custom host.
func TestClientExplicitOverrideWins(t *testing.T) {
	custom := &http.Client{}
	if got := (Config{HTTPClient: custom}).client(); got != custom {
		t.Error("an explicitly configured HTTPClient must be used unchanged")
	}
}

// TestFetchArtifactRejectsOversizedBody covers the read limit on the signature
// and certificate fetch, which previously read an unbounded body.
func TestFetchArtifactRejectsOversizedBody(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		buf := make([]byte, 64*1024)
		for written := 0; written <= maxArtifactBody; written += len(buf) {
			if _, err := w.Write(buf); err != nil {
				return
			}
		}
	}))
	t.Cleanup(server.Close)

	cfg := Config{
		Repo:            "owner/repo",
		BinaryName:      "tool",
		DownloadBaseURL: server.URL,
		HTTPClient:      server.Client(),
	}

	if _, err := cfg.FetchSignature(context.Background(), "v1.0.0"); err == nil {
		t.Fatal("expected an oversized signature body to be rejected")
	} else if !strings.Contains(err.Error(), "maximum size") {
		t.Errorf("error = %v, want a maximum-size rejection", err)
	}
}

// TestFetchArtifactAcceptsNormalBody guards against the size cap rejecting a
// real signature.
func TestFetchArtifactAcceptsNormalBody(t *testing.T) {
	want := []byte("MEUCIQDsignature-bytes")
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write(want)
	}))
	t.Cleanup(server.Close)

	cfg := Config{
		Repo:            "owner/repo",
		BinaryName:      "tool",
		DownloadBaseURL: server.URL,
		HTTPClient:      server.Client(),
	}

	got, err := cfg.FetchSignature(context.Background(), "v1.0.0")
	if err != nil {
		t.Fatalf("FetchSignature() error = %v", err)
	}
	if string(got) != string(want) {
		t.Errorf("FetchSignature() = %q, want %q", got, want)
	}
}

func mustParseURL(t *testing.T, raw string) *url.URL {
	t.Helper()
	u, err := url.Parse(raw)
	if err != nil {
		t.Fatalf("parse %q: %v", raw, err)
	}
	return u
}
