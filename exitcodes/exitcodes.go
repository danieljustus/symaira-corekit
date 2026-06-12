// Package exitcodes provides standardized CLI exit codes and structured error types for the Symaira ecosystem.
package exitcodes

import (
	"errors"
	"fmt"
)

// ExitCode represents a process exit code for CLI commands.
//
// The exit codes follow a convention inspired by sysexits.h but adapted for
// the Symaira ecosystem. New categories MUST be added at the end of the block
// to preserve backward compatibility with scripts that match on numeric codes.
type ExitCode uint8

const (
	// ExitOK indicates successful completion.
	ExitOK ExitCode = 0
	// ExitGeneric indicates a general or unspecified error.
	ExitGeneric ExitCode = 1
	// ExitNoInput indicates that input was missing or required but not provided.
	ExitNoInput ExitCode = 2
	// ExitNoAuth indicates an authentication failure (bad credentials, missing token).
	ExitNoAuth ExitCode = 3
	// ExitForbidden indicates the operation was permitted but not allowed
	// (insufficient permissions).
	ExitForbidden ExitCode = 4
	// ExitNotFound indicates the requested resource was not found.
	ExitNotFound ExitCode = 5
	// ExitConflict indicates a conflict with the current state (e.g. resource
	// already exists or version mismatch).
	ExitConflict ExitCode = 6
	// ExitSoftware indicates an internal software error (bug).
	ExitSoftware ExitCode = 7
	// ExitData indicates an error in the data format or content.
	ExitData ExitCode = 8
	// ExitConfig indicates a configuration error.
	ExitConfig ExitCode = 9
	// ExitInterrupted indicates the operation was interrupted.
	ExitInterrupted ExitCode = 10
)

// ErrorKind categorizes CLI errors for programmatic handling and display.
type ErrorKind string

const (
	// KindNotFound indicates the resource was not found.
	KindNotFound ErrorKind = "not_found"
	// KindAuth indicates an authentication error.
	KindAuth ErrorKind = "auth"
	// KindPermission indicates a permission/authorization error.
	KindPermission ErrorKind = "permission"
	// KindValidation indicates an input validation error.
	KindValidation ErrorKind = "validation"
	// KindConfig indicates a configuration error.
	KindConfig ErrorKind = "config"
	// KindConflict indicates a state conflict.
	KindConflict ErrorKind = "conflict"
	// KindInternal indicates an internal error.
	KindInternal ErrorKind = "internal"
	// KindUnavailable indicates the resource or service is unavailable.
	KindUnavailable ErrorKind = "unavailable"
)

// CLIError is a structured error with an exit code, kind classification,
// user-friendly message, optional wrapped cause, and optional remediation hint.
type CLIError struct {
	Code    ExitCode
	Kind    ErrorKind
	Message string
	Cause   error
	Hint    string
}

// Error implements the error interface.
func (e *CLIError) Error() string {
	if e.Cause != nil {
		return fmt.Sprintf("%s: %v", e.Message, e.Cause)
	}
	return e.Message
}

// Unwrap returns the underlying cause for errors.Is/errors.As support.
func (e *CLIError) Unwrap() error {
	return e.Cause
}

// Wrap creates a new CLIError wrapping the given cause with a message string.
func Wrap(err error, code ExitCode, kind ErrorKind, msg string) *CLIError {
	return &CLIError{
		Code:    code,
		Kind:    kind,
		Message: msg,
		Cause:   err,
	}
}

// Wrapf creates a new CLIError wrapping the given cause with a formatted message.
func Wrapf(err error, code ExitCode, kind ErrorKind, format string, args ...any) *CLIError {
	return &CLIError{
		Code:    code,
		Kind:    kind,
		Message: fmt.Sprintf(format, args...),
		Cause:   err,
	}
}

// ExitCodeFromError extracts the exit code from an error.
// If err is nil, it returns ExitOK.
// If err wraps a *CLIError, it returns that error's code.
// Otherwise it returns ExitGeneric.
func ExitCodeFromError(err error) ExitCode {
	if err == nil {
		return ExitOK
	}
	var cliErr *CLIError
	if errors.As(err, &cliErr) {
		return cliErr.Code
	}
	return ExitGeneric
}

// FormatCLIError formats an error for human-readable CLI output.
// If the error is a *CLIError with a non-empty Hint, the hint is appended
// on a separate line prefixed with "Hint: ".
// If the error has a Cause, the full chain is shown.
// If the error is not a *CLIError, the default error string is returned.
func FormatCLIError(err error) string {
	if err == nil {
		return ""
	}
	var cliErr *CLIError
	if !errors.As(err, &cliErr) {
		return err.Error()
	}

	msg := cliErr.Error()
	if cliErr.Hint != "" {
		return fmt.Sprintf("%s\nHint: %s", msg, cliErr.Hint)
	}
	return msg
}
