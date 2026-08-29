package ollamakit

import (
	"errors"
	"testing"
)

func TestCompatibilityErrorPreservesCause(t *testing.T) {
	cause := errors.New("cause")
	err := &Error{Message: "request failed", Err: cause}
	if got := err.Error(); got != "request failed: cause" {
		t.Fatalf("Error() = %q", got)
	}
	if !errors.Is(err, cause) {
		t.Fatal("compatibility error did not preserve its cause")
	}
	if got := (&Error{Message: "message only"}).Error(); got != "message only" {
		t.Fatalf("message-only Error() = %q", got)
	}
	if got := (&Error{Err: cause}).Error(); got != "cause" {
		t.Fatalf("cause-only Error() = %q", got)
	}
	responseErr := &ResponseError{StatusCode: 503, Body: "busy"}
	if got := responseErr.Error(); got != "ollamakit: unexpected response: status 503: busy" {
		t.Fatalf("ResponseError.Error() = %q", got)
	}
	if !errors.Is(responseErr, ErrResponse) {
		t.Fatal("response error did not unwrap to ErrResponse")
	}
}
