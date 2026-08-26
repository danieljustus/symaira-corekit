package llmkit

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

// DefaultTimeout is the default per-request timeout.
const DefaultTimeout = 2 * time.Minute

// Client is an HTTP client for one provider descriptor. It is safe for
// concurrent use once constructed.
type Client struct {
	desc     Descriptor
	baseURL  string
	dialect  WireDialect
	apiKey   string
	extraHdr map[string]string
	http     *http.Client
}

// Option configures a Client at construction time.
type Option func(*clientConfig)

type clientConfig struct {
	baseURL    string
	dialect    WireDialect
	timeout    time.Duration
	httpClient *http.Client
}

// WithBaseURL overrides the descriptor's default endpoint (only valid when
// the descriptor declares base_url_overridable or requires an override).
func WithBaseURL(u string) Option {
	return func(c *clientConfig) { c.baseURL = u }
}

// WithDialect overrides the wire dialect (custom endpoints only).
func WithDialect(d WireDialect) Option {
	return func(c *clientConfig) { c.dialect = d }
}

// WithTimeout sets the per-request timeout.
func WithTimeout(d time.Duration) Option {
	return func(c *clientConfig) { c.timeout = d }
}

// WithHTTPClient supplies a custom *http.Client (tests, transports).
func WithHTTPClient(h *http.Client) Option {
	return func(c *clientConfig) { c.httpClient = h }
}

// NewClient builds a Client for desc. The credential is resolved through the
// shared reference format: symvault://, keychain://, env://NAME, or a bare
// environment-variable name. Descriptors with auth scheme "none" skip
// resolution entirely.
func NewClient(desc Descriptor, credRef string, opts ...Option) (*Client, error) {
	if err := loadRegistry(); err != nil {
		return nil, err
	}
	if err := desc.Validate(); err != nil {
		return nil, err
	}
	cfg := clientConfig{
		baseURL: desc.BaseURL,
		dialect: desc.Dialect,
		timeout: DefaultTimeout,
	}
	for _, opt := range opts {
		opt(&cfg)
	}
	if cfg.baseURL == "" && desc.BaseURLRequiredOverride {
		return nil, fmt.Errorf("llmkit: provider %q requires a base URL override (WithBaseURL)", desc.ID)
	}
	if cfg.baseURL != "" && !desc.BaseURLOverridable && !desc.BaseURLRequiredOverride {
		return nil, fmt.Errorf("llmkit: provider %q does not allow base URL overrides", desc.ID)
	}
	cfg.baseURL = strings.TrimRight(cfg.baseURL, "/")

	key := ""
	if desc.AuthScheme != AuthNone {
		var err error
		key, err = ResolveCredential(credRef, desc.CredentialEnvDefault)
		if err != nil {
			return nil, err
		}
	}

	hc := cfg.httpClient
	if hc == nil {
		hc = &http.Client{
			Timeout: cfg.timeout,
			// A redirect from a configured endpoint is either a misconfigured
			// host or a hostile one. Never follow it silently.
			CheckRedirect: func(req *http.Request, via []*http.Request) error {
				return http.ErrUseLastResponse
			},
		}
	}

	extra := make(map[string]string, len(desc.ExtraHeaders))
	for k, v := range desc.ExtraHeaders {
		extra[k] = v
	}

	return &Client{
		desc:     desc,
		baseURL:  cfg.baseURL,
		dialect:  cfg.dialect,
		apiKey:   key,
		extraHdr: extra,
		http:     hc,
	}, nil
}

// Descriptor returns the provider descriptor this client was built from.
func (c *Client) Descriptor() Descriptor { return c.desc }

// BaseURL returns the resolved base URL.
func (c *Client) BaseURL() string { return c.baseURL }

