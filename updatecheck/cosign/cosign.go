// Package cosign provides Cosign keyless signature verification for
// self-update workflows. It handles fetching and verifying cosign
// signatures against release checksums using the cosign CLI.
package cosign

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// execCommand is overridden in tests to allow verification without the cosign
// CLI being installed.
var execCommand = exec.Command

// OIDCIssuer is the expected OIDC issuer for cosign keyless signatures.
// All GitHub Actions workflows use this issuer.
const OIDCIssuer = `https://token.actions.githubusercontent.com`

// Config defines the repository-specific parameters for cosign verification.
// Repo must be in "owner/repo" format (lowercase, hyphenated).
type Config struct {
	// Repo is the GitHub repository slug (e.g. "danieljustus/symaira-vault").
	Repo string

	// BinaryName is the artefact name used in signature filenames
	// (e.g. "symvault" → "symvault_1.0.0_checksums.txt.sig").
	BinaryName string

	// DownloadBaseURL is the GitHub release download URL.
	// Defaults to "https://github.com/{repo}/releases/download" when empty.
	DownloadBaseURL string

	// IdentityRegexp is the certificate identity regexp passed to
	// cosign verify-blob. Defaults to a pattern matching the release
	// workflow of Config.Repo when empty.
	IdentityRegexp string

	// HTTPClient is used for fetching cosign artefacts. Defaults to
	// http.DefaultClient when nil.
	HTTPClient *http.Client
}

// IdentityRegexp returns the certificate identity regexp. When empty in the
// config, it builds a default pattern from the repo slug.
func (c Config) IdentityRegexpOrDefault() string {
	if c.IdentityRegexp != "" {
		return c.IdentityRegexp
	}
	return fmt.Sprintf(
		`https://github\\.com/%s/\\.github/workflows/release\\.yml@refs/tags/v.*`,
		strings.ReplaceAll(c.Repo, "/", "/"),
	)
}

// DownloadBaseURLOrDefault returns the download base URL, defaulting to the
// standard GitHub releases download path.
func (c Config) DownloadBaseURLOrDefault() string {
	if c.DownloadBaseURL != "" {
		return c.DownloadBaseURL
	}
	return fmt.Sprintf("https://github.com/%s/releases/download", c.Repo)
}

func (c Config) client() *http.Client {
	if c.HTTPClient != nil {
		return c.HTTPClient
	}
	return http.DefaultClient
}

// signatureFileName returns the cosign signature filename for the checksums
// file of the given release version.
func (c Config) signatureFileName(version string) string {
	v := strings.TrimPrefix(version, "v")
	return fmt.Sprintf("%s_%s_checksums.txt.sig", c.BinaryName, v)
}

// certificateFileName returns the cosign certificate filename for the
// checksums file of the given release version.
func (c Config) certificateFileName(version string) string {
	v := strings.TrimPrefix(version, "v")
	return fmt.Sprintf("%s_%s_checksums.txt.pem", c.BinaryName, v)
}

// fetchArtifact downloads a cosign artefact (signature or certificate) for
// the given release version.
func (c Config) fetchArtifact(ctx context.Context, version string, artifactName func(string) string, artifactLabel string) ([]byte, error) {
	v := strings.TrimPrefix(version, "v")
	if v == "" {
		return nil, fmt.Errorf("version must not be empty")
	}

	name := artifactName(version)
	base := c.DownloadBaseURLOrDefault()
	u := fmt.Sprintf("%s/v%s/%s", base, v, name)

	parsed, err := url.Parse(u)
	if err != nil {
		return nil, fmt.Errorf("invalid cosign %s URL: %w", artifactLabel, err)
	}
	if parsed.Scheme != "https" {
		return nil, fmt.Errorf("cosign %s URL must use HTTPS, got %q", artifactLabel, parsed.Scheme)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, fmt.Errorf("create cosign %s request: %w", artifactLabel, err)
	}

	client := c.client()
	resp, err := client.Do(req) // #nosec G107 — URL is constructed from controlled inputs
	if err != nil {
		return nil, fmt.Errorf("fetch cosign %s: %w", artifactLabel, err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("fetch cosign %s: HTTP %d", artifactLabel, resp.StatusCode)
	}

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read cosign %s response: %w", artifactLabel, err)
	}

	return data, nil
}

// FetchSignature downloads the cosign signature file for the release checksums.
func (c Config) FetchSignature(ctx context.Context, version string) ([]byte, error) {
	return c.fetchArtifact(ctx, version, c.signatureFileName, "signature")
}

// FetchCertificate downloads the cosign certificate file for the release checksums.
func (c Config) FetchCertificate(ctx context.Context, version string) ([]byte, error) {
	return c.fetchArtifact(ctx, version, c.certificateFileName, "certificate")
}

// VerifySignature verifies a cosign keyless signature on the given content
// using the provided signature and certificate. It shells out to the cosign CLI.
//
// The verification enforces:
//   - The certificate's OIDC issuer must be GitHub Actions
//   - The certificate identity must match the configured release workflow
//
// If the cosign CLI is not installed, the function returns a clear error
// instructing the user to install it.
func (c Config) VerifySignature(content, signature, certificate []byte) error {
	if _, err := exec.LookPath("cosign"); err != nil {
		return fmt.Errorf(
			"cosign CLI not found — install cosign from https://docs.sigstore.dev "+
				"to verify release signatures: %w", err,
		)
	}

	tmpDir, err := os.MkdirTemp("", "cosign-verify-*")
	if err != nil {
		return fmt.Errorf("create temp directory: %w", err)
	}
	defer func() { _ = os.RemoveAll(tmpDir) }()

	contentPath := filepath.Join(tmpDir, "content")
	sigPath := filepath.Join(tmpDir, "signature.sig")
	certPath := filepath.Join(tmpDir, "certificate.pem")

	if err := os.WriteFile(contentPath, content, 0o600); err != nil {
		return fmt.Errorf("write content file: %w", err)
	}
	if err := os.WriteFile(sigPath, signature, 0o600); err != nil {
		return fmt.Errorf("write signature file: %w", err)
	}
	if err := os.WriteFile(certPath, certificate, 0o600); err != nil {
		return fmt.Errorf("write certificate file: %w", err)
	}

	var stderr bytes.Buffer
	cmd := execCommand("cosign",
		"verify-blob",
		"--certificate", certPath,
		"--signature", sigPath,
		"--certificate-identity-regexp",
		c.IdentityRegexpOrDefault(),
		"--certificate-oidc-issuer",
		OIDCIssuer,
		contentPath,
	)
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		return fmt.Errorf(
			"cosign verify-blob failed: %s: %w",
			strings.TrimSpace(stderr.String()),
			err,
		)
	}

	return nil
}
