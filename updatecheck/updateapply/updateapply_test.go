package updateapply

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"encoding/hex"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/danieljustus/symaira-corekit/updatecheck"
	"github.com/danieljustus/symaira-corekit/updatecheck/cosign"
)

func sha256Hex(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func newTestServer(t *testing.T, assetBody []byte, checksumsBody string) (*httptest.Server, string, string) {
	t.Helper()
	var assetURL, checksumsURL string
	mux := http.NewServeMux()
	mux.HandleFunc("/asset", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write(assetBody)
	})
	mux.HandleFunc("/checksums.txt", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(checksumsBody))
	})
	server := httptest.NewServer(mux)
	assetURL = server.URL + "/asset"
	checksumsURL = server.URL + "/checksums.txt"
	return server, assetURL, checksumsURL
}

// TestNewApplierDefaults asserts the default client's security properties
// rather than its identity. The download path replaces the running binary, so
// it must not fall back to a client without a timeout, without a TLS floor,
// and willing to follow redirects to any host.
func TestNewApplierDefaults(t *testing.T) {
	a := NewApplier()
	if a == nil {
		t.Fatal("NewApplier() returned nil")
	}

	client, ok := a.HTTPClient.(*http.Client)
	if !ok {
		t.Fatalf("HTTPClient = %T, want *http.Client", a.HTTPClient)
	}
	if client == http.DefaultClient {
		t.Fatal("HTTPClient must not be http.DefaultClient: no timeout, no TLS floor, follows any redirect")
	}
	if client.Timeout <= 0 {
		t.Error("HTTPClient.Timeout must be set so a stalled download cannot hang forever")
	}
	if client.CheckRedirect == nil {
		t.Fatal("HTTPClient.CheckRedirect must be set so downloads cannot be bounced off GitHub")
	}
	if err := client.CheckRedirect(
		&http.Request{URL: mustParseURL(t, "https://evil.example/payload")},
		[]*http.Request{{URL: mustParseURL(t, "https://github.com/o/r/releases/download/v1/asset")}},
	); err == nil {
		t.Error("redirect to a non-GitHub host must be refused on the download path")
	}
	if err := client.CheckRedirect(
		&http.Request{URL: mustParseURL(t, "https://objects.githubusercontent.com/blob")},
		[]*http.Request{{URL: mustParseURL(t, "https://github.com/o/r/releases/download/v1/asset")}},
	); err != nil {
		t.Errorf("redirect to the GitHub asset CDN must be allowed, got %v", err)
	}

	tr, ok := client.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("Transport = %T, want *http.Transport", client.Transport)
	}
	if tr.TLSClientConfig == nil || tr.TLSClientConfig.MinVersion != tls.VersionTLS13 {
		t.Error("HTTPClient must enforce a TLS 1.3 minimum")
	}

	if a.GOOS != runtime.GOOS {
		t.Errorf("GOOS = %q, want %q", a.GOOS, runtime.GOOS)
	}
	if a.GOARCH != runtime.GOARCH {
		t.Errorf("GOARCH = %q, want %q", a.GOARCH, runtime.GOARCH)
	}
}

