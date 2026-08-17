package updatecheck

import (
	"crypto/tls"
	"net/http"
	"net/url"
	"testing"
)

func mustParseURL(t *testing.T, raw string) *url.URL {
	t.Helper()
	u, err := url.Parse(raw)
	if err != nil {
		t.Fatalf("parse %q: %v", raw, err)
	}
	return u
}

// TestSecureClientTLSMinimum asserts the secure default client enforces
// TLS 1.3 as the minimum version.
func TestSecureClientTLSMinimum(t *testing.T) {
	c := newSecureClient()
	tr, ok := c.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("Transport = %T, want *http.Transport", c.Transport)
	}
	if tr.TLSClientConfig == nil {
		t.Fatal("TLSClientConfig is nil")
	}
	if tr.TLSClientConfig.MinVersion != tls.VersionTLS13 {
		t.Errorf("MinVersion = %d, want %d (TLS 1.3)", tr.TLSClientConfig.MinVersion, tls.VersionTLS13)
	}
}

// TestSecureClientRedirectRefusesForeignHost exercises the CheckRedirect
// branch that rejects redirects away from GitHub hosts.
func TestSecureClientRedirectRefusesForeignHost(t *testing.T) {
	c := newSecureClient()
	err := c.CheckRedirect(
		&http.Request{URL: mustParseURL(t, "https://evil.example/steal")},
		[]*http.Request{
			{URL: mustParseURL(t, "https://api.github.com/repos/x/y/releases/latest")},
		},
	)
	if err == nil {
		t.Fatal("expected redirect to non-GitHub host to be refused")
	}
}

// TestSecureClientRedirectAllowsGitHubHost exercises the accept branch for
// redirects that stay on GitHub hosts.
func TestSecureClientRedirectAllowsGitHubHost(t *testing.T) {
	c := newSecureClient()
	err := c.CheckRedirect(
		&http.Request{URL: mustParseURL(t, "https://github.com/danieljustus/symaira-corekit/releases/download/v1.0.0/asset")},
		[]*http.Request{
			{URL: mustParseURL(t, "https://api.github.com/repos/danieljustus/symaira-corekit/releases/latest")},
		},
	)
	if err != nil {
		t.Errorf("redirect within GitHub hosts should be allowed, got %v", err)
	}
}

// TestSecureClientRedirectCap exercises the 10-redirect cap branch.
func TestSecureClientRedirectCap(t *testing.T) {
	c := newSecureClient()
	via := make([]*http.Request, 0, 10)
	for i := 0; i < 10; i++ {
		via = append(via, &http.Request{URL: mustParseURL(t, "https://api.github.com/x")})
	}
	err := c.CheckRedirect(
		&http.Request{URL: mustParseURL(t, "https://api.github.com/y")},
		via,
	)
	if err == nil {
		t.Fatal("expected the 10-redirect cap to stop redirects")
	}
}

// TestNewSecureClientExported asserts the exported constructor carries the
// same hardening as the internal one, since sibling packages now depend on it
// for the asset, checksum and signature downloads.
func TestNewSecureClientExported(t *testing.T) {
	c := NewSecureClient()

	if c.Timeout != DefaultAPITimeout {
		t.Errorf("Timeout = %v, want %v", c.Timeout, DefaultAPITimeout)
	}
	tr, ok := c.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("Transport = %T, want *http.Transport", c.Transport)
	}
	if tr.TLSClientConfig == nil || tr.TLSClientConfig.MinVersion != tls.VersionTLS13 {
		t.Error("exported client must enforce a TLS 1.3 minimum")
	}
	if c.CheckRedirect == nil {
		t.Fatal("exported client must set CheckRedirect")
	}
	if err := c.CheckRedirect(
		&http.Request{URL: mustParseURL(t, "https://evil.example/x")},
		[]*http.Request{{URL: mustParseURL(t, "https://api.github.com/x")}},
	); err == nil {
		t.Error("exported client must refuse redirects to non-GitHub hosts")
	}
}

// TestNewSecureClientWithTimeout covers the download-oriented variant: same
// hardening, caller-chosen timeout. A metadata timeout would abort any real
// asset download, so the two must be separable.
func TestNewSecureClientWithTimeout(t *testing.T) {
	c := NewSecureClientWithTimeout(DefaultDownloadTimeout)

	if c.Timeout != DefaultDownloadTimeout {
		t.Errorf("Timeout = %v, want %v", c.Timeout, DefaultDownloadTimeout)
	}
	if DefaultDownloadTimeout <= DefaultAPITimeout {
		t.Errorf("DefaultDownloadTimeout (%v) must exceed DefaultAPITimeout (%v); a download reads a whole binary body",
			DefaultDownloadTimeout, DefaultAPITimeout)
	}
	tr, ok := c.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("Transport = %T, want *http.Transport", c.Transport)
	}
	if tr.TLSClientConfig == nil || tr.TLSClientConfig.MinVersion != tls.VersionTLS13 {
		t.Error("timeout variant must enforce a TLS 1.3 minimum")
	}
	if c.CheckRedirect == nil {
		t.Fatal("timeout variant must set CheckRedirect")
	}
}
