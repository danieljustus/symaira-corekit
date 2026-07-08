package evidencekit

import (
	"bytes"
	"reflect"
	"strings"
	"testing"
)

func TestAlignExact(t *testing.T) {
	source := "The invoice was paid on 2026-07-01 by wire transfer."
	span, ok := AlignExact(source, "paid on 2026-07-01")
	if !ok {
		t.Fatal("expected exact match")
	}
	want := Span{Start: strings.Index(source, "paid on 2026-07-01"), End: strings.Index(source, "paid on 2026-07-01") + len("paid on 2026-07-01")}
	if span != want {
		t.Errorf("got %+v, want %+v", span, want)
	}
	if source[span.Start:span.End] != "paid on 2026-07-01" {
		t.Errorf("span does not round-trip to evidence text: %q", source[span.Start:span.End])
	}
}

func TestAlignExactNoMatch(t *testing.T) {
	if _, ok := AlignExact("The invoice was paid.", "never happened"); ok {
		t.Error("expected no match")
	}
	if _, ok := AlignExact("anything", ""); ok {
		t.Error("expected empty evidence text to never match")
	}
}

func TestAlignNormalizedWhitespaceCollapse(t *testing.T) {
	source := "Line one.\n  Line   two continues\n\there."
	evidence := "Line two continues here."
	span, status := Align(source, evidence)
	if status != AlignmentNormalized {
		t.Fatalf("expected normalized alignment, got %s", status)
	}
	got := source[span.Start:span.End]
	gotNorm, _ := normalizeWithMap(got)
	wantNorm, _ := normalizeWithMap(evidence)
	if gotNorm != wantNorm {
		t.Errorf("normalized span text = %q, want %q (raw span %q)", gotNorm, wantNorm, got)
	}
}

func TestAlignPrefersExactOverNormalized(t *testing.T) {
	source := "exact match here, and also   here with   extra spaces"
	span, status := Align(source, "exact match here")
	if status != AlignmentExact {
		t.Fatalf("expected exact alignment, got %s", status)
	}
	if source[span.Start:span.End] != "exact match here" {
		t.Errorf("unexpected span text %q", source[span.Start:span.End])
	}
}

func TestAlignUnmatched(t *testing.T) {
	span, status := Align("The invoice was paid.", "this text is nowhere in the source")
	if status != AlignmentUnmatched {
		t.Fatalf("expected unmatched, got %s", status)
	}
	if span != (Span{}) {
		t.Errorf("expected zero span for unmatched, got %+v", span)
	}
}

func TestAlignNormalizedNoMatch(t *testing.T) {
	if _, ok := AlignNormalized("some source text", "text that is not present"); ok {
		t.Error("expected no normalized match")
	}
	if _, ok := AlignNormalized("some source text", "   "); ok {
		t.Error("expected blank evidence text to never match")
	}
}

func TestAlignNormalizedUnicodeOffsets(t *testing.T) {
	source := "café notes:\n  décision   validée hier"
	evidence := "décision validée hier"
	span, ok := AlignNormalized(source, evidence)
	if !ok {
		t.Fatal("expected normalized match with multi-byte runes")
	}
	got := source[span.Start:span.End]
	gotNorm, _ := normalizeWithMap(got)
	if gotNorm != evidence {
		t.Errorf("normalized span text = %q, want %q (raw span %q)", gotNorm, evidence, got)
	}
}

func TestValidateRejectsUnmatched(t *testing.T) {
	e := Extraction{
		EvidenceText:    "something",
		Span:            Span{Start: 0, End: 5},
		AlignmentStatus: AlignmentUnmatched,
	}
	if err := Validate(e); err == nil {
		t.Error("expected error for unmatched extraction")
	}
}

func TestValidateRejectsInvalidSpan(t *testing.T) {
	e := Extraction{
		EvidenceText:    "something",
		Span:            Span{Start: 10, End: 3},
		AlignmentStatus: AlignmentExact,
	}
	if err := Validate(e); err == nil {
		t.Error("expected error for invalid span bounds")
	}
}

func TestValidateRejectsEmptyEvidence(t *testing.T) {
	e := Extraction{
		EvidenceText:    "",
		Span:            Span{Start: 0, End: 0},
		AlignmentStatus: AlignmentExact,
	}
	if err := Validate(e); err == nil {
		t.Error("expected error for empty evidence text")
	}
}

func TestValidateAcceptsGrounded(t *testing.T) {
	e := Extraction{
		EvidenceText:    "paid on 2026-07-01",
		Span:            Span{Start: 16, End: 35},
		AlignmentStatus: AlignmentExact,
	}
	if err := Validate(e); err != nil {
		t.Errorf("expected valid extraction, got error: %v", err)
	}
}

func TestJSONLRoundTrip(t *testing.T) {
	want := []Extraction{
		{
			Source:          SourceRef{ID: "session-1", Kind: "chat"},
			Text:            "user prefers dark mode",
			EvidenceText:    "I always use dark mode",
			Span:            Span{Start: 12, End: 35},
			AlignmentStatus: AlignmentExact,
			Attributes:      map[string]string{"scope": "global"},
		},
		{
			Source:          SourceRef{ID: "doc-42"},
			Text:            "deploy freeze after Thursday",
			EvidenceText:    "we freeze  deploys   after Thursday",
			Span:            Span{Start: 0, End: 36},
			AlignmentStatus: AlignmentNormalized,
		},
	}

	var buf bytes.Buffer
	if err := EncodeJSONL(&buf, want); err != nil {
		t.Fatalf("encode: %v", err)
	}

	lineCount := strings.Count(buf.String(), "\n")
	if lineCount != len(want) {
		t.Fatalf("expected %d lines, got %d: %q", len(want), lineCount, buf.String())
	}

	got, err := DecodeJSONL(&buf)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(got) != len(want) {
		t.Fatalf("got %d extractions, want %d", len(got), len(want))
	}
	for i := range want {
		if !reflect.DeepEqual(got[i], want[i]) {
			t.Errorf("extraction %d: got %+v, want %+v", i, got[i], want[i])
		}
	}
}

func TestJSONLDecodeSkipsBlankLines(t *testing.T) {
	input := `{"source":{"id":"a"},"text":"t","evidence_text":"e","span":{"char_start":0,"char_end":1},"alignment_status":"exact"}

{"source":{"id":"b"},"text":"t2","evidence_text":"e2","span":{"char_start":0,"char_end":2},"alignment_status":"exact"}
`
	got, err := DecodeJSONL(strings.NewReader(input))
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(got) != 2 {
		t.Fatalf("got %d extractions, want 2", len(got))
	}
}

func TestJSONLDecodeRejectsInvalidJSON(t *testing.T) {
	if _, err := DecodeJSONL(strings.NewReader("{not valid json")); err == nil {
		t.Error("expected error decoding invalid JSON line")
	}
}

func TestExtractionFieldNamesAreTheContract(t *testing.T) {
	e := Extraction{
		Source:          SourceRef{ID: "s1", Kind: "session"},
		Text:            "fact",
		EvidenceText:    "evidence",
		Span:            Span{Start: 1, End: 2},
		AlignmentStatus: AlignmentExact,
	}
	var buf bytes.Buffer
	if err := EncodeJSONL(&buf, []Extraction{e}); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{`"source"`, `"text"`, `"evidence_text"`, `"span"`, `"alignment_status"`, `"char_start"`, `"char_end"`, `"id"`, `"kind"`} {
		if !strings.Contains(buf.String(), key) {
			t.Errorf("missing contract field %s in %s", key, buf.String())
		}
	}
}
