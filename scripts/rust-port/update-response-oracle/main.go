// Command update-response-oracle records response outcomes from public Checker.Check.
package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"

	"github.com/danieljustus/symaira-corekit/updatecheck"
)

type testCase struct {
	ID       string
	Current  string
	Response string
}

type release struct {
	TagName string  `json:"tag_name"`
	Body    string  `json:"body"`
	HTMLURL string  `json:"html_url"`
	Assets  []asset `json:"assets"`
}

type asset struct {
	Name               string `json:"name"`
	BrowserDownloadURL string `json:"browser_download_url"`
	Size               int64  `json:"size"`
}

type result struct {
	Release *release `json:"release"`
	Error   *string  `json:"error"`
}

type request struct {
	Count     int    `json:"count"`
	Method    string `json:"method"`
	Path      string `json:"path"`
	Accept    string `json:"accept"`
	UserAgent string `json:"user_agent"`
}

type observation struct {
	ID       string  `json:"id"`
	Current  string  `json:"current"`
	Response string  `json:"response"`
	Result   result  `json:"result"`
	Request  request `json:"request"`
}

func main() {
	cases := []testCase{
		{ID: "available-assets", Current: "v1.2.3", Response: `{"tag_name":" v1.3.0 ","body":"Release notes\nFixes","html_url":" https://github.com/acme/tool/releases/tag/v1.3.0 ","assets":[{"name":"tool-darwin-arm64.tar.gz","browser_download_url":"https://github.com/acme/tool/releases/download/v1.3.0/tool-darwin-arm64.tar.gz","size":12345},{"name":"checksums.txt","browser_download_url":"https://github.com/acme/tool/releases/download/v1.3.0/checksums.txt","size":87}]}`},
		{ID: "up-to-date", Current: "v1.2.3", Response: `{"tag_name":"v1.2.3","body":"Current","html_url":"https://github.com/acme/tool/releases/tag/v1.2.3","assets":[]}`},
		{ID: "older-release", Current: "v1.2.3", Response: `{"tag_name":"v1.2.2","body":"Old","html_url":"https://github.com/acme/tool/releases/tag/v1.2.2","assets":[]}`},
		{ID: "draft", Current: "v1.2.3", Response: `{"tag_name":"v1.3.0","draft":true}`},
		{ID: "prerelease", Current: "v1.2.3", Response: `{"tag_name":"v1.3.0-rc.1","prerelease":true}`},
		{ID: "empty-tag", Current: "v1.2.3", Response: `{"tag_name":"  "}`},
		{ID: "malformed-prerelease-tag", Current: "v1.2.3", Response: `{"tag_name":"v1.3.0-rc.1"}`},
		{ID: "malformed-tag", Current: "v1.2.3", Response: `{"tag_name":"latest"}`},
		{ID: "invalid-current", Current: "dev", Response: `{"tag_name":"v1.3.0"}`},
	}

	observed := make([]observation, 0, len(cases))
	for _, test := range cases {
		var seen request
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			seen.Count++
			seen.Method = r.Method
			seen.Path = r.URL.Path
			seen.Accept = r.Header.Get("Accept")
			seen.UserAgent = r.Header.Get("User-Agent")
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(test.Response))
		}))

		checker := updatecheck.NewChecker("fixture", "response")
		checker.HTTPClient = server.Client()
		checker.LatestReleaseURL = server.URL + "/releases/latest"
		checker.CachePath = ""
		got, err := checker.Check(context.Background(), test.Current)
		server.Close()

		item := observation{ID: test.ID, Current: test.Current, Response: test.Response, Request: seen}
		if got != nil {
			assets := make([]asset, 0, len(got.Assets))
			for _, item := range got.Assets {
				assets = append(assets, asset{Name: item.Name, BrowserDownloadURL: item.BrowserDownloadURL, Size: item.Size})
			}
			item.Result.Release = &release{TagName: got.TagName, Body: got.Body, HTMLURL: got.HTMLURL, Assets: assets}
		}
		if err != nil {
			message := err.Error()
			item.Result.Error = &message
		}
		observed = append(observed, item)
	}
	if err := json.NewEncoder(os.Stdout).Encode(observed); err != nil {
		os.Exit(1)
	}
}