// TestDownloadNilClientUsesSecureDefault covers the nil-HTTPClient fallback in
// download, which previously reached for http.DefaultClient.
func TestDownloadNilClientUsesSecureDefault(t *testing.T) {
	a := &Applier{}
	_, _, err := a.download(context.Background(), updatecheck.Asset{
		Name:               "asset",
		BrowserDownloadURL: "https://127.0.0.1:1/asset",
	})
	if err == nil {
		t.Fatal("expected the request to fail against a closed port")
	}
	// The point is that a client was constructed and used at all; a nil
	// fallback would have panicked or silently used the unhardened default.
	if !strings.Contains(err.Error(), "request asset") {
		t.Errorf("error = %v, want a request failure from the fallback client", err)
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

func TestApplyInstallsMatchingAsset(t *testing.T) {
	assetBody := []byte("fake-binary-content")
	sum := sha256Hex(assetBody)
	checksums := fmt.Sprintf("%s  mytool_linux_amd64\n", sum)

	server, assetURL, checksumsURL := newTestServer(t, assetBody, checksums)
	defer server.Close()

	release := &updatecheck.Release{
		TagName: "v1.2.0",
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: assetURL},
			{Name: "checksums.txt", BrowserDownloadURL: checksumsURL},
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")
	if err := os.WriteFile(target, []byte("old-binary"), 0o755); err != nil { //nolint:gosec
		t.Fatalf("seed target: %v", err)
	}

	a := &Applier{HTTPClient: http.DefaultClient, GOOS: "linux", GOARCH: "amd64"}
	if err := a.Apply(context.Background(), release, target); err != nil {
		t.Fatalf("Apply() error = %v", err)
	}

	got, err := os.ReadFile(target) //nolint:gosec
	if err != nil {
		t.Fatalf("read target: %v", err)
	}
	if string(got) != string(assetBody) {
		t.Fatalf("target content = %q, want %q", got, assetBody)
	}
	if _, err := os.Stat(target + ".bak"); !os.IsNotExist(err) {
		t.Fatalf("expected backup file to be cleaned up, stat err = %v", err)
	}
}

func TestApplyAbortsOnChecksumMismatch(t *testing.T) {
	assetBody := []byte("fake-binary-content")
	checksums := "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef  mytool_linux_amd64\n"

	server, assetURL, checksumsURL := newTestServer(t, assetBody, checksums)
	defer server.Close()

	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: assetURL},
			{Name: "checksums.txt", BrowserDownloadURL: checksumsURL},
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")
	original := []byte("old-binary")
	if err := os.WriteFile(target, original, 0o755); err != nil { //nolint:gosec
		t.Fatalf("seed target: %v", err)
	}

	a := &Applier{HTTPClient: http.DefaultClient, GOOS: "linux", GOARCH: "amd64"}
	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected checksum mismatch error, got nil")
	}

	got, readErr := os.ReadFile(target) //nolint:gosec
	if readErr != nil {
		t.Fatalf("read target: %v", readErr)
	}
	if string(got) != string(original) {
		t.Fatalf("target was modified despite checksum mismatch: got %q, want %q", got, original)
	}
}

func TestApplyFailsOnMissingAsset(t *testing.T) {
	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_darwin_arm64", BrowserDownloadURL: "https://example.com/asset"},
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")

	a := &Applier{HTTPClient: http.DefaultClient, GOOS: "linux", GOARCH: "amd64"}
	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected error for missing matching asset, got nil")
	}
}

func TestApplyFailsOnNonWritableTarget(t *testing.T) {
	assetBody := []byte("fake-binary-content")
	sum := sha256Hex(assetBody)
	checksums := fmt.Sprintf("%s  mytool_linux_amd64\n", sum)

	server, assetURL, checksumsURL := newTestServer(t, assetBody, checksums)
	defer server.Close()

	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: assetURL},
			{Name: "checksums.txt", BrowserDownloadURL: checksumsURL},
		},
	}

	dir := t.TempDir()
	if err := os.Chmod(dir, 0o500); err != nil { //nolint:gosec
		t.Fatalf("chmod dir: %v", err)
	}
	defer func() { _ = os.Chmod(dir, 0o700) }() //nolint:gosec

	target := filepath.Join(dir, "mytool")

	a := &Applier{HTTPClient: http.DefaultClient, GOOS: "linux", GOARCH: "amd64"}
	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected error for non-writable install location, got nil")
	}
}

func TestAtomicSwapRollsBackOnFailedRename(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")
	original := []byte("old-binary")
	if err := os.WriteFile(target, original, 0o755); err != nil { //nolint:gosec
		t.Fatalf("seed target: %v", err)
	}

	// newPath does not exist, so os.Rename must fail and roll back.
	missingNew := filepath.Join(dir, "does-not-exist")
	err := atomicSwap(missingNew, target, nil)
	if err == nil {
		t.Fatal("expected atomicSwap to fail for missing source, got nil")
	}

	got, readErr := os.ReadFile(target) //nolint:gosec
	if readErr != nil {
		t.Fatalf("read target after rollback: %v", readErr)
	}
	if string(got) != string(original) {
		t.Fatalf("target after failed swap = %q, want original %q (rollback did not restore)", got, original)
	}
	if _, err := os.Stat(target + ".bak"); !os.IsNotExist(err) {
		t.Fatalf("expected backup file to be cleaned up after rollback, stat err = %v", err)
	}
}

func TestApplyRejectsNilRelease(t *testing.T) {
	a := &Applier{HTTPClient: http.DefaultClient}
	err := a.Apply(context.Background(), nil, filepath.Join(t.TempDir(), "mytool"))
	if err == nil {
		t.Fatal("expected error for nil release, got nil")
	}
}

