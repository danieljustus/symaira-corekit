package exitcodes

import (
	"errors"
	"strings"
	"testing"
)

func TestCLIError_Error_NoCause(t *testing.T) {
	e := &CLIError{Code: ExitGeneric, Kind: KindInternal, Message: "something broke"}
	got := e.Error()
	if got != "something broke" {
		t.Errorf("Error() = %q, want %q", got, "something broke")
	}
}

func TestCLIError_Error_WithCause(t *testing.T) {
	cause := errors.New("underlying issue")
	e := &CLIError{Code: ExitGeneric, Kind: KindInternal, Message: "operation failed", Cause: cause}
	got := e.Error()
	want := "operation failed: underlying issue"
	if got != want {
		t.Errorf("Error() = %q, want %q", got, want)
	}
}

func TestCLIError_Error_WithCLICause(t *testing.T) {
	inner := &CLIError{Code: ExitNotFound, Kind: KindNotFound, Message: "entry missing"}
	outer := &CLIError{Code: ExitGeneric, Kind: KindInternal, Message: "read failed", Cause: inner}
	got := outer.Error()
	if !strings.Contains(got, "read failed:") {
		t.Errorf("Error() = %q, should contain outer message", got)
	}
	if !strings.Contains(got, "entry missing") {
		t.Errorf("Error() = %q, should contain inner message", got)
	}
}

func TestCLIError_Unwrap(t *testing.T) {
	cause := errors.New("root cause")
	e := &CLIError{Code: ExitGeneric, Cause: cause}
	if e.Unwrap() != cause {
		t.Error("Unwrap() did not return the cause")
	}
}

func TestCLIError_Unwrap_Nil(t *testing.T) {
	e := &CLIError{Code: ExitGeneric}
	if e.Unwrap() != nil {
		t.Error("Unwrap() should return nil when no cause")
	}
}

func TestCLIError_Unwrap_Chain(t *testing.T) {
	inner := errors.New("inner")
	outer := &CLIError{Code: ExitGeneric, Cause: inner}
	if !errors.Is(outer, inner) {
		t.Error("errors.Is should find inner error through CLIError chain")
	}
}

func TestExitCodeFromError_Nil(t *testing.T) {
	if got := ExitCodeFromError(nil); got != ExitOK {
		t.Errorf("ExitCodeFromError(nil) = %d, want %d", got, ExitOK)
	}
}

func TestExitCodeFromError_CLIError(t *testing.T) {
	e := &CLIError{Code: ExitNotFound, Kind: KindNotFound, Message: "missing"}
	if got := ExitCodeFromError(e); got != ExitNotFound {
		t.Errorf("ExitCodeFromError(CLIError{ExitNotFound}) = %d, want %d", got, ExitNotFound)
	}
}

func TestExitCodeFromError_WrappedCLIError(t *testing.T) {
	inner := &CLIError{Code: ExitNoAuth, Kind: KindAuth, Message: "bad token"}
	outer := errors.New("wrapped").Error()
	_ = outer
	err := Wrap(inner, ExitGeneric, KindInternal, "operation failed")
	if got := ExitCodeFromError(err); got != ExitGeneric {
		t.Errorf("ExitCodeFromError(Wrap(CLIError)) = %d, want %d", got, ExitGeneric)
	}
}

func TestExitCodeFromError_PlainError(t *testing.T) {
	err := errors.New("generic problem")
	if got := ExitCodeFromError(err); got != ExitGeneric {
		t.Errorf("ExitCodeFromError(plain error) = %d, want %d", got, ExitGeneric)
	}
}

func TestExitCodeFromError_AllCodes(t *testing.T) {
	codes := []ExitCode{
		ExitOK, ExitGeneric, ExitNoInput, ExitNoAuth,
		ExitForbidden, ExitNotFound, ExitConflict, ExitSoftware,
		ExitData, ExitConfig, ExitInterrupted,
	}
	for _, code := range codes {
		e := &CLIError{Code: code, Message: "test"}
		got := ExitCodeFromError(e)
		if got != code {
			t.Errorf("ExitCodeFromError(Code=%d) = %d", code, got)
		}
	}
}

func TestWrap(t *testing.T) {
	cause := errors.New("cause")
	e := Wrap(cause, ExitNoAuth, KindAuth, "auth failed")
	if e.Code != ExitNoAuth {
		t.Errorf("Code = %d, want %d", e.Code, ExitNoAuth)
	}
	if e.Kind != KindAuth {
		t.Errorf("Kind = %q, want %q", e.Kind, KindAuth)
	}
	if e.Message != "auth failed" {
		t.Errorf("Message = %q, want %q", e.Message, "auth failed")
	}
	if e.Cause != cause {
		t.Error("Cause not preserved")
	}
}

