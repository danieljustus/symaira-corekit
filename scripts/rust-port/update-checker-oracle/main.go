// Public Go Checker oracle. All expected results come from NewChecker/CheckWithForce.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/danieljustus/symaira-corekit/updatecheck"
)

type reply struct {
	Body      string `json:"body"`
	Status    int    `json:"status"`
	RateLimit bool   `json:"rate_limit"`
	Error     string `json:"error"`
}
type step struct {
	Override bool   `json:"endpoint_override"`
	Current  string `json:"current"`
	Force    bool   `json:"force"`
	Fresh    bool   `json:"fresh"`
	Expire   bool   `json:"expire"`
}
type result struct {
	Release    *updatecheck.Release `json:"release"`
	Error      any                  `json:"error"`
	Calls      int                  `json:"calls"`
	UserAgents []string             `json:"user_agents"`
	Exists     bool                 `json:"cache_exists"`
}
type scenario struct {
	ID      string   `json:"id"`
	Mode    string   `json:"mode"`
	Custom  bool     `json:"custom_endpoint"`
	Replies []reply  `json:"replies"`
	Steps   []step   `json:"steps"`
	Results []result `json:"results"`
}
type doer func(*http.Request) (*http.Response, error)

func (f doer) Do(r *http.Request) (*http.Response, error) { return f(r) }

