package updateapply

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/danieljustus/symaira-corekit/updatecheck"
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

func TestNewApplierDefaults(t *testing.T) {
	a := NewApplier()
	if a == nil {
		t.Fatal("NewApplier() returned nil")
	}
	if a.HTTPClient != http.DefaultClient {
		t.Errorf("HTTPClient = %T, want http.DefaultClient", a.HTTPClient)
	}
	if a.GOOS != runtime.GOOS {
		t.Errorf("GOOS = %q, want %q", a.GOOS, runtime.GOOS)
	}
	if a.GOARCH != runtime.GOARCH {
		t.Errorf("GOARCH = %q, want %q", a.GOARCH, runtime.GOARCH)
	}
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
	err := atomicSwap(missingNew, target)
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

func TestDownloadToTempFailsWhenTempDirUnwritable(t *testing.T) {
	assetBody := []byte("fake-binary-content")
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

	// os.CreateTemp("", ...) resolves its directory via os.TempDir(), which
	// reads $TMPDIR on unix. Pointing it at a nonexistent directory makes
	// downloadToTemp's os.CreateTemp call fail.
	t.Setenv("TMPDIR", filepath.Join(dir, "does-not-exist"))

	a := &Applier{HTTPClient: http.DefaultClient, GOOS: "linux", GOARCH: "amd64"}
	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected error when the temp directory is unwritable, got nil")
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
