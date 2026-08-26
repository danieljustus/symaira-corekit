package updatecheck

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"strings"
	"testing"
	"time"
)

type updateCheckFixture struct {
	CacheTTLHours            int      `json:"cache_ttl_hours"`
	PrereleaseRejected       bool     `json:"prerelease_and_build_metadata_rejected"`
	PrereleaseMarkers        []string `json:"prerelease_and_build_metadata_markers"`
	V0MajorGapSuppressed     bool     `json:"v0_major_gap_suppressed"`
	DefaultAPITimeoutSeconds int      `json:"default_api_timeout_seconds"`
}

func loadUpdateCheckFixture(t *testing.T) updateCheckFixture {
	t.Helper()
	raw, err := os.ReadFile("../contracts/update_check_invariants.json")
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var f updateCheckFixture
	if err := json.Unmarshal(raw, &f); err != nil {
		t.Fatalf("parse fixture: %v", err)
	}
	return f
}

// TestCacheTTLMatchesContractFixture asserts DefaultCacheTTL matches the
// fixture that appkit's Swift port asserts the same value against.
func TestCacheTTLMatchesContractFixture(t *testing.T) {
	f := loadUpdateCheckFixture(t)
	want := time.Duration(f.CacheTTLHours) * time.Hour
	if DefaultCacheTTL != want {
		t.Fatalf("DefaultCacheTTL = %v, fixture claims %v", DefaultCacheTTL, want)
	}
}

// TestAPITimeoutMatchesContractFixture asserts DefaultAPITimeout matches the fixture.
func TestAPITimeoutMatchesContractFixture(t *testing.T) {
	f := loadUpdateCheckFixture(t)
	want := time.Duration(f.DefaultAPITimeoutSeconds) * time.Second
	if DefaultAPITimeout != want {
		t.Fatalf("DefaultAPITimeout = %v, fixture claims %v", DefaultAPITimeout, want)
	}
}

// TestPrereleaseVersionsRejectedPerFixture asserts that version strings
// carrying any of the fixture's prerelease/build-metadata markers are
// treated as unparseable, per the fixture's
// prerelease_and_build_metadata_rejected invariant.
func TestPrereleaseVersionsRejectedPerFixture(t *testing.T) {
	f := loadUpdateCheckFixture(t)
	if !f.PrereleaseRejected {
		t.Skip("fixture does not claim prerelease rejection")
	}

	cases := []string{"v1.2.3-rc1", "v1.2.3+build5", "1.2.3-alpha"}
	for _, raw := range cases {
		hasMarker := false
		for _, m := range f.PrereleaseMarkers {
			if strings.Contains(raw, m) {
				hasMarker = true
			}
		}
		if !hasMarker {
			t.Fatalf("test case %q does not contain any fixture marker %v", raw, f.PrereleaseMarkers)
		}
		if _, ok := parseStableVersion(raw); ok {
			t.Errorf("parseStableVersion(%q) succeeded, fixture requires rejection", raw)
		}
	}

	if _, ok := parseStableVersion("v1.2.3"); !ok {
		t.Error("parseStableVersion(\"v1.2.3\") failed, expected a stable version to parse")
	}
}

// TestV0MajorGapSuppressedPerFixture asserts that a v0.x consumer is not
// offered a v1+ release, end-to-end through Checker.Check, per the fixture's
// v0_major_gap_suppressed invariant.
func TestV0MajorGapSuppressedPerFixture(t *testing.T) {
	f := loadUpdateCheckFixture(t)
	if !f.V0MajorGapSuppressed {
		t.Skip("fixture does not claim v0-major gap suppression")
	}

	c := &Checker{
		HTTPClient: stubHTTPDoer{
			do: func(req *http.Request) (*http.Response, error) {
				body := `{"tag_name":"v1.0.0","draft":false,"prerelease":false}`
				return &http.Response{
					StatusCode: http.StatusOK,
					Body:       io.NopCloser(strings.NewReader(body)),
					Header:     make(http.Header),
				}, nil
			},
		},
		LatestReleaseURL: "https://api.github.com/repos/owner/repo/releases/latest",
		CacheTTL:         DefaultCacheTTL,
	}

	release, err := c.Check(context.Background(), "v0.9.0")
	if err != nil {
		t.Fatalf("Check returned error: %v", err)
	}
	if release != nil {
		t.Fatalf("Check returned release %+v, fixture requires suppression of a v0 -> v1 jump", release)
	}
}
