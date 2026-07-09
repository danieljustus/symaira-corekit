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
