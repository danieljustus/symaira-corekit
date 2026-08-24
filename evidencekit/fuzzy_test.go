//nolint:gosec
package evidencekit

import (
	"math/rand"
	"strings"
	"testing"
	"unicode/utf8"
)

// Issue #37: fuzzy-alignment fallback in Align.

func TestAlignFuzzyRecoversTypoSpan(t *testing.T) {
	source := "The quarterly report shows revenue grew by twelve percent in March despite market headwinds."
	evidence := "revenue grew by twelve precent in March" // typo: precent
	span, status := Align(source, evidence)
	if status != AlignmentFuzzy {
		t.Fatalf("expected fuzzy alignment, got %s", status)
	}
	got := source[span.Start:span.End]
	if !strings.Contains(got, "revenue grew by twelve percent in March") {
		t.Errorf("fuzzy span %q does not cover the planted truth span", got)
	}
}

func TestAlignFuzzyRecoversDroppedToken(t *testing.T) {
	source := "alpha beta gamma delta epsilon zeta eta theta"
	evidence := "gamma delta epsilon zeta theta" // eta dropped
	span, status := Align(source, evidence)
	if status != AlignmentFuzzy {
		t.Fatalf("expected fuzzy alignment, got %s", status)
	}
	got := source[span.Start:span.End]
	if !strings.Contains(got, "gamma delta epsilon") {
		t.Errorf("fuzzy span %q does not cover the planted truth span", got)
	}
}

func TestAlignFuzzyBelowThresholdUnmatched(t *testing.T) {
	source := "The quarterly report shows revenue grew by twelve percent."
	_, status := Align(source, "completely unrelated tokens with no overlap whatsoever")
	if status != AlignmentUnmatched {
		t.Fatalf("expected unmatched below threshold, got %s", status)
	}
}

func TestAlignPrefersExactAndNormalizedOverFuzzy(t *testing.T) {
	source := "exact phrase here\n  and   normalized   phrase here"
	if _, status := Align(source, "exact phrase here"); status != AlignmentExact {
		t.Fatalf("expected exact, got %s", status)
	}
	if _, status := Align(source, "and normalized phrase here"); status != AlignmentNormalized {
		t.Fatalf("expected normalized, got %s", status)
	}
}

func TestValidateRejectsFuzzyByDefault(t *testing.T) {
	e := Extraction{
		EvidenceText:    "revenue grew by twelve precent",
		Span:            Span{Start: 0, End: 10},
		AlignmentStatus: AlignmentFuzzy,
	}
	if err := Validate(e); err == nil {
		t.Error("expected strict Validate to reject fuzzy alignment")
	}
}

func TestValidateWithOptionsAcceptsFuzzy(t *testing.T) {
	e := Extraction{
		EvidenceText:    "revenue grew by twelve precent",
		Span:            Span{Start: 0, End: 10},
		AlignmentStatus: AlignmentFuzzy,
	}
	if err := ValidateWithOptions(e, ValidateOptions{AcceptFuzzy: true}); err != nil {
		t.Errorf("expected fuzzy extraction to validate with AcceptFuzzy, got %v", err)
	}
	// Zero options must behave exactly like strict Validate.
	if err := ValidateWithOptions(e, ValidateOptions{}); err == nil {
		t.Error("expected zero-value ValidateOptions to reject fuzzy alignment")
	}
}

// Planted-span corpus: random source text with known-truth spans, mutated
// evidence must recover offsets covering the truth via the fuzzy path;
// unmutated evidence must stay exact/normalized. Also exercises the
// rune/byte offset math in normalizeWithMap/runeByteOffsets with
// multi-byte runes.
func TestPlantedSpanCorpus(t *testing.T) {
	vocab := []string{"alpha", "beta", "gamma", "delta", "café", "décision",
		"report", "revenue", "invoice", "支付", "token", "span", "offset",
		"source", "evidence", "grounded", "validée", "naïve"}
	rng := rand.New(rand.NewSource(20260729))

	for trial := 0; trial < 200; trial++ {
		n := 20 + rng.Intn(30)
		words := make([]string, n)
		for i := range words {
			words[i] = vocab[rng.Intn(len(vocab))]
		}
		source := strings.Join(words, " ")

		// Plant a truth span of 4-8 tokens.
		spanLen := 4 + rng.Intn(5)
		startTok := rng.Intn(n - spanLen)
		truthTokens := words[startTok : startTok+spanLen]
		truth := strings.Join(truthTokens, " ")

		// Mutate: change one interior token to a near-miss.
		mutated := make([]string, spanLen)
		copy(mutated, truthTokens)
		mi := 1 + rng.Intn(spanLen-2)
		mutated[mi] = mutated[mi] + "x" // typo-like near miss
		evidence := strings.Join(mutated, " ")

		span, status := Align(source, evidence)
		if status != AlignmentFuzzy {
			t.Fatalf("trial %d: expected fuzzy, got %s (evidence %q)", trial, status, evidence)
		}
		if span.Start < 0 || span.End > len(source) || span.End < span.Start {
			t.Fatalf("trial %d: span %+v out of bounds for source len %d", trial, span, len(source))
		}
		got := source[span.Start:span.End]
		if !strings.Contains(got, truthTokens[0]) || !strings.Contains(got, truthTokens[spanLen-1]) {
			t.Errorf("trial %d: recovered span %q does not cover truth %q", trial, got, truth)
		}
		// Span boundaries must fall on rune boundaries.
		if !utf8.ValidString(source[:span.Start]) || !utf8.ValidString(source[:span.End]) {
			t.Errorf("trial %d: span %+v splits a rune", trial, span)
		}
		_ = got
	}
}

// Direct offset-math coverage for normalizeWithMap/runeByteOffsets with
// multi-byte runes and collapsed whitespace.
func TestNormalizeWithMapOffsetMath(t *testing.T) {
	source := "a café\n\t  décision   支付 end"
	norm, mapping := normalizeWithMap(source)
	normRunes := []rune(norm)
	if len(mapping) != len(normRunes) {
		t.Fatalf("mapping len %d != normalized rune len %d", len(mapping), len(normRunes))
	}
	srcRunes := []rune(source)
	for j, origIdx := range mapping {
		if normRunes[j] == ' ' && !isSpaceRune(srcRunes[origIdx]) {
			// collapsed whitespace maps to first rune of the run
			t.Errorf("mapping[%d]=%d: expected whitespace rune, got %q", j, origIdx, srcRunes[origIdx])
		}
		if normRunes[j] != ' ' && normRunes[j] != srcRunes[origIdx] {
			t.Errorf("mapping[%d]=%d: rune %q != source rune %q", j, origIdx, normRunes[j], srcRunes[origIdx])
		}
	}

	offsets := runeByteOffsets(source)
	if len(offsets) != len(srcRunes)+1 {
		t.Fatalf("offsets len %d != runes+1 %d", len(offsets), len(srcRunes)+1)
	}
	if offsets[len(srcRunes)] != len(source) {
		t.Errorf("final offset %d != len(source) %d", offsets[len(srcRunes)], len(source))
	}
	for k := 1; k < len(offsets); k++ {
		if offsets[k] <= offsets[k-1] {
			t.Errorf("offsets not strictly increasing at %d: %v", k, offsets)
			break
		}
	}
}

func isSpaceRune(r rune) bool {
	return r == ' ' || r == '\n' || r == '\t' || r == '\r'
}
