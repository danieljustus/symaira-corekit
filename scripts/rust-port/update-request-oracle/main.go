// Command update-request-oracle records update HTTP behavior through updatecheck's public API.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/danieljustus/symaira-corekit/updatecheck"
)

type observation struct {
	ID              string            `json:"id"`
	URL             string            `json:"url_after_trim"`
	RequestLine     string            `json:"request_line,omitempty"`
	Headers         map[string]string `json:"headers,omitempty"`
	ResponseHeaders map[string]string `json:"response_headers,omitempty"`
	Status          int               `json:"status,omitempty"`
	ErrorCode       string            `json:"error_code,omitempty"`
	Error           string            `json:"error_message,omitempty"`
}

type scenario struct {
	id, body string
	status   int
	headers  http.Header
	delay    time.Duration
}

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--serve-tls" {
		server := localServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			_, _ = w.Write([]byte(`{"tag_name":"v1.2.4"}`))
		}), true)
		fmt.Println(server.URL)
		var stop [1]byte
		_, _ = os.Stdin.Read(stop[:])
		server.Close()
		return
	}
	results := []observation{
		observe(scenario{id: "request", body: `{"tag_name":"v1.2.4"}`, status: http.StatusOK}, "  %s/request?x=1  ", nil),
		observe(scenario{id: "404", status: http.StatusNotFound}, "%s/not-found", nil),
		observe(scenario{id: "429-retry-after", status: http.StatusTooManyRequests, headers: http.Header{"Retry-After": {"17"}}}, "%s/rate-limited", nil),
		observe(scenario{id: "malformed-json", body: `{"tag_name":`, status: http.StatusOK}, "%s/malformed", nil),
		observeRefusal(),
		observe(scenario{id: "timeout", body: `{"tag_name":"v1.2.4"}`, status: http.StatusOK, delay: 100 * time.Millisecond}, "%s/slow", timeoutClient(20*time.Millisecond)),
		observeTLSFailure(),
	}
	client := updatecheck.NewSecureClient()
	tr := client.Transport.(*http.Transport)
	results = append(results, observation{ID: "secure-client", ErrorCode: "tls_minimum", Error: fmt.Sprintf("min_tls_version=%d; timeout=%dms", tr.TLSClientConfig.MinVersion, client.Timeout/time.Millisecond)})
	results = append(results, observation{ID: "redirect-foreign", ErrorCode: "refused", Error: redirectError(client, "https://evil.example/x", "https://api.github.com/x")})
	results = append(results, observation{ID: "redirect-github", ErrorCode: "allowed", Error: redirectError(client, "https://github.com/x", "https://api.github.com/x")})
	via := make([]*http.Request, 10)
	for i := range via {
		via[i] = &http.Request{URL: mustURL("https://api.github.com/x")}
	}
	err := client.CheckRedirect(&http.Request{URL: mustURL("https://api.github.com/y")}, via)
	results = append(results, observation{ID: "redirect-cap", ErrorCode: "refused", Error: err.Error()})
	if err := json.NewEncoder(os.Stdout).Encode(results); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func observe(s scenario, urlPattern string, client *http.Client) observation {
	var line string
	var headers map[string]string
	server := localServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		line = fmt.Sprintf("%s %s %s", r.Method, r.URL.RequestURI(), r.Proto)
		headers = make(map[string]string, len(r.Header)+1)
		headers["Host"] = normalizeHost(r.Host)
		for key, values := range r.Header {
			sort.Strings(values)
			headers[key] = strings.Join(values, ", ")
		}
		headers["If-None-Match"] = r.Header.Get("If-None-Match")
		for key, values := range s.headers {
			for _, value := range values {
				w.Header().Add(key, value)
			}
		}
		if s.delay > 0 {
			time.Sleep(s.delay)
		}
		if s.status != 0 {
			w.WriteHeader(s.status)
		}
		_, _ = w.Write([]byte(s.body))
	}), false)
	defer server.Close()
	endpoint := fmt.Sprintf(urlPattern, server.URL)
	result := run(s.id, endpoint, &line, &headers, client)
	if len(s.headers) != 0 {
		result.ResponseHeaders = make(map[string]string, len(s.headers))
		for key, values := range s.headers {
			result.ResponseHeaders[key] = strings.Join(values, ", ")
		}
	}
	return result
}

