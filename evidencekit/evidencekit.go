// Package evidencekit defines Symaira-wide grounded extraction contracts:
// a source reference, a character span, and an Extraction that ties an
// extracted fact back to the exact source text that justified it.
//
// The pattern: callers align EvidenceText against the original source text
// to produce a Span. Alignment can be exact (byte-identical substring) or
// normalized (whitespace-collapsed substring); when neither succeeds the
// extraction is marked AlignmentUnmatched and must not be treated as
// grounded by consumers that require grounded-only ingestion.
//
// This package has no cloud, LLM, or tool-specific dependencies and does not
// import symingest, symseek, or symmemory. It only defines the shared shape
// and the deterministic alignment/validation helpers around it.
package evidencekit

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"unicode"
	"unicode/utf8"
)

// AlignmentStatus describes how confidently an Extraction's EvidenceText was
// located in its source text. Field values are part of the cross-repo
// contract — do not rename.
type AlignmentStatus string

const (
	// AlignmentExact means EvidenceText was found as a byte-identical
	// substring of the source text.
	AlignmentExact AlignmentStatus = "exact"
	// AlignmentNormalized means EvidenceText was found only after
	// collapsing runs of whitespace in both source and evidence text.
	AlignmentNormalized AlignmentStatus = "normalized"
	// AlignmentUnmatched means EvidenceText could not be located in the
	// source text by any supported strategy. Span is meaningless and
	// callers requiring grounded-only ingestion must reject or downgrade
	// the extraction.
	AlignmentUnmatched AlignmentStatus = "unmatched"
)

// SourceRef identifies the source document, session, or record that an
// Extraction's evidence was drawn from. Field names are part of the
// cross-repo JSON contract (snake_case) — do not rename.
type SourceRef struct {
	ID   string `json:"id"`
	Kind string `json:"kind,omitempty"`
}

// Span is a half-open [Start, End) byte range into the source text.
type Span struct {
	Start int `json:"char_start"`
	End   int `json:"char_end"`
}

// Extraction is one grounded fact extracted from a source, together with
// the evidence text and its span in the source text. Field names are part
// of the cross-repo JSON contract — do not rename.
type Extraction struct {
	Source          SourceRef         `json:"source"`
	Text            string            `json:"text"`
	EvidenceText    string            `json:"evidence_text"`
	Span            Span              `json:"span"`
	AlignmentStatus AlignmentStatus   `json:"alignment_status"`
	Attributes      map[string]string `json:"attributes,omitempty"`
}

// AlignExact reports whether evidenceText occurs verbatim in source and, if
// so, returns its byte span.
func AlignExact(source, evidenceText string) (Span, bool) {
	if evidenceText == "" {
		return Span{}, false
	}
	idx := strings.Index(source, evidenceText)
	if idx < 0 {
		return Span{}, false
	}
	return Span{Start: idx, End: idx + len(evidenceText)}, true
}

// AlignNormalized reports whether evidenceText occurs in source once runs of
// whitespace are collapsed to a single space on both sides (and the
// evidence text is trimmed). The returned Span maps back to byte offsets in
// the original, un-normalized source.
func AlignNormalized(source, evidenceText string) (Span, bool) {
	normSource, mapping := normalizeWithMap(source)
	normEvidence, _ := normalizeWithMap(evidenceText)
	normEvidence = strings.TrimSpace(normEvidence)
	if normEvidence == "" {
		return Span{}, false
	}

	byteIdx := strings.Index(normSource, normEvidence)
	if byteIdx < 0 {
		return Span{}, false
	}

	startRune := utf8.RuneCountInString(normSource[:byteIdx])
	matchedRunes := utf8.RuneCountInString(normEvidence)
	endRune := startRune + matchedRunes
	if startRune >= len(mapping) || endRune-1 >= len(mapping) {
		return Span{}, false
	}

	origOffsets := runeByteOffsets(source)
	startOrigRune := mapping[startRune]
	endOrigRune := mapping[endRune-1] + 1

	return Span{Start: origOffsets[startOrigRune], End: origOffsets[endOrigRune]}, true
}

// Align tries AlignExact, then AlignNormalized, and reports the resulting
// Span alongside the AlignmentStatus that produced it. When neither
// strategy succeeds it returns a zero Span and AlignmentUnmatched.
func Align(source, evidenceText string) (Span, AlignmentStatus) {
	if span, ok := AlignExact(source, evidenceText); ok {
		return span, AlignmentExact
	}
	if span, ok := AlignNormalized(source, evidenceText); ok {
		return span, AlignmentNormalized
	}
	return Span{}, AlignmentUnmatched
}

// Validate checks that an Extraction is grounded: its AlignmentStatus is not
// AlignmentUnmatched, its EvidenceText is non-empty, and its Span has
// non-negative, non-decreasing bounds. Callers implementing grounded-only
// ingestion should reject any Extraction that fails Validate.
func Validate(e Extraction) error {
	if e.AlignmentStatus == AlignmentUnmatched {
		return errors.New("evidencekit: extraction is unmatched, not grounded")
	}
	if e.EvidenceText == "" {
		return errors.New("evidencekit: empty evidence text")
	}
	if e.Span.Start < 0 || e.Span.End < e.Span.Start {
		return fmt.Errorf("evidencekit: invalid span [%d,%d)", e.Span.Start, e.Span.End)
	}
	return nil
}

// EncodeJSONL writes extractions to w as newline-delimited JSON, one
// Extraction per line — the extraction sidecar format shared across repos.
func EncodeJSONL(w io.Writer, extractions []Extraction) error {
	enc := json.NewEncoder(w)
	for _, e := range extractions {
		if err := enc.Encode(e); err != nil {
			return fmt.Errorf("evidencekit: encode extraction: %w", err)
		}
	}
	return nil
}

// DecodeJSONL reads newline-delimited Extraction JSON from r. Blank lines
// are skipped.
func DecodeJSONL(r io.Reader) ([]Extraction, error) {
	var out []Extraction
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var e Extraction
		if err := json.Unmarshal([]byte(line), &e); err != nil {
			return nil, fmt.Errorf("evidencekit: decode line: %w", err)
		}
		out = append(out, e)
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("evidencekit: scan jsonl: %w", err)
	}
	return out, nil
}

// normalizeWithMap collapses runs of Unicode whitespace in s to a single
// ' ' and returns the normalized string alongside mapping, where
// mapping[j] is the rune index (in s) of the rune that produced the j-th
// rune of the normalized string.
func normalizeWithMap(s string) (string, []int) {
	runes := []rune(s)
	norm := make([]rune, 0, len(runes))
	mapping := make([]int, 0, len(runes))
	inSpace := false
	for idx, r := range runes {
		if unicode.IsSpace(r) {
			if !inSpace {
				norm = append(norm, ' ')
				mapping = append(mapping, idx)
				inSpace = true
			}
			continue
		}
		norm = append(norm, r)
		mapping = append(mapping, idx)
		inSpace = false
	}
	return string(norm), mapping
}

// runeByteOffsets returns, for each rune index k in s, the byte offset of
// that rune; the final element is len(s).
func runeByteOffsets(s string) []int {
	offsets := make([]int, 0, len(s)+1)
	for i := range s {
		offsets = append(offsets, i)
	}
	offsets = append(offsets, len(s))
	return offsets
}
