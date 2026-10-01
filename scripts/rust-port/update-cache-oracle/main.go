// Command update-cache-oracle records public Checker cache behavior.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"time"

	"github.com/danieljustus/symaira-corekit/updatecheck"
)

type result struct {
	Release *string `json:"release"`
	Error   bool    `json:"error"`
}

type observation struct {
	ID       string `json:"id"`
	Requests int    `json:"requests"`
	Result   result `json:"result"`
}

func main() {
	responses := []struct {
		status int
		body   string
	}{
		{http.StatusOK, `{"tag_name":"v1.2.0","body":"initial"}`},
		{http.StatusOK, `{"tag_name":"v1.3.0","body":"forced"}`},
		{http.StatusOK, `{"tag_name":"v1.4.0","body":"expired"}`},
		{http.StatusInternalServerError, `{"message":"temporary failure"}`},
		{http.StatusOK, `{"tag_name":"v1.5.0","body":"recovered"}`},
	}
	requests := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		response := responses[requests]
		requests++
		w.WriteHeader(response.status)
		_, _ = fmt.Fprint(w, response.body)
	}))
	defer server.Close()

	cachePath := filepath.Join(os.TempDir(), fmt.Sprintf("upd003-%d.json", time.Now().UnixNano()))
	defer os.Remove(cachePath)
	checker := updatecheck.NewChecker("fixture", "cache")
	checker.HTTPClient = server.Client()
	checker.LatestReleaseURL = server.URL
	checker.CachePath = cachePath
	checker.CacheTTL = updatecheck.DefaultCacheTTL
	results := make([]observation, 0, 7)
	appendResult := func(id string, release *updatecheck.Release, err error) {
		item := observation{ID: id, Requests: requests}
		if release != nil {
			item.Result.Release = &release.TagName
		}
		item.Result.Error = err != nil
		results = append(results, item)
	}
	check := func(id string, c *updatecheck.Checker, force bool) {
		release, err := c.CheckWithForce(context.Background(), "v1.0.0", force)
		appendResult(id, release, err)
	}
	check("initial-fetch", checker, false)
	check("cache-hit", checker, false)
	check("forced-refresh", checker, true)
	check("cache-after-force", checker, false)
	checker.CacheTTL = 0 // The public TTL field exercises expiry without a 24-hour wait.
	check("expired-fetch", checker, false)
	check("expired-refresh-failure", checker, false)
	// A fresh checker proves that a failed refresh left the prior disk entry intact.
	second := updatecheck.NewChecker("fixture", "cache")
	second.HTTPClient = server.Client()
	second.LatestReleaseURL = server.URL
	second.CachePath = cachePath
	second.CacheTTL = updatecheck.DefaultCacheTTL
	check("persistent-across-checkers", second, false)
	if err := json.NewEncoder(os.Stdout).Encode(map[string]any{
		"default_cache_ttl_seconds": int(updatecheck.DefaultCacheTTL.Seconds()),
		"cases":                     results,
	}); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
