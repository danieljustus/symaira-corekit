package updatecheck

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type stubHTTPDoer struct {
	do func(req *http.Request) (*http.Response, error)
}

func (s stubHTTPDoer) Do(req *http.Request) (*http.Response, error) {
	return s.do(req)
}

func TestNewCheckerBuildsURL(t *testing.T) {
	c := NewChecker("danieljustus", "symaira-vault")
	want := "https://api.github.com/repos/danieljustus/symaira-vault/releases/latest"
	if c.LatestReleaseURL != want {
		t.Fatalf("LatestReleaseURL = %q, want %q", c.LatestReleaseURL, want)
	}
	if c.HTTPClient == nil {
		t.Fatal("expected non-nil HTTPClient")
	}
	if c.CacheTTL != DefaultCacheTTL {
		t.Fatalf("CacheTTL = %v, want %v", c.CacheTTL, DefaultCacheTTL)
	}
}

func TestCheckSkipsNonReleaseVersions(t *testing.T) {
	c := NewChecker("owner", "repo")
	c.HTTPClient = stubHTTPDoer{
		do: func(req *http.Request) (*http.Response, error) {
			t.Fatalf("unexpected HTTP request to %s", req.URL.String())
			return nil, nil
		},
	}

	release, err := c.Check(context.Background(), "dev")
	if err != nil {
		t.Fatalf("Check() error = %v", err)
	}
	if release != nil {
		t.Fatalf("expected nil release for non-parseable version, got %+v", release)
	}
}

func TestCheckReportsAvailableUpdate(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":"v1.2.0","html_url":"https://example.com/v1.2.0","body":"Release notes"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	release, err := c.Check(context.Background(), "1.0.0")
	if err != nil {
		t.Fatalf("Check() error = %v", err)
	}
	if release == nil {
		t.Fatal("expected release, got nil")
	}
	if release.TagName != "v1.2.0" {
		t.Fatalf("TagName = %q, want %q", release.TagName, "v1.2.0")
	}
	if release.HTMLURL != "https://example.com/v1.2.0" {
		t.Fatalf("HTMLURL = %q, want %q", release.HTMLURL, "https://example.com/v1.2.0")
	}
	if release.Body != "Release notes" {
		t.Fatalf("Body = %q, want %q", release.Body, "Release notes")
	}
}

func TestCheckReportsUpToDate(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":"v1.10.0","html_url":"https://example.com/v1.10.0"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	release, err := c.Check(context.Background(), "v1.10.0")
	if err != nil {
		t.Fatalf("Check() error = %v", err)
	}
	if release != nil {
		t.Fatalf("expected nil for up-to-date, got %+v", release)
	}
}

func TestCheckFiltersHistoricalVersions(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":"v4.0.0","html_url":"https://example.com/v4.0.0"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	release, err := c.Check(context.Background(), "0.4.0")
	if err != nil {
		t.Fatalf("Check() error = %v", err)
	}
	if release != nil {
		t.Fatal("expected nil when current major is 0 and latest is > 0")
	}
}

