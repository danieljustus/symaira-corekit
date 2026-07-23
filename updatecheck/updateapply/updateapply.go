// Package updateapply implements the apply half of self-update: given an
// updatecheck.Release, it downloads the matching asset, verifies its
// checksum against the release's goreleaser checksums.txt, and atomically
// replaces the running binary with backup + rollback.
//
// Optional hardening:
//   - Cosign keyless signature verification (set CosignConfig)
//   - Archive extraction from tar.gz/zip releases (set ExtractBinary)
//   - Install method detection rejecting Homebrew installs (set CheckInstallMethod)
package updateapply

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"

	"github.com/danieljustus/symaira-corekit/updatecheck"
	"github.com/danieljustus/symaira-corekit/updatecheck/cosign"
	"github.com/danieljustus/symaira-corekit/updatecheck/extract"
	"github.com/danieljustus/symaira-corekit/updatecheck/installmethod"
)

// maxAssetBody caps how many bytes are read for a single downloaded asset or
// the checksums.txt manifest, guarding against a compromised or redirected
// endpoint streaming an unbounded body.
const maxAssetBody = 1 << 30 // 1 GiB

// ProgressFunc reports download progress. written and total are byte counts;
// total is 0 when the server did not report Content-Length.
type ProgressFunc func(written, total int64)

type httpDoer interface {
	Do(req *http.Request) (*http.Response, error)
}

// Applier downloads and installs an update in place of the running binary.
type Applier struct {
	HTTPClient httpDoer

	// GOOS and GOARCH select the asset to install. Defaults to the running
	// binary's runtime.GOOS / runtime.GOARCH when empty.
	GOOS   string
	GOARCH string

	// Progress, when set, is called during asset download.
	Progress ProgressFunc

	// CheckInstallMethod, when true, detects the installation method of the
	// target binary and rejects self-update for Homebrew-managed binaries
	// with a clear error message directing the user to brew upgrade instead.
	CheckInstallMethod bool

	// BinaryName is the display name used in install method detection
	// guidance messages and archive extraction. Defaults to
	// filepath.Base(targetPath) when empty.
	BinaryName string

	// CosignConfig, when non-nil, enables Cosign keyless signature
	// verification of the release checksums. The checksums are verified
	// against their attached cosign signature+certificate before any
	// downloaded asset is trusted.
	CosignConfig *cosign.Config

	// ExtractBinary, when non-empty, treats the downloaded release asset
	// as an archive (tar.gz or zip). After successful checksum verification,
	// the archive is extracted and the binary matching ExtractBinary is
	// used for installation.
	ExtractBinary string
}

// NewApplier creates an Applier using the running binary's OS/arch.
func NewApplier() *Applier {
	return &Applier{
		HTTPClient: http.DefaultClient,
		GOOS:       runtime.GOOS,
		GOARCH:     runtime.GOARCH,
	}
}