func TestApplyExtractRejectsTraversalArchive(t *testing.T) {
	// A zip entry named ../evil must never be installed anywhere: the
	// extract package rejects it before any file is written.
	assetBody := testBuildZip(map[string]string{"../evil": "evil-binary"})
	checksums := fmt.Sprintf("%s  mytool_linux_amd64\n", sha256Hex(assetBody))

	server, assetURL, checksumsURL := newTestServer(t, assetBody, checksums)
	defer server.Close()

	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: assetURL},
			{Name: "checksums.txt", BrowserDownloadURL: checksumsURL},
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")
	original := []byte("old-binary")
	if err := os.WriteFile(target, original, 0o755); err != nil { //nolint:gosec
		t.Fatalf("seed target: %v", err)
	}

	a := &Applier{
		HTTPClient:    http.DefaultClient,
		GOOS:          "linux",
		GOARCH:        "amd64",
		ExtractBinary: "mytool",
	}
	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected error for traversal archive, got nil")
	}

	got, readErr := os.ReadFile(target) //nolint:gosec
	if readErr != nil {
		t.Fatalf("read target: %v", readErr)
	}
	if string(got) != string(original) {
		t.Fatalf("target was modified despite traversal archive: got %q, want %q", got, original)
	}
}

func TestApplyExtractRejectsTraversalReturnPath(t *testing.T) {
	// Defense in depth: an extracted path containing ".." as a substring
	// (which the extract package's segment-level validation allows, e.g.
	// a version directory named tool..v1.0.0) must be rejected before it
	// reaches the file operations in Apply.
	assetBody := testBuildZip(map[string]string{"tool..v1.0.0/mytool": "binary"})
	checksums := fmt.Sprintf("%s  mytool_linux_amd64\n", sha256Hex(assetBody))

	server, assetURL, checksumsURL := newTestServer(t, assetBody, checksums)
	defer server.Close()

	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: assetURL},
			{Name: "checksums.txt", BrowserDownloadURL: checksumsURL},
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")
	original := []byte("old-binary")
	if err := os.WriteFile(target, original, 0o755); err != nil { //nolint:gosec
		t.Fatalf("seed target: %v", err)
	}

	a := &Applier{
		HTTPClient:    http.DefaultClient,
		GOOS:          "linux",
		GOARCH:        "amd64",
		ExtractBinary: "mytool",
	}
	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected error for traversal-containing extracted path, got nil")
	}
	if !strings.Contains(err.Error(), "escapes extraction directory") {
		t.Fatalf("expected containment error, got: %v", err)
	}

	got, readErr := os.ReadFile(target) //nolint:gosec
	if readErr != nil {
		t.Fatalf("read target: %v", readErr)
	}
	if string(got) != string(original) {
		t.Fatalf("target was modified despite unsafe extracted path: got %q, want %q", got, original)
	}
}

func TestApplyRejectsEmptyTargetPath(t *testing.T) {
	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{{Name: "mytool_linux_amd64", BrowserDownloadURL: "https://example.com/asset"}},
	}
	a := &Applier{HTTPClient: http.DefaultClient, GOOS: "linux", GOARCH: "amd64"}
	err := a.Apply(context.Background(), release, "")
	if err == nil {
		t.Fatal("expected error for empty targetPath, got nil")
	}
	err = a.Apply(context.Background(), release, "   ")
	if err == nil {
		t.Fatal("expected error for whitespace-only targetPath, got nil")
	}
}

func TestApplyFailsWhenChecksumsMissingEntryForAsset(t *testing.T) {
	assetBody := []byte("fake-binary-content")
	// checksums.txt lists a different asset name than the one selected.
	checksums := fmt.Sprintf("%s  some_other_asset\n", sha256Hex(assetBody))

	server, assetURL, checksumsURL := newTestServer(t, assetBody, checksums)
	defer server.Close()

	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: assetURL},
			{Name: "checksums.txt", BrowserDownloadURL: checksumsURL},
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")
	original := []byte("old-binary")
	if err := os.WriteFile(target, original, 0o755); err != nil { //nolint:gosec
		t.Fatalf("seed target: %v", err)
	}

	a := &Applier{HTTPClient: http.DefaultClient, GOOS: "linux", GOARCH: "amd64"}
	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected error for missing checksum entry, got nil")
	}

	got, readErr := os.ReadFile(target) //nolint:gosec
	if readErr != nil {
		t.Fatalf("read target: %v", readErr)
	}
	if string(got) != string(original) {
		t.Fatalf("target was modified despite missing checksum entry: got %q, want %q", got, original)
	}
}

