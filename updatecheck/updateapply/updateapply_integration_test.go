package updateapply

import (
	"archive/tar"
	"archive/zip"
	"bytes"
	"compress/gzip"
	"context"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/danieljustus/symaira-corekit/updatecheck"
)

// test helpers for archive construction
func testBuildTarGz(entries map[string]string, dirMode bool) []byte {
	var buf bytes.Buffer
	gw := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gw)
	for path, content := range entries {
		if dirMode && content == "" {
			_ = tw.WriteHeader(&tar.Header{Name: path, Typeflag: tar.TypeDir, Mode: 0o755})
		} else {
			_ = tw.WriteHeader(&tar.Header{Name: path, Typeflag: tar.TypeReg, Mode: 0o755, Size: int64(len(content))})
			_, _ = tw.Write([]byte(content))
		}
	}
	_ = tw.Close()
	_ = gw.Close()
	return buf.Bytes()
}

func testBuildZip(entries map[string]string) []byte {
	var buf bytes.Buffer
	zw := zip.NewWriter(&buf)
	for path, content := range entries {
		if content == "" && strings.HasSuffix(path, "/") {
			_, _ = zw.Create(path)
		} else {
			w, _ := zw.Create(path)
			_, _ = w.Write([]byte(content))
		}
	}
	_ = zw.Close()
	return buf.Bytes()
}

func TestApplyRejectsHomebrewInstall(t *testing.T) {
	tmp := t.TempDir()
	cellarDir := filepath.Join(tmp, "Cellar", "tool", "1.0.0", "bin")
	if err := os.MkdirAll(cellarDir, 0755); err != nil {
		t.Fatal(err)
	}
	target := filepath.Join(cellarDir, "tool")
	if err := os.WriteFile(target, []byte("old-binary"), 0755); err != nil { //nolint:gosec
		t.Fatalf("seed target: %v", err)
	}

	release := &updatecheck.Release{
		TagName: "v1.2.0",
		Assets:  []updatecheck.Asset{{Name: "tool_linux_amd64", BrowserDownloadURL: "https://example.com/asset"}},
	}

	a := &Applier{
		HTTPClient:         http.DefaultClient,
		GOOS:               "linux",
		GOARCH:             "amd64",
		CheckInstallMethod: true,
		BinaryName:         "tool",
	}

	err := a.Apply(context.Background(), release, target)
	if err == nil {
		t.Fatal("expected error for Homebrew installation, got nil")
	}
	if !strings.Contains(err.Error(), "homebrew") {
		t.Fatalf("expected error mentioning homebrew, got: %v", err)
	}
}

func TestApplySkipsInstallMethodCheckWhenDisabled(t *testing.T) {
	assetBody := []byte("fake-binary-content")
	sum := sha256Hex(assetBody)
	checksums := fmt.Sprintf("%s  tool_linux_amd64\n", sum)

	server, assetURL, checksumsURL := newTestServer(t, assetBody, checksums)
	defer server.Close()

	release := &updatecheck.Release{
		TagName: "v1.2.0",
		Assets: []updatecheck.Asset{
			{Name: "tool_linux_amd64", BrowserDownloadURL: assetURL},
			{Name: "checksums.txt", BrowserDownloadURL: checksumsURL},
		},
	}

	dir := t.TempDir()
	target := filepath.Join(dir, "tool")
	if err := os.WriteFile(target, []byte("old-binary"), 0o755); err != nil { //nolint:gosec
		t.Fatalf("seed target: %v", err)
	}

	a := &Applier{
		HTTPClient: http.DefaultClient,
		GOOS:       "linux",
		GOARCH:     "amd64",
	}

	if err := a.Apply(context.Background(), release, target); err != nil {
		t.Fatalf("Apply() error = %v", err)
	}
}

func TestExtractFromArchiveTriesTarGzFirst(t *testing.T) {
	dir := t.TempDir()
	binaryName := "mytool"

	archiveData := testBuildTarGz(map[string]string{
		"mytool_1.0.0_darwin_arm64/":       "",
		"mytool_1.0.0_darwin_arm64/mytool": "extracted-binary",
	}, true)

	path, err := extractFromArchive(archiveData, dir, binaryName)
	if err != nil {
		t.Fatalf("extractFromArchive() error = %v", err)
	}
	if filepath.Base(path) != binaryName {
		t.Fatalf("extracted file = %q, want %q", filepath.Base(path), binaryName)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("ReadFile() error = %v", err)
	}
	if string(data) != "extracted-binary" {
		t.Fatalf("content = %q, want %q", string(data), "extracted-binary")
	}
}

func TestExtractFromArchiveFallsBackToZip(t *testing.T) {
	dir := t.TempDir()
	binaryName := "mytool.exe"

	archiveData := testBuildZip(map[string]string{
		"mytool_1.0.0_windows_amd64/":           "",
		"mytool_1.0.0_windows_amd64/mytool.exe": "win-binary",
	})

	path, err := extractFromArchive(archiveData, dir, binaryName)
	if err != nil {
		t.Fatalf("extractFromArchive() error = %v", err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("ReadFile() error = %v", err)
	}
	if string(data) != "win-binary" {
		t.Fatalf("content = %q, want %q", string(data), "win-binary")
	}
}

func TestExtractFromArchiveReturnsErrorWhenNothingWorks(t *testing.T) {
	_, err := extractFromArchive([]byte("garbage-data"), t.TempDir(), "mytool")
	if err == nil {
		t.Fatal("expected error for garbage archive data")
	}
}