// Apply downloads the asset in release matching the target OS/arch, verifies
// its checksum against the release's checksums.txt asset, and atomically
// replaces targetPath with the downloaded binary. On any failure prior to a
// successful swap, targetPath is left untouched. If the swap itself fails
// partway, the previous binary is restored from backup.
//
// Optional hardening steps (configured via Applier fields) run in this order:
//
//  1. Install method detection (CheckInstallMethod): rejects Homebrew installs.
//  2. Cosign verification (CosignConfig): verifies checksums.txt signature.
//  3. Archive extraction (ExtractBinary): unpacks the downloaded archive.
func (a *Applier) Apply(ctx context.Context, release *updatecheck.Release, targetPath string) error {
	if release == nil {
		return errors.New("updateapply: release is nil")
	}
	if strings.TrimSpace(targetPath) == "" {
		return errors.New("updateapply: targetPath is empty")
	}

	binaryName := a.BinaryName
	if binaryName == "" {
		binaryName = filepath.Base(targetPath)
	}

	// Step 1: Optional install method detection.
	if a.CheckInstallMethod {
		method, err := installmethod.Detect(targetPath)
		if err != nil {
			return fmt.Errorf("updateapply: detect install method: %w", err)
		}
		if !installmethod.IsSelfUpdateSupported(method) {
			return fmt.Errorf(
				"updateapply: self-update is not supported for %s installation — %s",
				method, installmethod.Guidance(method, binaryName),
			)
		}
	}

	goos := a.GOOS
	if goos == "" {
		goos = runtime.GOOS
	}
	goarch := a.GOARCH
	if goarch == "" {
		goarch = runtime.GOARCH
	}

	asset, err := selectAsset(release.Assets, goos, goarch)
	if err != nil {
		return err
	}

	checksums, err := a.fetchChecksums(ctx, release.Assets)
	if err != nil {
		return fmt.Errorf("updateapply: fetch checksums: %w", err)
	}

	// Step 2: Optional cosign verification of checksums.
	if cfg := a.CosignConfig; cfg != nil {
		sig, sigErr := cfg.FetchSignature(ctx, release.TagName)
		if sigErr != nil {
			return fmt.Errorf("updateapply: fetch cosign signature: %w", sigErr)
		}
		cert, certErr := cfg.FetchCertificate(ctx, release.TagName)
		if certErr != nil {
			return fmt.Errorf("updateapply: fetch cosign certificate: %w", certErr)
		}
		// Build the checksums content from the parsed map for verification.
		var checksumsData strings.Builder
		for name, sum := range checksums {
			checksumsData.WriteString(fmt.Sprintf("%s  %s\n", sum, name))
		}
		if vErr := cfg.VerifySignature([]byte(checksumsData.String()), sig, cert); vErr != nil {
			return fmt.Errorf("updateapply: cosign verification failed: %w", vErr)
		}
	}

	wantSum, ok := checksums[asset.Name]
	if !ok {
		return fmt.Errorf("updateapply: no checksum entry for asset %q", asset.Name)
	}

	tmpFile, gotSum, err := a.downloadToTemp(ctx, asset)
	if err != nil {
		return fmt.Errorf("updateapply: download asset: %w", err)
	}
	defer func() { _ = os.Remove(tmpFile) }()

	if !strings.EqualFold(gotSum, wantSum) {
		return fmt.Errorf("updateapply: checksum mismatch for %q: got %s, want %s", asset.Name, gotSum, wantSum)
	}

	// Step 3: Optional archive extraction.
	installTarget := tmpFile
	if a.ExtractBinary != "" {
		extractedDir, err := os.MkdirTemp("", "updateapply-extract-*")
		if err != nil {
			return fmt.Errorf("updateapply: create extract temp dir: %w", err)
		}
		defer func() { _ = os.RemoveAll(extractedDir) }()

		archiveData, err := os.ReadFile(tmpFile)
		if err != nil {
			return fmt.Errorf("updateapply: read downloaded archive: %w", err)
		}

		extracted, extErr := extractFromArchive(archiveData, extractedDir, a.ExtractBinary)
		if extErr != nil {
			return fmt.Errorf("updateapply: extract binary %q from archive: %w", a.ExtractBinary, extErr)
		}
		installTarget = extracted
	}

	absTarget, err := filepath.Abs(targetPath)
	if err != nil {
		return fmt.Errorf("updateapply: resolve target path: %w", err)
	}
	if err := checkWritable(absTarget); err != nil {
		return fmt.Errorf("updateapply: %w", err)
	}

	if err := os.Chmod(installTarget, 0o755); err != nil { //nolint:gosec // installed binary must be executable
		return fmt.Errorf("updateapply: make downloaded asset executable: %w", err)
	}

	return atomicSwap(installTarget, absTarget)
}

// InstallMethod detects the installation method of the given binary path.
// It is a convenience wrapper around installmethod.Detect.
func InstallMethod(binaryPath string) (installmethod.InstallMethod, error) {
	return installmethod.Detect(binaryPath)
}

// extractFromArchive dispatches to ExtractTarGz or ExtractZip based on the
// archive filename.
func extractFromArchive(archiveData []byte, destDir, binaryName string) (string, error) {
	// Try tar.gz first (most common for macOS/Linux).
	path, err := extract.ExtractTarGz(archiveData, destDir, binaryName)
	if err == nil {
		return path, nil
	}
	if !errors.Is(err, extract.ErrBinaryNotFound) && !strings.Contains(err.Error(), "gzip") {
		return "", err
	}

	// Fall back to zip (Windows/packaged releases).
	path, zipErr := extract.ExtractZip(archiveData, destDir, binaryName)
	if zipErr != nil {
		// Return the original tar.gz error if zip also fails — it was the first attempt.
		if errors.Is(err, extract.ErrBinaryNotFound) {
			return "", err
		}
		return "", zipErr
	}
	return path, nil
}

// Reexec replaces the current process image with targetPath via
// syscall.Exec, passing through the current arguments and environment. On
// success it does not return.
func Reexec(targetPath string) error {
	absTarget, err := filepath.Abs(targetPath)
	if err != nil {
		return fmt.Errorf("updateapply: resolve re-exec path: %w", err)
	}
	args := os.Args
	if len(args) == 0 {
		args = []string{absTarget}
	} else {
		args = append([]string{absTarget}, args[1:]...)
	}
	return syscall.Exec(absTarget, args, os.Environ()) //nolint:gosec // absTarget is the just-installed binary
}

func selectAsset(assets []updatecheck.Asset, goos, goarch string) (updatecheck.Asset, error) {
	for _, asset := range assets {
		name := strings.ToLower(asset.Name)
		if strings.Contains(name, "checksums") {
			continue
		}
		if strings.Contains(name, strings.ToLower(goos)) && strings.Contains(name, strings.ToLower(goarch)) {
			return asset, nil
		}
	}
	return updatecheck.Asset{}, fmt.Errorf("updateapply: no release asset matches %s/%s", goos, goarch)
}