func TestSelectAssetSkipsChecksumsFile(t *testing.T) {
	assets := []updatecheck.Asset{
		{Name: "checksums.txt"},
		{Name: "mytool_darwin_amd64_checksums.txt"},
		{Name: "mytool_linux_amd64"},
	}
	asset, err := selectAsset(assets, "linux", "amd64")
	if err != nil {
		t.Fatalf("selectAsset() error = %v", err)
	}
	if asset.Name != "mytool_linux_amd64" {
		t.Fatalf("selectAsset() = %q, want %q", asset.Name, "mytool_linux_amd64")
	}
}

func TestApplyFailsOnNon200AssetDownload(t *testing.T) {
	assetBody := []byte("fake-binary-content")
	checksums := fmt.Sprintf("%s  mytool_linux_amd64\n", sha256Hex(assetBody))

	mux := http.NewServeMux()
	mux.HandleFunc("/asset", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	})
	mux.HandleFunc("/checksums.txt", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(checksums))
	})
	server := httptest.NewServer(mux)
	defer server.Close()

	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: server.URL + "/asset"},
			{Name: "checksums.txt", BrowserDownloadURL: server.URL + "/checksums.txt"},
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")
	if err := os.WriteFile(target, []byte("old-binary"), 0o755); err != nil { //nolint:gosec
		t.Fatalf("seed target: %v", err)
	}

	a := &Applier{HTTPClient: http.DefaultClient, GOOS: "linux", GOARCH: "amd64"}
	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected error for HTTP 500 asset download, got nil")
	}
}

func TestFetchChecksumsFailsWhenAssetMissing(t *testing.T) {
	assetBody := []byte("fake-binary-content")
	server, assetURL, _ := newTestServer(t, assetBody, "")
	defer server.Close()

	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: assetURL},
			// No "checksums.txt" asset in the release at all.
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")

	a := &Applier{HTTPClient: http.DefaultClient, GOOS: "linux", GOARCH: "amd64"}
	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected error for release with no checksums.txt asset, got nil")
	}
}

func TestFetchChecksumsFailsOnNoParseableEntries(t *testing.T) {
	assetBody := []byte("fake-binary-content")
	// checksums.txt exists but has no valid "<sha>  <name>" lines.
	server, assetURL, checksumsURL := newTestServer(t, assetBody, "not a valid checksums file\n")
	defer server.Close()

	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: assetURL},
			{Name: "checksums.txt", BrowserDownloadURL: checksumsURL},
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")

	a := &Applier{HTTPClient: http.DefaultClient, GOOS: "linux", GOARCH: "amd64"}
	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected error for checksums.txt with no parseable entries, got nil")
	}
}

func TestApplyFailsOnIncompleteDownload(t *testing.T) {
	assetBody := []byte("fake-binary-content")
	checksums := fmt.Sprintf("%s  mytool_linux_amd64\n", sha256Hex(assetBody))

	mux := http.NewServeMux()
	mux.HandleFunc("/asset", func(w http.ResponseWriter, r *http.Request) {
		// Claim a larger body than what is actually written, then cut the
		// connection short by returning early — downloadToTemp must detect
		// the short read via the advertised Content-Length.
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(assetBody)+100))
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(assetBody)
	})
	mux.HandleFunc("/checksums.txt", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(checksums))
	})
	server := httptest.NewServer(mux)
	defer server.Close()

	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: server.URL + "/asset"},
			{Name: "checksums.txt", BrowserDownloadURL: server.URL + "/checksums.txt"},
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")
	if err := os.WriteFile(target, []byte("old-binary"), 0o755); err != nil { //nolint:gosec
		t.Fatalf("seed target: %v", err)
	}

	a := &Applier{HTTPClient: http.DefaultClient, GOOS: "linux", GOARCH: "amd64"}
	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected error for incomplete download, got nil")
	}
}

type stubDoer struct {
	do func(req *http.Request) (*http.Response, error)
}

func (s stubDoer) Do(req *http.Request) (*http.Response, error) {
	return s.do(req)
}

