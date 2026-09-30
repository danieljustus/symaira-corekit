// Command update-cache-persistence-oracle captures live cache persistence
// behavior from the public Go Checker for comparison with the Rust crate.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"time"

	"github.com/danieljustus/symaira-corekit/updatecheck"
)

const normalBody = `{"tag_name":"v1.3.0","body":"HTML <>& \u2028 \u2029 literal\\u2028","html_url":" https://github.com/o/r/releases/tag/v1.3.0 ","assets":[{"name":"tool.tar.gz","browser_download_url":"https://github.com/o/r/releases/download/v1.3.0/tool.tar.gz","size":42}]}`

type result struct {
	Tag   string `json:"tag,omitempty"`
	Error bool   `json:"error"`
}

type observation struct {
	ID                string  `json:"id"`
	Requests          int     `json:"requests"`
	Result            result  `json:"result"`
	CacheBytes        string  `json:"cache_bytes,omitempty"`
	CacheExists       bool    `json:"cache_exists"`
	CacheMode         *uint32 `json:"cache_mode,omitempty"`
	DirectoryMode     *uint32 `json:"directory_mode,omitempty"`
	AtomicReplace     *bool   `json:"atomic_replace,omitempty"`
	HardlinkPreserved *bool   `json:"hardlink_preserved,omitempty"`
}

type timestampSample struct {
	UnixMillis  int64  `json:"unix_millis"`
	RFC3339Nano string `json:"rfc3339_nano"`
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	cases := make([]observation, 0, 4)
	for _, item := range []struct{ id, body string }{
		{"normal", normalBody},
		{"duplicate-tag-casefold", `{"TAG_NAME":"v1.2.0","tag_name":"v1.3.0"}`},
		{"trailing-json", normalBody + " trailing-data"},
	} {
		observed, err := observe(item.id, item.body)
		if err != nil {
			return err
		}
		cases = append(cases, observed)
	}
	atomic, err := observeAtomicReplace()
	if err != nil {
		return err
	}
	cases = append(cases, atomic)

	samples := make([]timestampSample, 0, 4)
	for _, millis := range []int64{1000, 1001, 1120, 1100} {
		samples = append(samples, timestampSample{
			UnixMillis:  millis,
			RFC3339Nano: time.UnixMilli(millis).UTC().Format(time.RFC3339Nano),
		})
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]any{
		"cases":               cases,
		"timestamp_samples":   samples,
		"unix_mode_supported": runtime.GOOS != "windows",
	})
}

func observe(id, body string) (observation, error) {
	root, err := os.MkdirTemp("", "upd003-live-cache-")
	if err != nil {
		return observation{}, err
	}
	defer os.RemoveAll(root)
	requests := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		requests++
		_, _ = fmt.Fprint(w, body)
	}))
	defer server.Close()
	cachePath := filepath.Join(root, "cache", "cache.json")
	checker := newChecker(server, cachePath)
	release, checkErr := checker.CheckWithForce(context.Background(), "v1.0.0", true)
	item := observation{
		ID:       id,
		Requests: requests,
		Result:   result{Error: checkErr != nil},
	}
	if release != nil {
		item.Result.Tag = release.TagName
	}
	if raw, readErr := readObservation(root, "cache/cache.json"); readErr == nil {
		item.CacheExists = true
		item.CacheBytes, err = normalizeTimestamp(raw)
		if err != nil {
			return observation{}, err
		}
		if err := readModes(&item, cachePath); err != nil {
			return observation{}, err
		}
	}
	return item, nil
}

