// Package updatecheck provides GitHub release checking for CLI application updates.
package updatecheck

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"
)

const (
	// DefaultCacheTTL is the default time-to-live for cached update check results.
	DefaultCacheTTL = 24 * time.Hour

	// maxResponseBody caps how many bytes are read from the release API. A
	// release JSON payload is a few KB; the limit guards against a compromised,
	// MITM'd, or redirected endpoint streaming an unbounded body.
	maxResponseBody = 1 << 20 // 1 MiB
)

// Release represents a GitHub release.
type Release struct {
	TagName string
	Body    string
	HTMLURL string
	Assets  []Asset
}

// Asset represents a release asset.
type Asset struct {
	Name               string
	BrowserDownloadURL string
	Size               int64
}

type httpDoer interface {
	Do(req *http.Request) (*http.Response, error)
}

// Checker checks for application updates via GitHub releases.
type Checker struct {
	HTTPClient       httpDoer
	LatestReleaseURL string
	CacheTTL         time.Duration

	mu    sync.Mutex
	cache *cacheEntry
}

type cacheEntry struct {
	timestamp time.Time
	release   *Release
}

type latestReleaseResponse struct {
	Draft      bool          `json:"draft"`
	HTMLURL    string        `json:"html_url"`
	Prerelease bool          `json:"prerelease"`
	TagName    string        `json:"tag_name"`
	Body       string        `json:"body"`
	Assets     []githubAsset `json:"assets"`
}

type githubAsset struct {
	Name               string `json:"name"`
	BrowserDownloadURL string `json:"browser_download_url"`
	Size               int64  `json:"size"`
}

// NewChecker creates a new update checker for the given GitHub repo.
// The URL format is https://api.github.com/repos/{owner}/{repo}/releases/latest.
func NewChecker(owner, repo string) *Checker {
	return &Checker{
		HTTPClient:       newSecureClient(),
		LatestReleaseURL: fmt.Sprintf("https://api.github.com/repos/%s/%s/releases/latest", owner, repo),
		CacheTTL:         DefaultCacheTTL,
	}
}

// Check checks for updates. Returns nil release if currentVersion is latest
// or if the version cannot be parsed as a stable semver.
func (c *Checker) Check(ctx context.Context, currentVersion string) (*Release, error) {
	return c.CheckWithForce(ctx, currentVersion, false)
}

// CheckWithForce forces a check, bypassing the in-memory cache when force is true.
func (c *Checker) CheckWithForce(ctx context.Context, currentVersion string, force bool) (*Release, error) {
	current, ok := parseStableVersion(currentVersion)
	if !ok {
		return nil, nil
	}

	if !force {
		c.mu.Lock()
		entry := c.cache
		ttl := c.CacheTTL
		c.mu.Unlock()

		if entry != nil && time.Since(entry.timestamp) < ttl {
			if entry.release != nil {
				latest, latestOK := parseStableVersion(entry.release.TagName)
				if latestOK {
					if compareStableVersions(current, latest) < 0 {
						if current.major == 0 && latest.major > 0 {
							return nil, nil
						}
						return entry.release, nil
					}
					return nil, nil
				}
			}
		}
	}

	release, err := c.fetchLatestRelease(ctx, currentVersion)
	if err != nil {
		return nil, err
	}

	latest, ok := parseStableVersion(release.TagName)
	if !ok {
		return nil, fmt.Errorf("latest release tag %q is not a stable semantic version", release.TagName)
	}

	c.mu.Lock()
	c.cache = &cacheEntry{
		timestamp: time.Now(),
		release:   release,
	}
	c.mu.Unlock()

	if compareStableVersions(current, latest) < 0 {
		if current.major == 0 && latest.major > 0 {
			return nil, nil
		}
		return release, nil
	}

	return nil, nil
}