func TestWrapf(t *testing.T) {
	cause := errors.New("disk error")
	e := Wrapf(cause, ExitData, KindValidation, "field %q is invalid: %d issues", "name", 3)
	if e.Code != ExitData {
		t.Errorf("Code = %d, want %d", e.Code, ExitData)
	}
	if e.Kind != KindValidation {
		t.Errorf("Kind = %q, want %q", e.Kind, KindValidation)
	}
	want := `field "name" is invalid: 3 issues`
	if e.Message != want {
		t.Errorf("Message = %q, want %q", e.Message, want)
	}
	if e.Cause != cause {
		t.Error("Cause not preserved")
	}
}

func TestFormatCLIError_PlainError(t *testing.T) {
	err := errors.New("simple error")
	got := FormatCLIError(err)
	if got != "simple error" {
		t.Errorf("FormatCLIError(plain) = %q, want %q", got, "simple error")
	}
}

func TestFormatCLIError_Nil(t *testing.T) {
	got := FormatCLIError(nil)
	if got != "" {
		t.Errorf("FormatCLIError(nil) = %q, want empty", got)
	}
}

func TestFormatCLIError_WithHint(t *testing.T) {
	e := &CLIError{
		Code:    ExitNotFound,
		Kind:    KindNotFound,
		Message: "entry not found",
		Hint:    "symvault list to browse entries",
	}
	got := FormatCLIError(e)
	if !strings.Contains(got, "entry not found") {
		t.Errorf("missing message in output: %q", got)
	}
	if !strings.Contains(got, "Hint: symvault list to browse entries") {
		t.Errorf("missing hint in output: %q", got)
	}
}

func TestFormatCLIError_WithCause(t *testing.T) {
	cause := errors.New("underlying")
	e := &CLIError{
		Code:    ExitGeneric,
		Kind:    KindInternal,
		Message: "failed",
		Cause:   cause,
	}
	got := FormatCLIError(e)
	want := "failed: underlying"
	if got != want {
		t.Errorf("FormatCLIError = %q, want %q", got, want)
	}
}

func TestFormatCLIError_WithCauseAndHint(t *testing.T) {
	cause := errors.New("underlying")
	e := &CLIError{
		Code:    ExitGeneric,
		Kind:    KindInternal,
		Message: "failed",
		Cause:   cause,
		Hint:    "check logs",
	}
	got := FormatCLIError(e)
	if !strings.Contains(got, "failed: underlying") {
		t.Errorf("missing cause chain: %q", got)
	}
	if !strings.Contains(got, "Hint: check logs") {
		t.Errorf("missing hint: %q", got)
	}
}

func TestFormatCLIError_NoHint(t *testing.T) {
	e := &CLIError{Code: ExitGeneric, Message: "error"}
	got := FormatCLIError(e)
	if strings.Contains(got, "Hint:") {
		t.Errorf("should not contain Hint when empty: %q", got)
	}
}

func TestExitCodeValues(t *testing.T) {
	if ExitOK != 0 {
		t.Errorf("ExitOK = %d, want 0", ExitOK)
	}
	if ExitGeneric != 1 {
		t.Errorf("ExitGeneric = %d, want 1", ExitGeneric)
	}
	if ExitInterrupted != 10 {
		t.Errorf("ExitInterrupted = %d, want 10", ExitInterrupted)
	}
}

func TestErrorKindValues(t *testing.T) {
	kinds := map[ErrorKind]string{
		KindNotFound:    "not_found",
		KindAuth:        "auth",
		KindPermission:  "permission",
		KindValidation:  "validation",
		KindConfig:      "config",
		KindConflict:    "conflict",
		KindInternal:    "internal",
		KindUnavailable: "unavailable",
	}
	for kind, want := range kinds {
		if string(kind) != want {
			t.Errorf("ErrorKind %v = %q, want %q", kind, string(kind), want)
		}
	}
}

func TestExitCodeType_IsUint8(t *testing.T) {
	var code ExitCode
	if code != 0 {
		t.Error("zero value of ExitCode should be 0")
	}
	code = 255
	if code != 255 {
		t.Error("ExitCode should hold uint8 values")
	}
}