func observeAtomicReplace() (observation, error) {
	root, err := os.MkdirTemp("", "upd003-live-cache-atomic-")
	if err != nil {
		return observation{}, err
	}
	defer os.RemoveAll(root)
	responses := []string{
		normalBody,
		`{"tag_name":"v1.4.0","body":"replacement","assets":[]}`,
	}
	requests := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Connection", "close")
		if requests >= len(responses) {
			http.Error(w, "unexpected extra request", http.StatusInternalServerError)
			return
		}
		_, _ = fmt.Fprint(w, responses[requests])
		requests++
	}))
	defer server.Close()
	cachePath := filepath.Join(root, "cache", "cache.json")
	checker := newChecker(server, cachePath)
	oldRelease, err := checker.CheckWithForce(context.Background(), "v1.0.0", true)
	if err != nil || oldRelease == nil {
		return observation{}, fmt.Errorf("initial atomic-cache check: release=%v error=%v", oldRelease, err)
	}
	oldInfo, err := os.Stat(cachePath)
	if err != nil {
		return observation{}, err
	}
	snapshot := cachePath + ".snapshot"
	if err := os.Link(cachePath, snapshot); err != nil {
		return observation{}, fmt.Errorf("create cache hardlink: %w", err)
	}
	oldBytes, err := readObservation(root, "cache/cache.json")
	if err != nil {
		return observation{}, err
	}
	newRelease, err := checker.CheckWithForce(context.Background(), "v1.0.0", true)
	if err != nil || newRelease == nil {
		return observation{}, fmt.Errorf("replacement atomic-cache check: release=%v error=%v", newRelease, err)
	}
	newInfo, err := os.Stat(cachePath)
	if err != nil {
		return observation{}, err
	}
	snapshotBytes, err := readObservation(root, "cache/cache.json.snapshot")
	if err != nil {
		return observation{}, err
	}
	currentBytes, err := readObservation(root, "cache/cache.json")
	if err != nil {
		return observation{}, err
	}
	var atomicReplace *bool
	if runtime.GOOS != "windows" {
		changed := !os.SameFile(oldInfo, newInfo)
		atomicReplace = &changed
	}
	hardlinkPreserved := bytes.Equal(snapshotBytes, oldBytes)
	item := observation{
		ID:                "atomic-replace",
		Requests:          requests,
		Result:            result{Tag: newRelease.TagName},
		CacheExists:       true,
		CacheBytes:        "",
		AtomicReplace:     atomicReplace,
		HardlinkPreserved: &hardlinkPreserved,
	}
	item.CacheBytes, err = normalizeTimestamp(currentBytes)
	if err != nil {
		return observation{}, err
	}
	if err := readModes(&item, cachePath); err != nil {
		return observation{}, err
	}
	return item, nil
}

func newChecker(server *httptest.Server, cachePath string) *updatecheck.Checker {
	checker := updatecheck.NewChecker("fixture", "cache")
	checker.HTTPClient = server.Client()
	checker.LatestReleaseURL = server.URL
	checker.CachePath = cachePath
	return checker
}

func normalizeTimestamp(raw []byte) (string, error) {
	const marker = `"timestamp":"`
	start := bytes.Index(raw, []byte(marker))
	if start < 0 {
		return "", fmt.Errorf("cache bytes have no timestamp field")
	}
	valueStart := start + len(marker)
	valueEndRel := bytes.IndexByte(raw[valueStart:], '"')
	if valueEndRel < 0 {
		return "", fmt.Errorf("cache timestamp is unterminated")
	}
	valueEnd := valueStart + valueEndRel
	if bytes.Contains(raw[valueEnd+1:], []byte(marker)) {
		return "", fmt.Errorf("cache bytes contain multiple timestamp fields")
	}
	normalized := make([]byte, 0, len(raw)-valueEndRel)
	normalized = append(normalized, raw[:valueStart]...)
	normalized = append(normalized, "<TIMESTAMP>"...)
	normalized = append(normalized, raw[valueEnd:]...)
	return string(normalized), nil
}

func readModes(item *observation, cachePath string) error {
	fileInfo, err := os.Stat(cachePath)
	if err != nil {
		return err
	}
	dirInfo, err := os.Stat(filepath.Dir(cachePath))
	if err != nil {
		return err
	}
	fileMode, dirMode := uint32(fileInfo.Mode().Perm()), uint32(dirInfo.Mode().Perm())
	item.CacheMode, item.DirectoryMode = &fileMode, &dirMode
	return nil
}

// readObservation confines observation reads to the private temporary root.
func readObservation(root, name string) ([]byte, error) {
	dir, err := os.OpenRoot(root)
	if err != nil {
		return nil, err
	}
	defer dir.Close()
	return dir.ReadFile(name)
}