func (c *Checker) fetchLatestRelease(ctx context.Context, currentVersion string) (*Release, error) {
	url := strings.TrimSpace(c.LatestReleaseURL)

	client := c.HTTPClient
	if client == nil {
		client = newSecureClient()
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("create latest release request: %w", err)
	}

	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("User-Agent", fmt.Sprintf("symaira-updatecheck/%s", strings.TrimSpace(currentVersion)))

	resp, err := client.Do(req) // #nosec G107 — URL is validated and points to GitHub API
	if err != nil {
		if isTLSCertificateError(err) {
			return nil, fmt.Errorf("update check failed: TLS certificate verification error - %w", err)
		}
		return nil, fmt.Errorf("request latest release: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		if resp.StatusCode == http.StatusForbidden && resp.Header.Get("X-RateLimit-Remaining") == "0" {
			return nil, fmt.Errorf("GitHub API rate limit exceeded")
		}
		return nil, fmt.Errorf("GitHub API returned HTTP %d", resp.StatusCode)
	}

	var apiResp latestReleaseResponse
	if err := json.NewDecoder(io.LimitReader(resp.Body, maxResponseBody)).Decode(&apiResp); err != nil {
		return nil, fmt.Errorf("decode latest release response: %w", err)
	}

	if apiResp.Draft {
		return nil, fmt.Errorf("latest release response returned a draft release")
	}
	if apiResp.Prerelease {
		return nil, fmt.Errorf("latest release response returned a prerelease")
	}
	if strings.TrimSpace(apiResp.TagName) == "" {
		return nil, fmt.Errorf("latest release response did not include a tag name")
	}

	assets := make([]Asset, 0, len(apiResp.Assets))
	for _, a := range apiResp.Assets {
		assets = append(assets, Asset{
			Name:               a.Name,
			BrowserDownloadURL: a.BrowserDownloadURL,
			Size:               a.Size,
		})
	}

	return &Release{
		TagName: strings.TrimSpace(apiResp.TagName),
		Body:    apiResp.Body,
		HTMLURL: strings.TrimSpace(apiResp.HTMLURL),
		Assets:  assets,
	}, nil
}

func isTLSCertificateError(err error) bool {
	var certErr *x509.CertificateInvalidError
	if errors.As(err, &certErr) {
		return true
	}
	var hostnameErr x509.HostnameError
	if errors.As(err, &hostnameErr) {
		return true
	}
	var unknownAuthorityErr x509.UnknownAuthorityError
	return errors.As(err, &unknownAuthorityErr)
}

type stableVersion struct {
	major int
	minor int
	patch int
}

func (v stableVersion) String() string {
	return fmt.Sprintf("%d.%d.%d", v.major, v.minor, v.patch)
}

func parseStableVersion(raw string) (stableVersion, bool) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return stableVersion{}, false
	}

	trimmed = strings.TrimPrefix(trimmed, "v")
	if strings.ContainsAny(trimmed, "-+") {
		return stableVersion{}, false
	}

	parts := strings.Split(trimmed, ".")
	if len(parts) != 3 {
		return stableVersion{}, false
	}

	values := make([]int, 0, len(parts))
	for _, part := range parts {
		if part == "" {
			return stableVersion{}, false
		}
		value, err := strconv.Atoi(part)
		if err != nil || value < 0 {
			return stableVersion{}, false
		}
		values = append(values, value)
	}

	return stableVersion{major: values[0], minor: values[1], patch: values[2]}, true
}

func compareStableVersions(left, right stableVersion) int {
	switch {
	case left.major != right.major:
		if left.major < right.major {
			return -1
		}
	case left.minor != right.minor:
		if left.minor < right.minor {
			return -1
		}
	case left.patch != right.patch:
		if left.patch < right.patch {
			return -1
		}
	default:
		return 0
	}

	return 1
}

func newSecureClient() *http.Client {
	return &http.Client{
		Timeout: 3 * time.Second,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				MinVersion: tls.VersionTLS13,
			},
		},
		// Keep redirects on the GitHub API host so the request cannot be
		// bounced to an attacker-controlled origin (which would invalidate the
		// "URL points to GitHub API" justification on the request call).
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if !isGitHubHost(req.URL.Host) {
				return fmt.Errorf("refusing redirect to non-GitHub host %q", req.URL.Host)
			}
			if len(via) >= 10 {
				return errors.New("stopped after 10 redirects")
			}
			return nil
		},
	}
}

// isGitHubHost reports whether host belongs to github.com (api or download hosts).
func isGitHubHost(host string) bool {
	if i := strings.IndexByte(host, ':'); i != -1 {
		host = host[:i]
	}
	host = strings.ToLower(host)
	return host == "github.com" || host == "api.github.com" ||
		strings.HasSuffix(host, ".github.com") ||
		strings.HasSuffix(host, ".githubusercontent.com")
}