// do performs one classified round trip against path with the given JSON
// body. On a non-2xx response it returns a *Error.
func (c *Client) do(ctx context.Context, method, path string, body any, contentType string) (*http.Response, error) {
	u, err := url.JoinPath(c.baseURL, path)
	if err != nil {
		return nil, &Error{Code: ErrCodeProvider, Err: fmt.Errorf("build url: %w", err)}
	}
	var rd io.Reader
	if body != nil {
		buf, err := json.Marshal(body)
		if err != nil {
			return nil, &Error{Code: ErrCodeProvider, Err: fmt.Errorf("encode request: %w", err)}
		}
		rd = strings.NewReader(string(buf))
	}
	req, err := http.NewRequestWithContext(ctx, method, u, rd)
	if err != nil {
		return nil, &Error{Code: ErrCodeProvider, Err: fmt.Errorf("build request: %w", err)}
	}
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", contentType)
	}
	c.applyAuth(req)

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, errTransport(err)
	}
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 8<<10))
		resp.Body.Close()
		e := classify(resp.StatusCode, string(b))
		if ra := resp.Header.Get("Retry-After"); ra != "" {
			e.RetryAfter = ra
		}
		return nil, e
	}
	return resp, nil
}

// applyAuth writes the credential and mandatory headers onto the request.
func (c *Client) applyAuth(req *http.Request) {
	switch c.desc.AuthScheme {
	case AuthBearer:
		req.Header.Set("Authorization", "Bearer "+c.apiKey)
	case AuthHeader:
		name := c.desc.AuthHeader
		if name == "" {
			name = "Authorization"
		}
		req.Header.Set(name, c.apiKey)
	}
	for k, v := range c.extraHdr {
		req.Header.Set(k, v)
	}
}

// ResolveCredential resolves a credential reference in the shared format:
//
//	symvault://path  -> `symvault get path --print`
//	keychain://svc/acct -> reserved for Swift consumers; unsupported here
//	env://NAME       -> os.Getenv("NAME")
//	NAME             -> bare env name shorthand for env://NAME
//
// An empty ref falls back to envDefault (a bare env name). The resolved value
// must never be logged; errors name only the reference.
func ResolveCredential(ref, envDefault string) (string, error) {
	target := ref
	if target == "" {
		target = envDefault
	}
	if target == "" {
		return "", &Error{Code: ErrCodeAuth, Err: fmt.Errorf("no credential reference or default provided")}
	}
	switch {
	case strings.HasPrefix(target, "symvault://"):
		path := strings.TrimPrefix(target, "symvault://")
		out, err := resolveSymvault(path)
		if err != nil {
			return "", &Error{Code: ErrCodeAuth, Err: fmt.Errorf("resolve %s: %w", refLabel(ref), err)}
		}
		return out, nil
	case strings.HasPrefix(target, "keychain://"):
		return "", &Error{Code: ErrCodeAuth, Err: fmt.Errorf("keychain:// references are resolved by the Swift half (SymairaProviderKit), not by llmkit")}
	case strings.HasPrefix(target, "env://"):
		name := strings.TrimPrefix(target, "env://")
		v := os.Getenv(name)
		if v == "" {
			return "", &Error{Code: ErrCodeAuth, Err: fmt.Errorf("environment variable %s is not set (reference %s)", name, refLabel(ref))}
		}
		return v, nil
	default:
		v := os.Getenv(target)
		if v == "" {
			return "", &Error{Code: ErrCodeAuth, Err: fmt.Errorf("environment variable %s is not set (reference %s)", target, refLabel(ref))}
		}
		return v, nil
	}
}

// refLabel keeps error messages pointing at the reference the user
// configured, never at any resolved value.
func refLabel(ref string) string {
	if ref == "" {
		return "<default>"
	}
	return ref
}

// resolveSymvault shells out to the vault CLI. Kept as a small indirection so
// tests can replace it.
var resolveSymvault = func(path string) (string, error) {
	cmd := execCommand("symvault", "get", path, "--print")
	out, err := cmd.Output()
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(out)), nil
}

// retryAfterSeconds parses the Retry-After header value (seconds form); ok is
// false when absent or unparseable.
func retryAfterSeconds(v string) (int, bool) {
	if v == "" {
		return 0, false
	}
	n, err := strconv.Atoi(v)
	if err != nil || n < 0 {
		return 0, false
	}
	return n, true
}
