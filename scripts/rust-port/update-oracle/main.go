// Command update-oracle records stable release decisions through the public Go Checker.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"

	"github.com/danieljustus/symaira-corekit/updatecheck"
)

type observation struct {
	Current   string `json:"current"`
	Latest    string `json:"latest"`
	Available bool   `json:"available"`
	Invalid   bool   `json:"invalid_latest"`
	Requests  int    `json:"requests"`
}

func main() {
	inputs := [][2]string{
		{"dev", "v1.2.3"}, {"v1.2.3-rc1", "v1.2.4"},
		{"v1.2.3+build", "v1.2.4"}, {"", "v1.2.4"},
		{"v0.9.0", "v1.0.0"}, {"v0.9.0", "v0.10.0"},
		{"v1.2.3", "v1.2.3"}, {"v1.2.3", "v1.2.2"},
		{"  v1.2.3  ", "v1.2.4"}, {"+1.2.3", "v1.2.4"},
		{"v1.2.3", "v1.2.4-rc1"}, {"v1.2.3", "latest"},
		{"1.2.3", "1.2.4"}, {"v1.2", "v1.2.4"},
		{"v1.2.3.4", "v1.2.4"}, {"v1..3", "v1.2.4"},
		{"v1.a.3", "v1.2.4"}, {"v-1.2.3", "v1.2.4"},
		{"v+1.2.3", "v1.2.4"}, {"v1.2.+3", "v1.2.4"},
		{"v01.02.003", "v1.2.4"}, {"V1.2.3", "v1.2.4"},
		{"v1.2.3", " v1.2.4 "}, {"v1.2.3", "v1.2.3+build"},
		{"v1.2.3", "v1.2"}, {"v1.2.3", "v1.2.4.5"},
		{"v1.2.3", "v1.a.4"}, {"v1.2.3", "v-1.2.4"},
		{"v1.2.3", "v1.2.+4"}, {"v0.9.0", "v0.9.1"},
	}
	results := make([]observation, 0, len(inputs))
	for _, input := range inputs {
		requests := 0
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			requests++
			_ = json.NewEncoder(w).Encode(map[string]string{"tag_name": input[1]})
		}))
		checker := updatecheck.NewChecker("fixture", "stable")
		checker.HTTPClient = server.Client()
		checker.LatestReleaseURL = server.URL
		checker.CachePath = ""
		release, err := checker.Check(context.Background(), input[0])
		server.Close()
		results = append(results, observation{
			Current: input[0], Latest: input[1], Available: release != nil,
			Invalid: err != nil, Requests: requests,
		})
	}
	if err := json.NewEncoder(os.Stdout).Encode(results); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