func TestApplyFailsWhenHTTPClientErrors(t *testing.T) {
	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: "https://example.invalid/asset"},
			{Name: "checksums.txt", BrowserDownloadURL: "https://example.invalid/checksums.txt"},
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")

	a := &Applier{
		HTTPClient: stubDoer{do: func(req *http.Request) (*http.Response, error) {
			return nil, fmt.Errorf("simulated transport failure")
		}},
		GOOS:   "linux",
		GOARCH: "amd64",
	}
	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected error when the HTTP client fails, got nil")
	}
}

func TestApplyFailsOnMalformedAssetURL(t *testing.T) {
	// A control character in the URL makes http.NewRequestWithContext itself
	// fail (net/url: invalid control character in URL), before any request
	// is ever sent.
	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: "https://example.invalid/asset"},
			{Name: "checksums.txt", BrowserDownloadURL: "https://example.invalid/checksums\x7f.txt"},
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")

	a := &Applier{HTTPClient: http.DefaultClient, GOOS: "linux", GOARCH: "amd64"}
	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected error for a malformed asset URL, got nil")
	}
}

func TestDownloadToTempFailsWhenStagingDirUnwritable(t *testing.T) {
	assetBody := []byte("fake-binary-content")
	checksums := fmt.Sprintf("%s  mytool_linux_amd64\n", sha256Hex(assetBody))
	server, assetURL, _ := newTestServer(t, assetBody, checksums)
	defer server.Close()

	// The staging directory is now passed in explicitly (it is the install
	// directory, so the final rename stays on one filesystem) rather than
	// resolved from $TMPDIR. Point it at a directory that does not exist so
	// the os.CreateTemp call inside downloadToTemp fails.
	stagingDir := filepath.Join(t.TempDir(), "does-not-exist")

	a := &Applier{HTTPClient: http.DefaultClient, GOOS: "linux", GOARCH: "amd64"}
	_, _, err := a.downloadToTemp(context.Background(), stagingDir, updatecheck.Asset{
		Name:               "mytool_linux_amd64",
		BrowserDownloadURL: assetURL,
	})
	if err == nil {
		t.Fatal("expected error when the staging directory is unwritable, got nil")
	}
	if !strings.Contains(err.Error(), "create temp file") {
		t.Errorf("error = %v, want a temp-file creation failure", err)
	}
}

// erroringReadCloser returns a fixed error on Read after yielding no bytes,
// simulating a connection that dies mid-download (a non-EOF read error).
type erroringReadCloser struct{}

func (erroringReadCloser) Read(_ []byte) (int, error) {
	return 0, fmt.Errorf("simulated read failure")
}

func (erroringReadCloser) Close() error { return nil }

func TestDownloadToTempFailsOnBodyReadError(t *testing.T) {
	checksums := fmt.Sprintf("%s  mytool_linux_amd64\n", sha256Hex([]byte("fake-binary-content")))
	checksumsServer, _, checksumsURL := newTestServer(t, nil, checksums)
	defer checksumsServer.Close()

	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: "https://example.invalid/asset"},
			{Name: "checksums.txt", BrowserDownloadURL: checksumsURL},
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")

	a := &Applier{
		HTTPClient: stubDoer{do: func(req *http.Request) (*http.Response, error) {
			if req.URL.String() == checksumsURL {
				return http.DefaultClient.Do(req)
			}
			return &http.Response{
				StatusCode: http.StatusOK,
				Body:       erroringReadCloser{},
			}, nil
		}},
		GOOS:   "linux",
		GOARCH: "amd64",
	}
	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected error when the asset body read fails, got nil")
	}
}

