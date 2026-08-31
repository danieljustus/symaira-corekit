// Package updateapply implements the apply half of self-update: given an
// updatecheck.Release, it downloads the matching asset, verifies its
// checksum against the release's goreleaser checksums.txt, and atomically
// replaces the running binary with backup + rollback.
//
// Optional hardening:
//   - Cosign keyless signature verification (set CosignConfig)
//   - Archive extraction from tar.gz/zip releases (set ExtractBinary)
//   - Install method detection rejecting Homebrew installs (set CheckInstallMethod)
//   - Post-swap executable validation with rollback (set ValidateBinary)
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

// BinaryValidator validates an installed executable at path. Returning an
// error rejects the update and causes the previous binary to be restored.
type BinaryValidator func(path string) error

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

	// ValidateBinary, when set, is called after the new binary has replaced
	// targetPath and before the rollback backup is removed. Returning an error
	// restores the previous binary and returns that error from Apply. When no
	// previous binary exists, the failed installation is removed instead.
	ValidateBinary BinaryValidator
}

// NewApplier creates an Applier using the running binary's OS/arch and the
// hardened download client (TLS 1.3 minimum, bounded timeout, redirects
// refused off GitHub hosts). Callers that need different transport behaviour
// can replace HTTPClient after construction.
func NewApplier() *Applier {
	return &Applier{
		HTTPClient: updatecheck.NewSecureClientWithTimeout(updatecheck.DefaultDownloadTimeout),
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
//  4. Executable validation (ValidateBinary): validates the installed binary
//     and rolls back when the hook returns an error.
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

	checksums, checksumsBytes, err := a.fetchChecksums(ctx, release.Assets)
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
		// Verify the signature over the exact downloaded checksums bytes.
		// Rebuilding the file from the parsed map would reorder entries and
		// normalize whitespace, so the bytes handed to cosign would almost
		// never match what goreleaser actually signed.
		if vErr := cfg.VerifySignature(checksumsBytes, sig, cert); vErr != nil {
			return fmt.Errorf("updateapply: cosign verification failed: %w", vErr)
		}
	}

	wantSum, ok := checksums[asset.Name]
	if !ok {
		return fmt.Errorf("updateapply: no checksum entry for asset %q", asset.Name)
	}

	absTarget, err := filepath.Abs(targetPath)
	if err != nil {
		return fmt.Errorf("updateapply: resolve target path: %w", err)
	}
	// Verify writability before downloading rather than after: there is no
	// point pulling a multi-megabyte asset only to discover the install
	// location is read-only.
	if err := checkWritable(absTarget); err != nil {
		return fmt.Errorf("updateapply: %w", err)
	}

	// Stage in the install directory so the final swap is a same-filesystem
	// rename. rename(2) fails with EXDEV across filesystems, which is the
	// normal case when TMPDIR is a tmpfs and the binary lives in /usr/local/bin.
	stagingDir := stagingDirFor(absTarget)

	tmpFile, gotSum, err := a.downloadToTemp(ctx, stagingDir, asset)
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
		extractedDir, err := os.MkdirTemp(stagingDir, "updateapply-extract-*")
		if err != nil {
			return fmt.Errorf("updateapply: create extract temp dir: %w", err)
		}
		defer func() { _ = os.RemoveAll(extractedDir) }()

		archiveData, err := os.ReadFile(tmpFile) //nolint:gosec
		if err != nil {
			return fmt.Errorf("updateapply: read downloaded archive: %w", err)
		}

		extracted, extErr := extractFromArchive(archiveData, asset.Name, extractedDir, a.ExtractBinary)
		if extErr != nil {
			return fmt.Errorf("updateapply: extract binary %q from archive: %w", a.ExtractBinary, extErr)
		}

		// Defense in depth: the extract package validates archive entry names,
		// but the returned path is used in file operations below (os.Chmod,
		// os.Rename). Reject any path with a parent-directory reference before
		// it reaches those sinks, so a traversal can never escape the
		// extraction directory.
		if strings.Contains(extracted, "..") {
			return fmt.Errorf("updateapply: extracted binary path %q escapes extraction directory %q", extracted, extractedDir)
		}
		installTarget = extracted
	}

	if err := os.Chmod(installTarget, 0o755); err != nil { //nolint:gosec // installed binary must be executable
		return fmt.Errorf("updateapply: make downloaded asset executable: %w", err)
	}

	return atomicSwap(installTarget, absTarget, a.ValidateBinary)
}

// InstallMethod detects the installation method of the given binary path.
// It is a convenience wrapper around installmethod.Detect.
func InstallMethod(binaryPath string) (installmethod.InstallMethod, error) {
	return installmethod.Detect(binaryPath)
}

// extractFromArchive dispatches to ExtractTarGz or ExtractZip based on
// assetName's extension. goreleaser names its archives *.tar.gz / *.tgz /
// *.zip, so the format is known before a single byte is parsed.
//
// An unrecognised extension falls back to trying both formats, so consumers
// with a custom naming scheme keep working.
func extractFromArchive(archiveData []byte, assetName, destDir, binaryName string) (string, error) {
	switch {
	case hasAnySuffix(assetName, ".zip"):
		return extract.ExtractZip(archiveData, destDir, binaryName)
	case hasAnySuffix(assetName, ".tar.gz", ".tgz"):
		return extract.ExtractTarGz(archiveData, destDir, binaryName)
	default:
		return extractByProbing(archiveData, destDir, binaryName)
	}
}

