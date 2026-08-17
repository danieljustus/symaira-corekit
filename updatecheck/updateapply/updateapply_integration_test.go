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

// TestExtractFromArchiveProbesTarGzFirst covers the fallback path used when
// the asset name does not reveal the archive format.
func TestExtractFromArchiveProbesTarGzFirst(t *testing.T) {
	dir := t.TempDir()
	binaryName := "mytool"

	archiveData := testBuildTarGz(map[string]string{
		"mytool_1.0.0_darwin_arm64/":       "",
		"mytool_1.0.0_darwin_arm64/mytool": "extracted-binary",
	}, true)

	path, err := extractFromArchive(archiveData, "release-bundle", dir, binaryName)
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

// TestExtractFromArchiveProbesZipSecond covers the zip half of the same
// fallback path.
func TestExtractFromArchiveProbesZipSecond(t *testing.T) {
	dir := t.TempDir()
	binaryName := "mytool.exe"

	archiveData := testBuildZip(map[string]string{
		"mytool_1.0.0_windows_amd64/":           "",
		"mytool_1.0.0_windows_amd64/mytool.exe": "win-binary",
	})

	path, err := extractFromArchive(archiveData, "release-bundle", dir, binaryName)
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
	_, err := extractFromArchive([]byte("garbage-data"), "release-bundle", t.TempDir(), "mytool")
	if err == nil {
		t.Fatal("expected error for garbage archive data")
	}
}

// TestExtractFromArchiveDispatchesByAssetName pins the format decision to the
// asset's extension. The previous implementation always attempted tar.gz and
// only reached the zip branch when the resulting error text happened to
// contain "gzip" — an implementation detail of compress/gzip, not a contract.
func TestExtractFromArchiveDispatchesByAssetName(t *testing.T) {
	tarGz := testBuildTarGz(map[string]string{
		"mytool_1.0.0_linux_amd64/":       "",
		"mytool_1.0.0_linux_amd64/mytool": "tar-binary",
	}, true)
	zipData := testBuildZip(map[string]string{
		"mytool_1.0.0_windows_amd64/":           "",
		"mytool_1.0.0_windows_amd64/mytool.exe": "zip-binary",
	})

	tests := []struct {
		name       string
		assetName  string
		data       []byte
		binaryName string
		want       string
	}{
		{"tar.gz suffix", "mytool_1.0.0_linux_amd64.tar.gz", tarGz, "mytool", "tar-binary"},
		{"tgz suffix", "mytool_1.0.0_linux_amd64.tgz", tarGz, "mytool", "tar-binary"},
		{"zip suffix", "mytool_1.0.0_windows_amd64.zip", zipData, "mytool.exe", "zip-binary"},
		{"uppercase suffix", "MYTOOL_1.0.0_WINDOWS_AMD64.ZIP", zipData, "mytool.exe", "zip-binary"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			path, err := extractFromArchive(tt.data, tt.assetName, t.TempDir(), tt.binaryName)
			if err != nil {
				t.Fatalf("extractFromArchive(%q) error = %v", tt.assetName, err)
			}
			data, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			if string(data) != tt.want {
				t.Errorf("content = %q, want %q", data, tt.want)
			}
		})
	}
}

// TestExtractZipAssetNeverConsultsGzipError is the regression guard: a .zip
// asset must extract without the tar.gz attempt running at all, so no change
// to compress/gzip's error wording can break Windows releases.
func TestExtractZipAssetNeverConsultsGzipError(t *testing.T) {
	zipData := testBuildZip(map[string]string{
		"mytool_1.0.0_windows_amd64/":           "",
		"mytool_1.0.0_windows_amd64/mytool.exe": "win-binary",
	})

	path, err := extractFromArchive(zipData, "mytool_1.0.0_windows_amd64.zip", t.TempDir(), "mytool.exe")
	if err != nil {
		t.Fatalf("extractFromArchive() error = %v", err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != "win-binary" {
		t.Errorf("content = %q, want %q", data, "win-binary")
	}
}

// TestExtractFromArchiveNamedFormatMismatch documents that a named format is
// trusted: a .zip name carrying tar.gz bytes fails as a zip error rather than
// silently falling through to the other parser.
func TestExtractFromArchiveNamedFormatMismatch(t *testing.T) {
	tarGz := testBuildTarGz(map[string]string{
		"mytool_1.0.0_linux_amd64/":       "",
		"mytool_1.0.0_linux_amd64/mytool": "tar-binary",
	}, true)

	if _, err := extractFromArchive(tarGz, "mytool_1.0.0_linux_amd64.zip", t.TempDir(), "mytool"); err == nil {
		t.Fatal("expected tar.gz bytes named .zip to fail as a zip archive")
	}
}