func TestApplyVerifiesCosignOverExactChecksumsBytes(t *testing.T) {
	// Multi-entry checksums.txt with non-canonical separators: the second
	// line uses a single space and the third a tab. A map rebuild (the old
	// behaviour) normalizes every separator to two spaces and randomizes
	// entry order, so it can never reproduce these exact bytes — cosign
	// would verify a document nobody signed. Byte-exact verification must
	// hand cosign the original downloaded bytes instead.
	assetBody := []byte("fake-binary-content")
	checksumsBody := strings.Join([]string{
		sha256Hex(assetBody) + "  mytool_linux_amd64",
		strings.Repeat("a", 64) + " mytool_darwin_arm64",
		strings.Repeat("b", 64) + "	mytool_windows_amd64",
	}, "\n") + "\n"

	mux := http.NewServeMux()
	mux.HandleFunc("/asset", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write(assetBody)
	})
	mux.HandleFunc("/checksums.txt", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(checksumsBody))
	})
	mux.HandleFunc("/v1.2.0/mytool_1.2.0_checksums.txt.sig", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("fake-signature"))
	})
	mux.HandleFunc("/v1.2.0/mytool_1.2.0_checksums.txt.pem", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("fake-certificate"))
	})
	server := httptest.NewTLSServer(mux)
	defer server.Close()
	serverClient := server.Client()

	release := &updatecheck.Release{
		TagName: "v1.2.0",
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: server.URL + "/asset"},
			{Name: "checksums.txt", BrowserDownloadURL: server.URL + "/checksums.txt"},
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "mytool")
	if err := os.WriteFile(target, []byte("old-binary"), 0o755); err != nil { //nolint:gosec
		t.Fatalf("seed target: %v", err)
	}

	// Stub the cosign CLI with a fake binary that captures the content
	// file VerifySignature writes (its last argument) and exits 0,
	// instead of actually verifying anything.
	captureFile := filepath.Join(dir, "captured-checksums")
	fakeCosignDir := t.TempDir()
	fakeCosign := filepath.Join(fakeCosignDir, "cosign")
	script := "#!/bin/sh\nfor last; do :; done\ncp \"$last\" \"$COSIGN_CONTENT_CAPTURE\"\n"
	if err := os.WriteFile(fakeCosign, []byte(script), 0o755); err != nil { //nolint:gosec
		t.Fatalf("write fake cosign binary: %v", err)
	}
	t.Setenv("PATH", fakeCosignDir+string(os.PathListSeparator)+os.Getenv("PATH"))
	t.Setenv("COSIGN_CONTENT_CAPTURE", captureFile)

	a := &Applier{
		HTTPClient: serverClient,
		GOOS:       "linux",
		GOARCH:     "amd64",
		BinaryName: "mytool",
		CosignConfig: &cosign.Config{
			Repo:       "testowner/testrepo",
			BinaryName: "mytool",
			// Signature and certificate are served by the test server
			// above; the fake cosign ignores them.
			DownloadBaseURL: server.URL,
			HTTPClient:      serverClient,
		},
	}
	if err := a.Apply(context.Background(), release, target); err != nil {
		t.Fatalf("Apply() error = %v", err)
	}

	// The exact downloaded bytes — original order and whitespace — must be
	// what was written for cosign to verify, not a map-rebuilt document.
	got, err := os.ReadFile(captureFile) //nolint:gosec
	if err != nil {
		t.Fatalf("read captured cosign content: %v", err)
	}
	if string(got) != checksumsBody {
		t.Fatalf("cosign content file has %d bytes, want the exact %d downloaded bytes (order and whitespace preserved)", len(got), len(checksumsBody))
	}

	// The install itself must have completed.
	installed, err := os.ReadFile(target) //nolint:gosec
	if err != nil {
		t.Fatalf("read target: %v", err)
	}
	if string(installed) != string(assetBody) {
		t.Fatalf("target content = %q, want %q", installed, assetBody)
	}
}

