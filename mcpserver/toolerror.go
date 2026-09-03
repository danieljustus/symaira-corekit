package mcpserver

import (
	"errors"

	"github.com/danieljustus/symaira-corekit/exitcodes"
)

// ToolErrorMetaKey is the tool-result "_meta" key under which a failed
// tools/call carries the machine-readable twin of its message.
//
// MCP reports a tool failure as a result with isError: true whose content is
// prose written for the model. Prose is all a caller gets unless the error
// says more about itself, so an agent cannot tell a refused address from a
// mistyped selector from a slow host without parsing English — and a server
// that wants to deliver a code ends up rendering it into the sentence. The
// base MCP Result type carries a free-form "_meta" object (present since
// protocol version 2024-11-05); this key holds the structured fields, and
// the message text stays exactly what the handler produced.
//
// The key is namespaced per the MCP "_meta" naming rule: a reverse-DNS-style
// prefix, a slash, then the name.
const ToolErrorMetaKey = "symaira.dev/tool_error"

// A tool handler's error may implement any of the optional interfaces below.
// Each one contributes a single field to the object stored under
// [ToolErrorMetaKey]:
//
//	ErrorCode() string            → "code"
//	RetryableError() bool         → "retryable"
//	RequiresConfirmation() bool   → "requires_confirmation"
//	ResumeGuidance() string       → "resume_hint"
//	ErrorHint() string            → "hint" (or Hint() string)
//	ErrorDetails() map[string]any → "details"
//
// The method names are the ones consumers already carry their error metadata
// on, so an existing structured error usually satisfies them unchanged. An
// error implementing none of them produces no "_meta" member at all, leaving
// the wire format byte-identical to a server that never adopted this.
//
// Field names are snake_case, per contracts/json_encoding.json: this object
// is a tool-defined payload, not part of the MCP envelope.
type toolErrorCoder interface{ ErrorCode() string }

type toolErrorRetryable interface{ RetryableError() bool }

type toolErrorConfirmer interface{ RequiresConfirmation() bool }

type toolErrorResumer interface{ ResumeGuidance() string }

type toolErrorHinter interface{ ErrorHint() string }

type toolErrorPlainHinter interface{ Hint() string }

type toolErrorDetailer interface{ ErrorDetails() map[string]any }

// ToolErrorData renders the structured metadata an error carries into the
// object published under [ToolErrorMetaKey]. It returns nil when the error
// describes itself no further than its message, which is the signal to omit
// "_meta" entirely.
//
// Every interface is consulted with [errors.As], so a wrapped error still
// reports the metadata of the error underneath. A [exitcodes.CLIError] fills
// in "code" (from its Kind) and "hint" when nothing more specific did.
//
// Boolean fields are reported whenever the error implements their interface,
// including when they are false: "retryable": false is a statement that
// retrying will not help, which is exactly what a caller needs, while an
// absent field only means the error never said.
func ToolErrorData(err error) map[string]any {
	if err == nil {
		return nil
	}
	data := map[string]any{}

	var coder toolErrorCoder
	if errors.As(err, &coder) {
		if code := coder.ErrorCode(); code != "" {
			data["code"] = code
		}
	}
	var retryable toolErrorRetryable
	if errors.As(err, &retryable) {
		data["retryable"] = retryable.RetryableError()
	}
	var confirmer toolErrorConfirmer
	if errors.As(err, &confirmer) {
		data["requires_confirmation"] = confirmer.RequiresConfirmation()
	}
	var resumer toolErrorResumer
	if errors.As(err, &resumer) {
		if guidance := resumer.ResumeGuidance(); guidance != "" {
			data["resume_hint"] = guidance
		}
	}
	if hint := toolErrorHint(err); hint != "" {
		data["hint"] = hint
	}
	var detailer toolErrorDetailer
	if errors.As(err, &detailer) {
		if details := detailer.ErrorDetails(); len(details) > 0 {
			data["details"] = details
		}
	}

	var cliErr *exitcodes.CLIError
	if errors.As(err, &cliErr) {
		if _, ok := data["code"]; !ok && cliErr.Kind != "" {
			data["code"] = string(cliErr.Kind)
		}
		if _, ok := data["hint"]; !ok && cliErr.Hint != "" {
			data["hint"] = cliErr.Hint
		}
	}

	if len(data) == 0 {
		return nil
	}
	// The message is repeated here so a client reading only the metadata
	// object has the whole failure, without re-deriving it from the text
	// content block.
	data["message"] = err.Error()
	return data
}

// toolErrorHint prefers the ErrorHint method over the shorter Hint, matching
// the precedence consumers already use when both are present on one error.
func toolErrorHint(err error) string {
	var hinter toolErrorHinter
	if errors.As(err, &hinter) {
		if hint := hinter.ErrorHint(); hint != "" {
			return hint
		}
	}
	var plain toolErrorPlainHinter
	if errors.As(err, &plain) {
		return plain.Hint()
	}
	return ""
}