// extractByProbing handles archives whose name does not reveal the format. It
// tries tar.gz first (the common case for macOS/Linux releases) and falls back
// to zip. ErrBinaryNotFound from the first attempt is preserved: it means the
// archive parsed fine and simply did not contain the expected binary, which is
// a more useful error than a zip parse failure.
func extractByProbing(archiveData []byte, destDir, binaryName string) (string, error) {
	path, tarErr := extract.ExtractTarGz(archiveData, destDir, binaryName)
	if tarErr == nil {
		return path, nil
	}
	if errors.Is(tarErr, extract.ErrPathTraversal) {
		return "", tarErr
	}

	path, zipErr := extract.ExtractZip(archiveData, destDir, binaryName)
	if zipErr != nil {
		if errors.Is(tarErr, extract.ErrBinaryNotFound) {
			return "", tarErr
		}
		return "", zipErr
	}
	return path, nil
}

func hasAnySuffix(name string, suffixes ...string) bool {
	lower := strings.ToLower(name)
	for _, suffix := range suffixes {
		if strings.HasSuffix(lower, suffix) {
			return true
		}
	}
	return false
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
// "<sha256>  <filename>" lines (the format goreleaser emits). It returns the
// parsed map plus the exact raw bytes downloaded, so callers can verify a
// cosign signature over the file exactly as published — re-encoding from the
// map would reorder entries and normalize whitespace.
func (a *Applier) fetchChecksums(ctx context.Context, assets []updatecheck.Asset) (map[string]string, []byte, error) {
	var checksumAsset *updatecheck.Asset
	for i := range assets {
		if strings.Contains(strings.ToLower(assets[i].Name), "checksums") {
			checksumAsset = &assets[i]
			break
		}
	}
	if checksumAsset == nil {
		return nil, nil, errors.New("release has no checksums.txt asset")
	}

	body, _, err := a.download(ctx, *checksumAsset)
	if err != nil {
		return nil, nil, err
	}
	defer func() { _ = body.Close() }()

	data, err := io.ReadAll(io.LimitReader(body, maxAssetBody))
	if err != nil {
		return nil, nil, fmt.Errorf("read checksums.txt: %w", err)
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
		return nil, nil, errors.New("checksums.txt contained no parseable entries")
	}
	return sums, data, nil
}

func (a *Applier) download(ctx context.Context, asset updatecheck.Asset) (io.ReadCloser, int64, error) {
	client := a.HTTPClient
	if client == nil {
		client = updatecheck.NewSecureClientWithTimeout(updatecheck.DefaultDownloadTimeout)
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

// stagingDirFor returns the directory the update is staged in. It prefers the
// target binary's own directory so the final os.Rename is a same-filesystem
// operation; a rename across filesystems fails with EXDEV. It falls back to
// the system temp directory only when the install directory cannot be written
// to, which Apply rejects earlier anyway.
func stagingDirFor(absTarget string) string {
	dir := filepath.Dir(absTarget)
	probe, err := os.CreateTemp(dir, ".updateapply-staging-*")
	if err != nil {
		return os.TempDir()
	}
	name := probe.Name()
	_ = probe.Close()
	_ = os.Remove(name)
	return dir
}

// downloadToTemp downloads asset into a temp file inside dir and returns its
// path plus the hex sha256 of its content. dir is the staging directory —
// normally the install directory, so the later rename stays on one filesystem.
func (a *Applier) downloadToTemp(ctx context.Context, dir string, asset updatecheck.Asset) (string, string, error) {
	body, total, err := a.download(ctx, asset)
	if err != nil {
		return "", "", err
	}
	defer func() { _ = body.Close() }()

	tmp, err := os.CreateTemp(dir, "updateapply-*")
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
// back if the swap fails partway or validation rejects the new binary.
func atomicSwap(newPath, targetPath string, validate BinaryValidator) error {
	backupPath := targetPath + ".bak"

	_, statErr := os.Stat(targetPath)
	hadExisting := statErr == nil

	if hadExisting {
		_ = os.Remove(backupPath)
		if err := os.Rename(targetPath, backupPath); err != nil {
			return fmt.Errorf("backup current binary: %w", err)
		}
	}

	if err := os.Rename(newPath, targetPath); err != nil { //nolint:gosec // paths are constructed, not user-supplied
		if hadExisting {
			if rbErr := os.Rename(backupPath, targetPath); rbErr != nil {
				return fmt.Errorf("install new binary failed (%v) and rollback failed (%w)", err, rbErr)
			}
		}
		return fmt.Errorf("install new binary: %w", err)
	}

	if validate != nil {
		if err := validate(targetPath); err != nil {
			if hadExisting {
				if rbErr := restoreBackup(backupPath, targetPath); rbErr != nil {
					return fmt.Errorf("validate installed binary failed (%v) and rollback failed: %w", err, rbErr)
				}
			} else if rmErr := os.Remove(targetPath); rmErr != nil && !os.IsNotExist(rmErr) {
				return fmt.Errorf("validate installed binary failed (%v) and remove failed: %w", err, rmErr)
			}
			return fmt.Errorf("validate installed binary: %w", err)
		}
	}

	if hadExisting {
		_ = os.Remove(backupPath)
	}
	return nil
}

func restoreBackup(backupPath, targetPath string) error {
	if err := os.Remove(targetPath); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("remove failed installed binary: %w", err)
	}
	if err := os.Rename(backupPath, targetPath); err != nil {
		return fmt.Errorf("restore previous binary: %w", err)
	}
	return nil
}
