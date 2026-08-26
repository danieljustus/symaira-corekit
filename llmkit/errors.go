package llmkit

import (
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/danieljustus/symaira-corekit/exitcodes"
)

// ErrorCode is the contract error taxonomy from
// contracts/llm_errors.json. Callers branch on these codes instead of
// string-matching provider-specific error text.
type ErrorCode string

const (
	// ErrCodeAuth means the credential is missing, invalid or expired.
	ErrCodeAuth ErrorCode = "auth_failure"
	// ErrCodeRateLimited means the provider rejected the request for rate
	// limiting; RetryAfter may carry the reported delay.
	ErrCodeRateLimited ErrorCode = "rate_limited"
	// ErrCodeContextOverflow means the prompt exceeds the context window.
	ErrCodeContextOverflow ErrorCode = "context_overflow"
	// ErrCodeModelNotFound means the model/deployment does not exist for
	// this credential.
	ErrCodeModelNotFound ErrorCode = "model_not_found"
	// ErrCodeTransport means a network-level failure (refused, DNS, TLS,
	// timeout).
	ErrCodeTransport ErrorCode = "transport_error"
	// ErrCodeProvider means any other provider-reported failure.
	ErrCodeProvider ErrorCode = "provider_error"
)

// Error is a classified provider failure. Use errors.As to extract it from a
// call chain; ExitCode maps the failure onto the shared CLI exit-code table.
type Error struct {
	Code       ErrorCode
	StatusCode int    // upstream HTTP status, 0 for transport failures
	Body       string // upstream body excerpt, truncated
	RetryAfter string // provider-reported retry delay, rate-limited only
	Err        error  // underlying transport error, if any
}

func (e *Error) Error() string {
	var b strings.Builder
	fmt.Fprintf(&b, "llmkit: %s", e.Code)
	if e.StatusCode != 0 {
		fmt.Fprintf(&b, " (status %d)", e.StatusCode)
	}
	if e.Body != "" {
		fmt.Fprintf(&b, ": %s", e.Body)
	}
	return b.String()
}

func (e *Error) Unwrap() error { return e.Err }

// ExitCode maps this failure onto the exitcodes table per the contract.
func (e *Error) ExitCode() exitcodes.ExitCode {
	switch e.Code {
	case ErrCodeAuth:
		return exitcodes.ExitNoAuth
	case ErrCodeRateLimited:
		return exitcodes.ExitConflict
	case ErrCodeContextOverflow:
		return exitcodes.ExitData
	case ErrCodeModelNotFound:
		return exitcodes.ExitNotFound
	default:
		return exitcodes.ExitGeneric
	}
}

// Retryable reports whether retrying the same request can plausibly succeed.
func (e *Error) Retryable() bool {
	switch e.Code {
	case ErrCodeRateLimited, ErrCodeTransport:
		return true
	default:
		return false
	}
}

// classify turns an HTTP response into a contract Error. body must already be
// truncated to a sane excerpt.
func classify(status int, body string) *Error {
	code := ErrCodeProvider
	switch {
	case status == http.StatusUnauthorized || status == http.StatusForbidden:
		code = ErrCodeAuth
	case status == http.StatusTooManyRequests:
		code = ErrCodeRateLimited
	case status == http.StatusNotFound:
		code = ErrCodeModelNotFound
	case status == http.StatusBadRequest && isOverflowBody(body):
		code = ErrCodeContextOverflow
	case status >= 500:
		code = ErrCodeProvider
	}
	e := &Error{Code: code, StatusCode: status, Body: truncateBody(body)}
	if code == ErrCodeRateLimited || status == http.StatusTooManyRequests {
		// Callers that need the raw header value can read it off the error;
		// classification itself stays header-free because the taxonomy only
		// promises the field when the provider reports one.
	}
	return e
}

// overflowMarkers are stable substrings providers use to report an exceeded
// context window on HTTP 400.
var overflowMarkers = []string{
	"context_length_exceeded",
	"maximum context length",
	"context window",
	"too many tokens",
	"input length exceeds",
}

func isOverflowBody(body string) bool {
	lower := strings.ToLower(body)
	for _, m := range overflowMarkers {
		if strings.Contains(lower, m) {
			return true
		}
	}
	return false
}

const maxBodyExcerpt = 512

func truncateBody(body string) string {
	body = strings.TrimSpace(body)
	if len(body) <= maxBodyExcerpt {
		return body
	}
	return body[:maxBodyExcerpt]
}

// errTransport wraps a network-level failure as a contract Error.
func errTransport(err error) *Error {
	return &Error{Code: ErrCodeTransport, Err: err}
}

// AsError extracts a *Error from err, or nil when err is not a classified
// provider failure.
func AsError(err error) *Error {
	var e *Error
	if errors.As(err, &e) {
		return e
	}
	return nil
}