// TestApplyStagesDownloadBesideTarget proves the download is staged in the
// install directory rather than $TMPDIR. Staging in $TMPDIR made the final
// os.Rename a cross-filesystem rename, which fails with EXDEV whenever the
// temp directory and the install directory live on different filesystems —
// the normal Linux layout (/tmp on tmpfs, binary in /usr/local/bin).
//
// The assertion runs inside the Progress callback, the one moment the staged
// file is guaranteed to exist.
func TestApplyStagesDownloadBesideTarget(t *testing.T) {
	assetBody := []byte(strings.Repeat("fake-binary-content", 4096))
	sum := sha256Hex(assetBody)
	checksums := fmt.Sprintf("%s  mytool_linux_amd64\n", sum)

	server, assetURL, checksumsURL := newTestServer(t, assetBody, checksums)
	defer server.Close()

	tmpDir := t.TempDir()
	targetDir := t.TempDir()
	t.Setenv("TMPDIR", tmpDir)

	target := filepath.Join(targetDir, "mytool")
	if err := os.WriteFile(target, []byte("old-binary"), 0o755); err != nil { //nolint:gosec
		t.Fatal(err)
	}

	var sawStagingInTargetDir, sawStagingInTmpDir bool
	a := &Applier{
		HTTPClient: http.DefaultClient,
		GOOS:       "linux",
		GOARCH:     "amd64",
		Progress: func(written, total int64) {
			if globHasStagedFile(t, targetDir) {
				sawStagingInTargetDir = true
			}
			if globHasStagedFile(t, tmpDir) {
				sawStagingInTmpDir = true
			}
		},
	}

	release := &updatecheck.Release{
		TagName: "v1.0.0",
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: assetURL},
			{Name: "checksums.txt", BrowserDownloadURL: checksumsURL},
		},
	}

	if err := a.Apply(context.Background(), release, target); err != nil {
		t.Fatalf("Apply() error = %v", err)
	}

	if !sawStagingInTargetDir {
		t.Error("download was not staged in the install directory; the final rename can cross filesystems")
	}
	if sawStagingInTmpDir {
		t.Error("download was staged in $TMPDIR, which may be on a different filesystem than the target")
	}

	got, err := os.ReadFile(target) //nolint:gosec
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != string(assetBody) {
		t.Error("target binary was not replaced with the downloaded asset")
	}

	// No staging debris may survive a successful run.
	if globHasStagedFile(t, targetDir) {
		t.Error("staging artefacts left behind in the install directory after a successful update")
	}
}

// TestApplyCleansStagingOnChecksumMismatch makes sure the new staging location
// does not leak files next to the user's binary when the update is rejected.
func TestApplyCleansStagingOnChecksumMismatch(t *testing.T) {
	assetBody := []byte("fake-binary-content")
	checksums := fmt.Sprintf("%s  mytool_linux_amd64\n", sha256Hex([]byte("something-else")))

	server, assetURL, checksumsURL := newTestServer(t, assetBody, checksums)
	defer server.Close()

	targetDir := t.TempDir()
	target := filepath.Join(targetDir, "mytool")
	original := []byte("old-binary")
	if err := os.WriteFile(target, original, 0o755); err != nil { //nolint:gosec
		t.Fatal(err)
	}

	a := &Applier{HTTPClient: http.DefaultClient, GOOS: "linux", GOARCH: "amd64"}
	release := &updatecheck.Release{
		TagName: "v1.0.0",
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: assetURL},
			{Name: "checksums.txt", BrowserDownloadURL: checksumsURL},
		},
	}

	if err := a.Apply(context.Background(), release, target); err == nil {
		t.Fatal("expected a checksum mismatch to be rejected")
	}

	if globHasStagedFile(t, targetDir) {
		t.Error("staging artefacts left behind in the install directory after a rejected update")
	}
	got, err := os.ReadFile(target) //nolint:gosec
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != string(original) {
		t.Error("target binary must be untouched when the checksum does not match")
	}
}

// TestStagingDirFallsBackWhenTargetDirUnwritable covers the fallback branch.
func TestStagingDirFallsBackWhenTargetDirUnwritable(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("running as root — directory permissions are not enforced")
	}

	dir := t.TempDir()
	if err := os.Chmod(dir, 0o500); err != nil { //nolint:gosec
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chmod(dir, 0o700) }) //nolint:gosec

	if got := stagingDirFor(filepath.Join(dir, "mytool")); got != os.TempDir() {
		t.Errorf("stagingDirFor() = %q, want the system temp dir for an unwritable install directory", got)
	}
}

func globHasStagedFile(t *testing.T, dir string) bool {
	t.Helper()
	matches, err := filepath.Glob(filepath.Join(dir, "updateapply-*"))
	if err != nil {
		t.Fatal(err)
	}
	return len(matches) > 0
}

