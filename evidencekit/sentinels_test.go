package evidencekit

import (
	"errors"
	"testing"
)

// Issue #38: Validate errors must wrap exported sentinels so callers can
// errors.Is()-branch, while message text stays unchanged.

func TestValidateSentinelUnmatched(t *testing.T) {
	e := Extraction{
		EvidenceText:    "something",
		Span:            Span{Start: 0, End: 5},
		AlignmentStatus: AlignmentUnmatched,
	}
	err := Validate(e)
	if err == nil {
		t.Fatal("expected error")
	}
	if !errors.Is(err, ErrUnmatched) {
		t.Errorf("expected errors.Is(err, ErrUnmatched), got %v", err)
	}
	if err.Error() != "evidencekit: extraction is unmatched, not grounded" {
		t.Errorf("message text changed: %q", err.Error())
	}
}

func TestValidateSentinelEmptyEvidence(t *testing.T) {
	e := Extraction{
		EvidenceText:    "",
		Span:            Span{Start: 0, End: 0},
		AlignmentStatus: AlignmentExact,
	}
	err := Validate(e)
	if err == nil {
		t.Fatal("expected error")
	}
	if !errors.Is(err, ErrEmptyEvidence) {
		t.Errorf("expected errors.Is(err, ErrEmptyEvidence), got %v", err)
	}
	if err.Error() != "evidencekit: empty evidence text" {
		t.Errorf("message text changed: %q", err.Error())
	}
}

func TestValidateSentinelInvalidSpan(t *testing.T) {
	e := Extraction{
		EvidenceText:    "something",
		Span:            Span{Start: 10, End: 3},
		AlignmentStatus: AlignmentExact,
	}
	err := Validate(e)
	if err == nil {
		t.Fatal("expected error")
	}
	if !errors.Is(err, ErrInvalidSpan) {
		t.Errorf("expected errors.Is(err, ErrInvalidSpan), got %v", err)
	}
	if err.Error() != "evidencekit: invalid span [10,3)" {
		t.Errorf("message text changed: %q", err.Error())
	}
}