// fetchChecksums downloads the release's checksums.txt asset and parses its
// "<sha256>  <filename>" lines (the format goreleaser emits).
func (a *Applier) fetchChecksums(ctx context.Context, assets []updatecheck.Asset) (map[string]string, error) {
	var checksumAsset *updatecheck.Asset
	for i := range assets {
		if strings.Contains(strings.ToLower(assets[i].Name), "checksums") {
			checksumAsset = &assets[i]
			break
		}
	}
	if checksumAsset == nil {
		return nil, errors.New("release has no checksums.txt asset")
	}

	body, _, err := a.download(ctx, *checksumAsset)
	if err != nil {
		return nil, err
	}
	defer func() { _ = body.Close() }()

	data, err := io.ReadAll(io.LimitReader(body, maxAssetBody))
	if err != nil {
		return nil, fmt.Errorf("read checksums.txt: %w", err)
	}

	sums := make(map[string]string)
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) != 2 {
			continue
		}
		sums[fields[1]] = fields[0]
	}
	if len(sums) == 0 {
		return nil, errors.New("checksums.txt contained no parseable entries")
	}
	return sums, nil
}

func (a *Applier) download(ctx context.Context, asset updatecheck.Asset) (io.ReadCloser, int64, error) {
	client := a.HTTPClient
	if client == nil {
		client = http.DefaultClient
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, asset.BrowserDownloadURL, nil)
	if err != nil {
		return nil, 0, fmt.Errorf("create request: %w", err)
	}

	resp, err := client.Do(req) // #nosec G107 — URL comes from a verified GitHub release asset
	if err != nil {
		return nil, 0, fmt.Errorf("request asset: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		_ = resp.Body.Close()
		return nil, 0, fmt.Errorf("download %q: HTTP %d", asset.Name, resp.StatusCode)
	}
	return resp.Body, resp.ContentLength, nil
}

// downloadToTemp downloads asset into a temp file next to os.TempDir and
// returns its path plus the hex sha256 of its content.
func (a *Applier) downloadToTemp(ctx context.Context, asset updatecheck.Asset) (string, string, error) {
	body, total, err := a.download(ctx, asset)
	if err != nil {
		return "", "", err
	}
	defer func() { _ = body.Close() }()

	tmp, err := os.CreateTemp("", "updateapply-*")
	if err != nil {
		return "", "", fmt.Errorf("create temp file: %w", err)
	}
	tmpPath := tmp.Name()
	defer func() { _ = tmp.Close() }()

	hasher := sha256.New()
	limited := io.LimitReader(body, maxAssetBody)

	var written int64
	buf := make([]byte, 32*1024)
	for {
		n, readErr := limited.Read(buf)
		if n > 0 {
			if _, werr := tmp.Write(buf[:n]); werr != nil {
				_ = os.Remove(tmpPath)
				return "", "", fmt.Errorf("write temp file: %w", werr)
			}
			hasher.Write(buf[:n])
			written += int64(n)
			if a.Progress != nil {
				a.Progress(written, total)
			}
		}
		if readErr == io.EOF {
			break
		}
		if readErr != nil {
			_ = os.Remove(tmpPath)
			return "", "", fmt.Errorf("read asset body: %w", readErr)
		}
	}

	if total > 0 && written != total {
		_ = os.Remove(tmpPath)
		return "", "", fmt.Errorf("incomplete download: got %d bytes, want %d", written, total)
	}

	return tmpPath, hex.EncodeToString(hasher.Sum(nil)), nil
}

// checkWritable verifies the target's parent directory is writable and, if
// the target already exists, that it can be renamed (i.e. is not read-only
// in a way that would block the swap).
func checkWritable(targetPath string) error {
	dir := filepath.Dir(targetPath)
	probe := filepath.Join(dir, ".updateapply-writecheck")
	f, err := os.OpenFile(probe, os.O_CREATE|os.O_WRONLY, 0o600) //nolint:gosec // probe file, immediately removed
	if err != nil {
		return fmt.Errorf("install location %q is not writable: %w", dir, err)
	}
	_ = f.Close()
	_ = os.Remove(probe)

	if info, err := os.Stat(targetPath); err == nil && info.Mode().Perm()&0o200 == 0 {
		return fmt.Errorf("target binary %q is not writable", targetPath)
	}
	return nil
}

// atomicSwap replaces targetPath with newPath, keeping a backup and rolling
// back if the swap fails partway.
func atomicSwap(newPath, targetPath string) error {
	backupPath := targetPath + ".bak"

	_, statErr := os.Stat(targetPath)
	hadExisting := statErr == nil

	if hadExisting {
		_ = os.Remove(backupPath)
		if err := os.Rename(targetPath, backupPath); err != nil {
			return fmt.Errorf("backup current binary: %w", err)
		}
	}

	if err := os.Rename(newPath, targetPath); err != nil {
		if hadExisting {
			if rbErr := os.Rename(backupPath, targetPath); rbErr != nil {
				return fmt.Errorf("install new binary failed (%v) and rollback failed (%w)", err, rbErr)
			}
		}
		return fmt.Errorf("install new binary: %w", err)
	}

	if hadExisting {
		_ = os.Remove(backupPath)
	}
	return nil
}