func run(id, endpoint string, line *string, headers *map[string]string, client *http.Client) observation {
	trimmed := strings.TrimSpace(endpoint)
	checker := updatecheck.NewChecker("fixture", "stable")
	checker.LatestReleaseURL = endpoint
	checker.CachePath = ""
	if client == nil {
		client = &http.Client{Timeout: 2 * time.Second}
	}
	checker.HTTPClient = client
	_, err := checker.Check(context.Background(), " 1.2.3 ")
	result := observation{ID: id, URL: normalizeURL(trimmed), RequestLine: *line, Headers: *headers}
	switch id {
	case "404":
		result.Status = http.StatusNotFound
	case "429-retry-after":
		result.Status = http.StatusTooManyRequests
	case "request", "malformed-json", "timeout":
		result.Status = http.StatusOK
	}
	if err != nil {
		result.ErrorCode, result.Error = classify(err)
	}
	return result
}

func observeRefusal() observation {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		panic(err)
	}
	endpoint := "http://" + listener.Addr().String() + "/refused"
	_ = listener.Close()
	var line string
	var headers map[string]string
	return run("connection-refused", endpoint, &line, &headers, nil)
}

func observeTLSFailure() observation {
	server := localServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"tag_name":"v1.2.4"}`))
	}), true)
	defer server.Close()
	var line string
	var headers map[string]string
	return run("tls-certificate", server.URL, &line, &headers, updatecheck.NewSecureClientWithTimeout(2*time.Second))
}

func localServer(handler http.Handler, tlsEnabled bool) *httptest.Server {
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		panic(err)
	}
	server := &httptest.Server{Config: &http.Server{Handler: handler, ReadHeaderTimeout: 5 * time.Second}, Listener: listener}
	if tlsEnabled {
		server.StartTLS()
	} else {
		server.Start()
	}
	return server
}

func timeoutClient(timeout time.Duration) *http.Client { return &http.Client{Timeout: timeout} }

func classify(err error) (string, string) {
	if err == nil {
		return "", ""
	}
	text := err.Error()
	switch {
	case strings.Contains(text, "HTTP 404"):
		return "http_404", text
	case strings.Contains(text, "HTTP 429"):
		return "http_429", text
	case strings.Contains(text, "decode latest release response"):
		return "malformed_json", text
	case strings.Contains(text, "TLS certificate verification error"):
		return "tls_certificate", "update check failed: TLS certificate verification error"
	case errors.Is(err, context.DeadlineExceeded) || strings.Contains(text, "Client.Timeout"):
		return "timeout", "request latest release"
	case strings.Contains(text, "connection refused"):
		return "connection_refused", "request latest release"
	default:
		return "network", "request latest release"
	}
}

func normalizeURL(raw string) string {
	u, err := url.Parse(raw)
	if err != nil {
		return raw
	}
	if u.Port() != "" {
		u.Host = u.Hostname() + ":<port>"
	}
	return u.String()
}

func normalizeHost(raw string) string {
	if host, _, err := net.SplitHostPort(raw); err == nil {
		return net.JoinHostPort(host, "<port>")
	}
	return raw
}

func redirectError(client *http.Client, to, from string) string {
	err := client.CheckRedirect(&http.Request{URL: mustURL(to)}, []*http.Request{{URL: mustURL(from)}})
	if err == nil {
		return ""
	}
	return err.Error()
}

func mustURL(raw string) *url.URL {
	u, err := url.Parse(raw)
	if err != nil {
		panic(err)
	}
	return u
}
