// Record public Go APIs with controlled transports; no production executable or credentials.
package main

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/danieljustus/symaira-corekit/updatecheck"
	"github.com/danieljustus/symaira-corekit/updatecheck/cosign"
	"github.com/danieljustus/symaira-corekit/updatecheck/installmethod"
	"github.com/danieljustus/symaira-corekit/updatecheck/updateapply"
)

type transport func(*http.Request) (*http.Response, error)

func (f transport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

type cancelBody struct {
	ctx   context.Context
	ready chan struct{}
	once  sync.Once
}

func (b *cancelBody) Read([]byte) (int, error) {
	b.once.Do(func() { close(b.ready) })
	<-b.ctx.Done()
	return 0, b.ctx.Err()
}
func (b *cancelBody) Close() error { return nil }

type observation struct {
	ID        string `json:"id"`
	Cancelled bool   `json:"cancelled"`
	Cache     bool   `json:"cache"`
	Target    string `json:"target"`
	Message   string `json:"message"`
	Identity  bool   `json:"identity"`
	Body      string `json:"body"`
	Residue   bool   `json:"residue"`
}

func serve() {
	server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/asset-body/checksums" || r.URL.Path == "/apply/checksums" {
			_, _ = fmt.Fprintf(w, "%x  tool_linux_amd64\n", sha256.Sum256([]byte("new")))
			return
		}
		if r.URL.Path == "/apply/asset" {
			_, _ = io.WriteString(w, "new")
			return
		}
		if strings.HasPrefix(r.URL.Path, "/injected") {
			_, _ = io.WriteString(w, "injected")
			return
		}
		if strings.HasPrefix(r.URL.Path, "/body") || strings.HasPrefix(r.URL.Path, "/asset-body") {
			w.WriteHeader(200)
			w.(http.Flusher).Flush()
		}
		ready := r.Header.Get("X-Ready")
		if ready == "" {
			panic("missing readiness path")
		}
		if err := os.WriteFile(ready, []byte("ready"), 0600); err != nil {
			panic(err)
		}
		<-r.Context().Done()
	}))
	// Match the existing request oracle: httptest's legacy certificate can be
	// rejected by Rust's verifier. Generate an ephemeral Ed25519 test identity;
	// production certificate verification stays fully enabled.
	public, private, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		panic(err)
	}
	template := x509.Certificate{
		SerialNumber: big.NewInt(1),
		NotBefore:    time.Date(2020, 1, 1, 0, 0, 0, 0, time.UTC),
		NotAfter:     time.Date(2040, 1, 1, 0, 0, 0, 0, time.UTC),
		KeyUsage:     x509.KeyUsageDigitalSignature,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		IPAddresses:  []net.IP{net.IPv4(127, 0, 0, 1)},
	}
	der, err := x509.CreateCertificate(rand.Reader, &template, &template, public, private)
	if err != nil {
		panic(err)
	}
	server.TLS = &tls.Config{MinVersion: tls.VersionTLS13, MaxVersion: tls.VersionTLS13, Certificates: []tls.Certificate{{Certificate: [][]byte{der}, PrivateKey: private}}}
	server.StartTLS()
	defer server.Close()
	cert := filepath.Join(os.TempDir(), "oracle-cert.der")
	if err := os.WriteFile(cert, server.TLS.Certificates[0].Certificate[0], 0600); err != nil {
		panic(err)
	}
	if err := json.NewEncoder(os.Stdout).Encode(map[string]string{"url": server.URL, "cert": cert}); err != nil {
		panic(err)
	}
	_, _ = io.Copy(io.Discard, os.Stdin)
}
func main() {
	// Disposable Cosign stand-in for native process-tree cleanup, never a
	// signature-verification oracle or a replacement for real signing evidence.
	if len(os.Args) > 1 && os.Args[1] == "cosign-child" {
		if err := os.WriteFile(os.Getenv("UPDATE_CANCEL_VERIFIER_READY"), []byte(fmt.Sprint(os.Getpid())), 0600); err != nil {
			panic(err)
		}
		for {
			time.Sleep(time.Second)
		}
	}
	if len(os.Args) > 1 && os.Args[1] == "verify-blob" && os.Getenv("UPDATE_CANCEL_VERIFIER_READY") != "" {
		self, err := os.Executable()
		if err != nil {
			panic(err)
		}
		child := exec.Command(self, "cosign-child")
		if err := child.Start(); err != nil {
			panic(err)
		}
		_ = child.Wait()
		return
	}
	if len(os.Args) > 1 && os.Args[1] == "serve" {
		serve()
		return
	}

	root, err := os.MkdirTemp("", "update-cancellation-")
	if err != nil {
		panic(err)
	}
	defer os.RemoveAll(root)
	var out []observation
	for _, op := range []string{"checker", "signature", "certificate", "applier"} {
		for _, phase := range []string{"pre", "metadata", "body", "asset-body"} {
			if phase == "asset-body" && op != "applier" {
				continue
			}
			ctx, cancel := context.WithCancel(context.Background())
			ready := make(chan struct{})
			if phase == "pre" {
				cancel()
			}
			client := &http.Client{Transport: transport(func(r *http.Request) (*http.Response, error) {
				if phase == "asset-body" && strings.HasSuffix(r.URL.Path, "/checksums") {
					body := fmt.Sprintf("%x  tool_linux_amd64\n", sha256.Sum256([]byte("new")))
					return &http.Response{StatusCode: 200, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(body))}, nil
				}
				if phase == "metadata" {
					close(ready)
					<-r.Context().Done()
					return nil, r.Context().Err()
				}
				if phase == "pre" {
					return nil, r.Context().Err()
				}
				return &http.Response{StatusCode: 200, Header: make(http.Header), Body: &cancelBody{ctx: r.Context(), ready: ready}}, nil
			})}
			cache := filepath.Join(root, op+phase+".json")
			target := filepath.Join(root, op+phase+"-tool")
			if err := os.WriteFile(target, []byte("old"), 0700); err != nil {
				panic(err)
			}
			done := make(chan error, 1)
			go func() {
				switch op {
				case "checker":
					c := updatecheck.NewChecker("owner", "repo")
					c.HTTPClient = client
					c.LatestReleaseURL = "https://controlled.invalid/latest"
					c.CachePath = cache
					_, err := c.Check(ctx, "1.0.0")
					done <- err
				case "signature", "certificate":
					c := cosign.Config{Repo: "owner/repo", BinaryName: "tool", HTTPClient: client}
					var err error
					if op == "signature" {
						_, err = c.FetchSignature(ctx, "1.0.1")
					} else {
						_, err = c.FetchCertificate(ctx, "1.0.1")
					}
					done <- err
				case "applier":
					a := updateapply.NewApplier()
					a.HTTPClient = client
					a.GOOS = "linux"
					a.GOARCH = "amd64"
					done <- a.Apply(ctx, &updatecheck.Release{TagName: "v1.0.1", Assets: []updatecheck.Asset{{Name: "tool_linux_amd64", BrowserDownloadURL: "https://controlled.invalid/asset"}, {Name: "checksums.txt", BrowserDownloadURL: "https://controlled.invalid/checksums"}}}, target)
				}
			}()
			if phase != "pre" {
				<-ready
				cancel()
			}
			err := <-done
			cancel()
			_, cacheErr := os.Stat(cache)
			data, readErr := os.ReadFile(target)
			if readErr != nil {
				panic(readErr)
			}
			entries, directoryErr := os.ReadDir(root)
			if directoryErr != nil {
				panic(directoryErr)
			}
			residue := false
			for _, entry := range entries {
				if strings.HasPrefix(entry.Name(), "updateapply") {
					residue = true
				}
			}
			out = append(out, observation{ID: op + "-" + phase, Cancelled: errors.Is(err, context.Canceled), Cache: cacheErr == nil, Target: string(data), Residue: residue})
		}
	}
	_, err = installmethod.Detect("")
	out = append(out, observation{ID: "empty-path", Message: err.Error(), Identity: errors.Is(err, installmethod.ErrEmptyBinaryPath)})
	client := &http.Client{Transport: transport(func(r *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader("injected")), Header: make(http.Header)}, nil
	})}
	cfg := cosign.Config{Repo: "owner/repo", BinaryName: "tool", HTTPClient: client}
	body, err := cfg.FetchSignature(context.Background(), "1.0.1")
	if err != nil {
		panic(err)
	}
	out = append(out, observation{ID: "injected-client", Body: string(body)}, observation{ID: "issuer", Body: cosign.OIDCIssuer})
	if err := json.NewEncoder(os.Stdout).Encode(out); err != nil {
		panic(err)
	}
}