func TestCheckRejectsInvalidLatestTag(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":"latest","html_url":"https://example.com/latest"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	_, err := c.Check(context.Background(), "1.0.0")
	if err == nil {
		t.Fatal("expected invalid tag name to fail")
	}
	if !strings.Contains(err.Error(), "stable semantic version") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestCheckReturnsHTTPError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "nope", http.StatusInternalServerError)
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	_, err := c.Check(context.Background(), "1.0.0")
	if err == nil {
		t.Fatal("expected HTTP error")
	}
	if !strings.Contains(err.Error(), "HTTP 500") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestCheckReturnsDecodeError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	_, err := c.Check(context.Background(), "1.0.0")
	if err == nil {
		t.Fatal("expected decode error")
	}
	if !strings.Contains(err.Error(), "decode latest release response") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestCheckReturnsTimeoutError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(50 * time.Millisecond)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":"v1.0.1","html_url":"https://example.com/v1.0.1"}`))
	}))
	defer server.Close()

	client := server.Client()
	client.Timeout = 10 * time.Millisecond

	c := NewChecker("owner", "repo")
	c.HTTPClient = client
	c.LatestReleaseURL = server.URL

	_, err := c.Check(context.Background(), "1.0.0")
	if err == nil {
		t.Fatal("expected timeout error")
	}
	if !strings.Contains(err.Error(), "request latest release") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestCheckRejectsDraftRelease(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"draft":true,"tag_name":"v1.0.0","html_url":"https://example.com/v1.0.0"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	_, err := c.Check(context.Background(), "0.9.0")
	if err == nil {
		t.Fatal("expected error for draft release")
	}
	if !strings.Contains(err.Error(), "draft") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestCheckRejectsPrerelease(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"prerelease":true,"tag_name":"v1.0.0","html_url":"https://example.com/v1.0.0"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	_, err := c.Check(context.Background(), "0.9.0")
	if err == nil {
		t.Fatal("expected error for prerelease")
	}
	if !strings.Contains(err.Error(), "prerelease") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestCheckRejectsEmptyTagName(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":"   ","html_url":"https://example.com/"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	_, err := c.Check(context.Background(), "1.0.0")
	if err == nil {
		t.Fatal("expected error for empty tag name")
	}
	if !strings.Contains(err.Error(), "did not include a tag name") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestCheckRateLimitExceeded(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-RateLimit-Remaining", "0")
		w.WriteHeader(http.StatusForbidden)
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	_, err := c.Check(context.Background(), "1.0.0")
	if err == nil {
		t.Fatal("expected error for rate limit exceeded")
	}
	if !strings.Contains(err.Error(), "rate limit exceeded") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestCheckUsesCache(t *testing.T) {
	requestCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount++
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":"v1.5.0","html_url":"https://example.com/v1.5.0"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	_, _ = c.Check(context.Background(), "1.0.0")
	if requestCount != 1 {
		t.Fatalf("expected 1 HTTP request for first check, got %d", requestCount)
	}

	_, _ = c.Check(context.Background(), "1.0.0")
	if requestCount != 1 {
		t.Fatalf("expected cache hit (still 1 request), got %d", requestCount)
	}
}

func TestCheckForceBypassesCache(t *testing.T) {
	requestCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount++
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":"v1.6.0","html_url":"https://example.com/v1.6.0"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	_, _ = c.Check(context.Background(), "1.0.0")
	if requestCount != 1 {
		t.Fatalf("expected 1 HTTP request, got %d", requestCount)
	}

	_, _ = c.CheckWithForce(context.Background(), "1.0.0", true)
	if requestCount != 2 {
		t.Fatalf("expected 2 HTTP requests with force, got %d", requestCount)
	}
}

func TestCheckCacheExpiry(t *testing.T) {
	requestCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount++
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":"v1.5.0","html_url":"https://example.com/v1.5.0"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL
	c.CacheTTL = 1 * time.Millisecond

	_, _ = c.Check(context.Background(), "1.0.0")
	if requestCount != 1 {
		t.Fatalf("expected 1 HTTP request, got %d", requestCount)
	}

	time.Sleep(5 * time.Millisecond)

	_, _ = c.Check(context.Background(), "1.0.0")
	if requestCount != 2 {
		t.Fatalf("expected cache expiry to trigger re-fetch (2 requests), got %d", requestCount)
	}
}

func TestCheckNilHTTPClient(t *testing.T) {
	c := NewChecker("owner", "repo")
	c.HTTPClient = nil
	c.LatestReleaseURL = "http://localhost:1"

	_, err := c.Check(context.Background(), "1.0.0")
	if err == nil {
		t.Fatal("expected error with nil HTTPClient")
	}
}

func TestCheckReturnsNetworkError(t *testing.T) {
	c := NewChecker("owner", "repo")
	c.HTTPClient = stubHTTPDoer{
		do: func(req *http.Request) (*http.Response, error) {
			return nil, fmt.Errorf("connection refused")
		},
	}
	c.LatestReleaseURL = "http://localhost:1"

	_, err := c.Check(context.Background(), "1.0.0")
	if err == nil {
		t.Fatal("expected network error")
	}
	if !strings.Contains(err.Error(), "request latest release") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestCheckURLTrimming(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":"v1.2.0","html_url":"https://example.com/v1.2.0"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = "  " + server.URL + "  "

	release, err := c.Check(context.Background(), "1.0.0")
	if err != nil {
		t.Fatalf("Check() error = %v", err)
	}
	if release == nil || release.TagName != "v1.2.0" {
		t.Fatalf("TagName = %v, want v1.2.0", release)
	}
}

func TestCheckReturnsHTTP404(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "not found", http.StatusNotFound)
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	_, err := c.Check(context.Background(), "1.0.0")
	if err == nil {
		t.Fatal("expected HTTP 404 error")
	}
	if !strings.Contains(err.Error(), "HTTP 404") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestCheckParsesAssets(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"tag_name":"v2.0.0",
			"html_url":"https://example.com/v2.0.0",
			"assets":[
				{"name":"app-darwin-arm64.tar.gz","browser_download_url":"https://example.com/dl/app.tar.gz","size":12345}
			]
		}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	release, err := c.Check(context.Background(), "1.0.0")
	if err != nil {
		t.Fatalf("Check() error = %v", err)
	}
	if release == nil {
		t.Fatal("expected release, got nil")
	}
	if len(release.Assets) != 1 {
		t.Fatalf("len(Assets) = %d, want 1", len(release.Assets))
	}
	if release.Assets[0].Name != "app-darwin-arm64.tar.gz" {
		t.Fatalf("Asset.Name = %q, want %q", release.Assets[0].Name, "app-darwin-arm64.tar.gz")
	}
	if release.Assets[0].Size != 12345 {
		t.Fatalf("Asset.Size = %d, want 12345", release.Assets[0].Size)
	}
}

func TestParseStableVersionEmpty(t *testing.T) {
	_, ok := parseStableVersion("")
	if ok {
		t.Fatal("parseStableVersion(\"\") should return ok=false")
	}
}

func TestParseStableVersionWhitespaceOnly(t *testing.T) {
	_, ok := parseStableVersion("   ")
	if ok {
		t.Fatal("parseStableVersion(\"   \") should return ok=false")
	}
}

func TestParseStableVersionNegative(t *testing.T) {
	_, ok := parseStableVersion("-1.0.0")
	if ok {
		t.Fatal("parseStableVersion(\"-1.0.0\") should return ok=false")
	}
}

func TestParseStableVersionPrerelease(t *testing.T) {
	_, ok := parseStableVersion("1.0.0-alpha")
	if ok {
		t.Fatal("parseStableVersion(\"1.0.0-alpha\") should return ok=false")
	}
}

func TestParseStableVersionBuildMetadata(t *testing.T) {
	_, ok := parseStableVersion("1.0.0+build")
	if ok {
		t.Fatal("parseStableVersion(\"1.0.0+build\") should return ok=false")
	}
}

func TestParseStableVersionTooFewParts(t *testing.T) {
	_, ok := parseStableVersion("1.0")
	if ok {
		t.Fatal("parseStableVersion(\"1.0\") should return ok=false")
	}
}

func TestParseStableVersionTooManyParts(t *testing.T) {
	_, ok := parseStableVersion("1.0.0.0")
	if ok {
		t.Fatal("parseStableVersion(\"1.0.0.0\") should return ok=false")
	}
}

func TestParseStableVersionEmptyPart(t *testing.T) {
	_, ok := parseStableVersion("1..0")
	if ok {
		t.Fatal("parseStableVersion(\"1..0\") should return ok=false")
	}
}

func TestParseStableVersionNonNumeric(t *testing.T) {
	_, ok := parseStableVersion("a.b.c")
	if ok {
		t.Fatal("parseStableVersion(\"a.b.c\") should return ok=false")
	}
}

func TestParseStableVersionWithVPrefix(t *testing.T) {
	v, ok := parseStableVersion("v1.2.3")
	if !ok {
		t.Fatal("parseStableVersion(\"v1.2.3\") should return ok=true")
	}
	if v.major != 1 || v.minor != 2 || v.patch != 3 {
		t.Fatalf("got %d.%d.%d, want 1.2.3", v.major, v.minor, v.patch)
	}
}

func TestParseStableVersionWithoutVPrefix(t *testing.T) {
	v, ok := parseStableVersion("1.2.3")
	if !ok {
		t.Fatal("parseStableVersion(\"1.2.3\") should return ok=true")
	}
	if v.major != 1 || v.minor != 2 || v.patch != 3 {
		t.Fatalf("got %d.%d.%d, want 1.2.3", v.major, v.minor, v.patch)
	}
}

func TestCompareStableVersionsEqual(t *testing.T) {
	left, _ := parseStableVersion("1.0.0")
	right, _ := parseStableVersion("1.0.0")
	if compareStableVersions(left, right) != 0 {
		t.Fatal("expected 1.0.0 == 1.0.0")
	}
}

func TestCompareStableVersionsLeftGreaterMajor(t *testing.T) {
	left, _ := parseStableVersion("2.0.0")
	right, _ := parseStableVersion("1.9.9")
	if compareStableVersions(left, right) != 1 {
		t.Fatal("expected 2.0.0 > 1.9.9")
	}
}

func TestCompareStableVersionsRightGreaterMajor(t *testing.T) {
	left, _ := parseStableVersion("1.0.0")
	right, _ := parseStableVersion("2.0.0")
	if compareStableVersions(left, right) != -1 {
		t.Fatal("expected 1.0.0 < 2.0.0")
	}
}

func TestCompareStableVersionsRightGreaterMinor(t *testing.T) {
	left, _ := parseStableVersion("1.1.0")
	right, _ := parseStableVersion("1.2.0")
	if compareStableVersions(left, right) != -1 {
		t.Fatal("expected 1.1.0 < 1.2.0")
	}
}

func TestCompareStableVersionsRightGreaterPatch(t *testing.T) {
	left, _ := parseStableVersion("1.0.1")
	right, _ := parseStableVersion("1.0.2")
	if compareStableVersions(left, right) != -1 {
		t.Fatal("expected 1.0.1 < 1.0.2")
	}
}

func TestCompareStableVersionsLeftGreaterMinor(t *testing.T) {
	left, _ := parseStableVersion("1.2.0")
	right, _ := parseStableVersion("1.1.0")
	if compareStableVersions(left, right) != 1 {
		t.Fatal("expected 1.2.0 > 1.1.0")
	}
}

func TestCompareStableVersionsLeftGreaterPatch(t *testing.T) {
	left, _ := parseStableVersion("1.0.2")
	right, _ := parseStableVersion("1.0.1")
	if compareStableVersions(left, right) != 1 {
		t.Fatal("expected 1.0.2 > 1.0.1")
	}
}

func TestStableVersionString(t *testing.T) {
	v := stableVersion{major: 1, minor: 2, patch: 3}
	if v.String() != "1.2.3" {
		t.Fatalf("String() = %q, want %q", v.String(), "1.2.3")
	}
}

func TestCheckSetsUserAgent(t *testing.T) {
	var gotUA string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotUA = r.Header.Get("User-Agent")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":"v1.0.0","html_url":"https://example.com"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	_, _ = c.Check(context.Background(), "1.2.3")

	want := "symaira-updatecheck/1.2.3"
	if gotUA != want {
		t.Fatalf("User-Agent = %q, want %q", gotUA, want)
	}
}

func TestCheckSetsAcceptHeader(t *testing.T) {
	var gotAccept string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAccept = r.Header.Get("Accept")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":"v1.0.0","html_url":"https://example.com"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	_, _ = c.Check(context.Background(), "1.0.0")

	want := "application/vnd.github+json"
	if gotAccept != want {
		t.Fatalf("Accept = %q, want %q", gotAccept, want)
	}
}

func TestCheckRespectsContextCancellation(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":"v1.0.0","html_url":"https://example.com"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	_, err := c.Check(ctx, "1.0.0")
	if err == nil {
		t.Fatal("expected error for cancelled context")
	}
}

func TestCheckEmptyLatestReleaseURL(t *testing.T) {
	c := NewChecker("owner", "repo")
	c.HTTPClient = stubHTTPDoer{
		do: func(req *http.Request) (*http.Response, error) {
			return &http.Response{
				StatusCode: http.StatusOK,
				Body:       io.NopCloser(strings.NewReader(`{"tag_name":"v1.0.0","html_url":"https://example.com"}`)),
				Header:     http.Header{"Content-Type": []string{"application/json"}},
			}, nil
		},
	}
	c.LatestReleaseURL = ""

	_, err := c.Check(context.Background(), "1.0.0")
	if err != nil {
		t.Fatalf("Check() error = %v", err)
	}
}

func TestCheckCacheUnparseableVersion(t *testing.T) {
	requestCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestCount++
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"tag_name":"v1.5.0","html_url":"https://example.com/v1.5.0"}`))
	}))
	defer server.Close()

	c := NewChecker("owner", "repo")
	c.HTTPClient = server.Client()
	c.LatestReleaseURL = server.URL

	_, _ = c.Check(context.Background(), "1.0.0")
	if requestCount != 1 {
		t.Fatalf("expected 1 HTTP request, got %d", requestCount)
	}

	c.mu.Lock()
	c.cache = &cacheEntry{
		timestamp: time.Now(),
		release:   &Release{TagName: "not-a-version"},
	}
	c.mu.Unlock()

	release, err := c.Check(context.Background(), "1.0.0")
	if err != nil {
		t.Fatalf("Check() error = %v", err)
	}
	if requestCount != 2 {
		t.Fatalf("expected 2 HTTP requests due to unparseable cache version, got %d", requestCount)
	}
	if release == nil || release.TagName != "v1.5.0" {
		t.Fatalf("TagName = %v, want v1.5.0", release)
	}
}