func main() {
	root, err := os.MkdirTemp("", "checker-oracle-")
	must(err)
	defer os.RemoveAll(root)
	must(os.Setenv("HOME", filepath.Join(root, "home")))
	must(os.Setenv("USERPROFILE", filepath.Join(root, "home")))
	must(os.Setenv("XDG_CACHE_HOME", filepath.Join(root, "cache")))
	metadata := `{"tag_name":" v1.3.0 ","body":"notes <&>\nnext","html_url":" https://github.com/o/r/releases/v1.3.0 ","assets":[{"name":"tool.tar.gz","browser_download_url":"https://github.com/o/r/a","size":42},{"name":"checksums","browser_download_url":"https://github.com/o/r/s","size":7}]}`
	valid := reply{Body: metadata, Status: 200}
	newer := step{Current: " v1.2.3 "}
	cases := []scenario{
		{ID: "metadata-newer", Mode: "empty", Replies: []reply{valid}, Steps: []step{newer}},
		{ID: "equal", Mode: "empty", Replies: []reply{valid}, Steps: []step{{Current: "1.3.0"}}},
		{ID: "older", Mode: "empty", Replies: []reply{valid}, Steps: []step{{Current: "2.0.0"}}},
		{ID: "v0-to-v1", Mode: "empty", Replies: []reply{valid}, Steps: []step{{Current: "v0.9.0"}}},
		{ID: "invalid-current", Mode: "explicit", Replies: []reply{valid}, Steps: []step{{Current: "dev", Force: true}, {Current: "1.2.3-beta"}, {Current: ""}, {Current: "1.2"}}},
		{ID: "memory-conditioned", Mode: "empty", Replies: []reply{valid}, Steps: []step{newer, {Current: "1.3.0"}, {Current: "2.0.0"}, {Current: "0.9.0"}, newer}},
		{ID: "forced-refresh", Mode: "explicit", Replies: []reply{valid, {Status: 200, Body: `{"tag_name":"v1.4.0"}`}, {Status: 200, Body: `{"tag_name":"v1.6.0"}`}}, Steps: []step{newer, {Current: "1.2.3", Force: true}, newer, {Current: "1.2.3", Fresh: true, Force: true}}},
		{ID: "empty-persistence", Mode: "empty", Replies: []reply{valid, valid}, Steps: []step{newer, {Current: "1.2.3", Fresh: true}}},
		{ID: "persistent", Mode: "explicit", Replies: []reply{valid}, Steps: []step{newer, {Current: "1.2.3", Fresh: true}}},
		{ID: "expired", Mode: "explicit", Replies: []reply{valid, {Status: 200, Body: `{"tag_name":"v1.4.0"}`}}, Steps: []step{newer, {Current: "1.2.3", Expire: true}}},
		{ID: "default-canonical", Mode: "default", Replies: []reply{valid}, Steps: []step{newer, {Current: "1.2.3", Fresh: true}}},
		{ID: "endpoint-isolation", Mode: "default", Replies: []reply{valid, {Status: 200, Body: `{"tag_name":"v1.4.0"}`}}, Steps: []step{newer, {Current: "1.2.3", Fresh: true, Override: true}, {Current: "1.2.3", Fresh: true}}},
		{ID: "endpoint-explicit", Mode: "explicit", Custom: true, Replies: []reply{valid}, Steps: []step{newer, {Current: "1.2.3", Fresh: true}}},
		{ID: "valid-invalid-valid", Mode: "explicit", Replies: []reply{valid, {Status: 200, Body: `{"tag_name":"broken"}`}, {Status: 200, Body: `{"tag_name":"v1.5.0"}`}}, Steps: []step{newer, {Current: "1.2.3", Force: true}, {Current: "1.2.3", Force: true}, newer}},
		{ID: "invalid-retry", Mode: "explicit", Replies: []reply{{Status: 200, Body: `{"tag_name":"broken"}`}, valid}, Steps: []step{newer, newer}},
		{ID: "draft", Mode: "explicit", Replies: []reply{{Status: 200, Body: `{"draft":true,"tag_name":"v1.4.0"}`}}, Steps: []step{newer}},
		{ID: "prerelease", Mode: "explicit", Replies: []reply{{Status: 200, Body: `{"prerelease":true,"tag_name":"v1.4.0"}`}}, Steps: []step{newer}},
		{ID: "missing-tag", Mode: "explicit", Replies: []reply{{Status: 200, Body: `{"body":"missing"}`}}, Steps: []step{newer}},
		{ID: "http-404", Mode: "explicit", Replies: []reply{{Status: 404}}, Steps: []step{newer}},
		{ID: "rate-limit", Mode: "explicit", Replies: []reply{{Status: 403, RateLimit: true}}, Steps: []step{newer}},
		{ID: "transport-error", Mode: "explicit", Replies: []reply{{Error: "oracle transport failure"}}, Steps: []step{newer}},
	}
	for i := range cases {
		c := &cases[i]
		owner := "owner-" + c.ID
		calls := 0
		agents := []string{}
		transport := doer(func(r *http.Request) (*http.Response, error) {
			if calls >= len(c.Replies) {
				panic("unexpected extra HTTP request: " + c.ID)
			}
			reply := c.Replies[calls]
			calls++
			agents = append(agents, r.Header.Get("User-Agent"))
			if r.Header.Get("Accept") != "application/vnd.github+json" {
				panic("missing Accept")
			}
			if reply.Error != "" {
				return nil, errors.New(reply.Error)
			}
			headers := http.Header{}
			if reply.RateLimit {
				headers.Set("X-RateLimit-Remaining", "0")
			}
			return &http.Response{StatusCode: reply.Status, Header: headers, Body: io.NopCloser(strings.NewReader(reply.Body))}, nil
		})
		newChecker := func() *updatecheck.Checker {
			x := updatecheck.NewChecker(owner, "repo")
			x.HTTPClient = transport
			if c.Custom {
				x.LatestReleaseURL = "https://example.invalid/latest"
			}
			if c.Mode == "empty" {
				x.CachePath = ""
			}
			if c.Mode == "explicit" {
				x.CachePath = filepath.Join(root, c.ID, "response.json")
			}
			return x
		}
		checker := newChecker()
		for _, s := range c.Steps {
			if s.Fresh {
				checker = newChecker()
			}
			if s.Override {
				checker.LatestReleaseURL = "https://example.invalid/latest"
			}
			if s.Expire {
				checker.CacheTTL = 0 * time.Second
			}
			release, err := checker.CheckWithForce(context.Background(), s.Current, s.Force)
			var errorText any
			if err != nil {
				errorText = err.Error()
			}
			_, statErr := os.Stat(checker.CachePath)
			c.Results = append(c.Results, result{release, errorText, calls, append([]string{}, agents...), statErr == nil})
		}
	}
	path := updatecheck.DefaultCachePath("../owner", "repo/../../x")
	relative, err := filepath.Rel(os.Getenv("XDG_CACHE_HOME"), path)
	must(err)
	canonical := updatecheck.NewChecker("owner", "repo").LatestReleaseURL
	fallback := func(xdg string) string {
		must(os.Setenv("XDG_CACHE_HOME", xdg))
		p := updatecheck.DefaultCachePath("../owner", "repo/../../x")
		r, e := filepath.Rel(os.Getenv("HOME"), p)
		must(e)
		return filepath.ToSlash(r)
	}
	output := map[string]any{"cases": cases, "default_path": filepath.ToSlash(relative), "canonical_url": canonical, "relative_xdg_path": fallback("relative-cache"), "empty_xdg_path": fallback("")}
	must(json.NewEncoder(os.Stdout).Encode(output))
}
func must(err error) {
	if err != nil {
		panic(fmt.Sprint(err))
	}
}