func TestApplyValidatesInstalledBinary(t *testing.T) {
	assetBody := []byte("validated-binary")
	checksums := fmt.Sprintf("%s  mytool_linux_amd64\n", sha256Hex(assetBody))

	server, assetURL, checksumsURL := newTestServer(t, assetBody, checksums)
	defer server.Close()

	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: assetURL},
			{Name: "checksums.txt", BrowserDownloadURL: checksumsURL},
		},
	}

	target := filepath.Join(t.TempDir(), "mytool")
	if err := os.WriteFile(target, []byte("old-binary"), 0o755); err != nil { //nolint:gosec
		t.Fatalf("seed target: %v", err)
	}

	var validatedPath string
	a := &Applier{
		HTTPClient: http.DefaultClient,
		GOOS:       "linux",
		GOARCH:     "amd64",
		ValidateBinary: func(path string) error {
			validatedPath = path
			got, err := os.ReadFile(path) //nolint:gosec
			if err != nil {
				return err
			}
			if string(got) != string(assetBody) {
				return fmt.Errorf("installed content = %q, want %q", got, assetBody)
			}
			return nil
		},
	}

	if err := a.Apply(context.Background(), release, target); err != nil {
		t.Fatalf("Apply() error = %v", err)
	}
	if validatedPath != target {
		t.Fatalf("validator path = %q, want %q", validatedPath, target)
	}
	if _, err := os.Stat(target + ".bak"); !os.IsNotExist(err) {
		t.Fatalf("expected backup file to be cleaned up, stat err = %v", err)
	}
}

func TestApplyRollsBackWhenBinaryValidationFails(t *testing.T) {
	assetBody := []byte("invalid-binary")
	checksums := fmt.Sprintf("%s  mytool_linux_amd64\n", sha256Hex(assetBody))

	server, assetURL, checksumsURL := newTestServer(t, assetBody, checksums)
	defer server.Close()

	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: assetURL},
			{Name: "checksums.txt", BrowserDownloadURL: checksumsURL},
		},
	}

	target := filepath.Join(t.TempDir(), "mytool")
	original := []byte("old-binary")
	if err := os.WriteFile(target, original, 0o640); err != nil { //nolint:gosec
		t.Fatalf("seed target: %v", err)
	}
	if err := os.Chmod(target, 0o640); err != nil { //nolint:gosec
		t.Fatalf("set target permissions: %v", err)
	}

	validationErr := errors.New("installed binary does not start")
	a := &Applier{
		HTTPClient: http.DefaultClient,
		GOOS:       "linux",
		GOARCH:     "amd64",
		ValidateBinary: func(path string) error {
			return validationErr
		},
	}

	err := a.Apply(context.Background(), release, target)
	if !errors.Is(err, validationErr) {
		t.Fatalf("Apply() error = %v, want validation error %v", err, validationErr)
	}

	got, readErr := os.ReadFile(target) //nolint:gosec
	if readErr != nil {
		t.Fatalf("read target after rollback: %v", readErr)
	}
	if string(got) != string(original) {
		t.Fatalf("target after rollback = %q, want original %q", got, original)
	}
	info, statErr := os.Stat(target)
	if statErr != nil {
		t.Fatalf("stat target after rollback: %v", statErr)
	}
	if gotPerm := info.Mode().Perm(); gotPerm != 0o640 {
		t.Fatalf("target permissions after rollback = %o, want %o", gotPerm, 0o640)
	}
	if _, statErr := os.Stat(target + ".bak"); !os.IsNotExist(statErr) {
		t.Fatalf("expected backup file to be consumed by rollback, stat err = %v", statErr)
	}
}

func TestApplyRemovesFailedInstallWhenNoPreviousBinaryExists(t *testing.T) {
	assetBody := []byte("invalid-binary")
	checksums := fmt.Sprintf("%s  mytool_linux_amd64\n", sha256Hex(assetBody))

	server, assetURL, checksumsURL := newTestServer(t, assetBody, checksums)
	defer server.Close()

	release := &updatecheck.Release{
		Assets: []updatecheck.Asset{
			{Name: "mytool_linux_amd64", BrowserDownloadURL: assetURL},
			{Name: "checksums.txt", BrowserDownloadURL: checksumsURL},
		},
	}

	target := filepath.Join(t.TempDir(), "mytool")
	validationErr := errors.New("installed binary does not start")
	a := &Applier{
		HTTPClient: http.DefaultClient,
		GOOS:       "linux",
		GOARCH:     "amd64",
		ValidateBinary: func(path string) error {
			return validationErr
		},
	}

	err := a.Apply(context.Background(), release, target)
	if !errors.Is(err, validationErr) {
		t.Fatalf("Apply() error = %v, want validation error %v", err, validationErr)
	}
	if _, statErr := os.Stat(target); !os.IsNotExist(statErr) {
		t.Fatalf("failed install still exists, stat err = %v", statErr)
	}
	if _, statErr := os.Stat(target + ".bak"); !os.IsNotExist(statErr) {
		t.Fatalf("unexpected backup after failed first install, stat err = %v", statErr)
	}
}
