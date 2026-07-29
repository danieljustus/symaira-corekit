// Package evidencekit defines Symaira-wide grounded extraction contracts:
// a source reference, a character span, and an Extraction that ties an
// extracted fact back to the exact source text that justified it.
//
// The pattern: callers align EvidenceText against the original source text
// to produce a Span. Alignment can be exact (byte-identical substring),
// normalized (whitespace-collapsed substring), or fuzzy (token-based
// approximate match); when none succeeds the extraction is marked
// AlignmentUnmatched and must not be treated as grounded by consumers that
// require grounded-only ingestion.
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
	// AlignmentFuzzy means EvidenceText was located only by the
	// token-based fuzzy fallback: a token sliding-window over the source
	// scored by sequence similarity (LCS-style, difflib-like) with
	// per-token edit-distance tolerance. It runs only after exact and
	// whitespace-normalized matching fail. Validate rejects fuzzy
	// alignments by default; see ValidateWithOptions.
	AlignmentFuzzy AlignmentStatus = "fuzzy"
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

// Align tries AlignExact, then AlignNormalized, then a token-based fuzzy
// fallback (AlignFuzzy), and reports the resulting Span alongside the
// AlignmentStatus that produced it. When no strategy succeeds it returns a
// zero Span and AlignmentUnmatched.
func Align(source, evidenceText string) (Span, AlignmentStatus) {
	if span, ok := AlignExact(source, evidenceText); ok {
		return span, AlignmentExact
	}
	if span, ok := AlignNormalized(source, evidenceText); ok {
		return span, AlignmentNormalized
	}
	if span, ok := AlignFuzzy(source, evidenceText); ok {
		return span, AlignmentFuzzy
	}
	return Span{}, AlignmentUnmatched
}

// fuzzyMinScore is the minimum token-sequence similarity (in [0,1]) a
// sliding window of source tokens must reach against the evidence tokens
// for a fuzzy match. Below this threshold extraction falls through to
// AlignmentUnmatched.
const fuzzyMinScore = 0.6

// fuzzyTokenSim is the minimum per-token edit similarity for two tokens to
// count as a (near-)match in the LCS-style sequence score.
const fuzzyTokenSim = 0.6

// AlignFuzzy reports whether evidenceText approximately occurs in source
// using pure-stdlib text processing: both sides are split into
// whitespace-separated tokens, a sliding window of source tokens (sized len(evidence
// tokens)-1..+1) is scored with an LCS-style sequence matcher where tokens
// match when identical or within a small edit-distance ratio, and the best
// window wins when its similarity is at least fuzzyMinScore. The returned
// Span maps back to byte offsets in the original source.
func AlignFuzzy(source, evidenceText string) (Span, bool) {
	ev := tokenize(evidenceText)
	if len(ev) == 0 {
		return Span{}, false
	}
	src := tokenize(source)
	if len(src) == 0 {
		return Span{}, false
	}

	n := len(ev)
	best := 0.0
	var bestSpan Span
	for w := n - 1; w <= n+1; w++ {
		if w < 1 || w > len(src) {
			continue
		}
		for i := 0; i+w <= len(src); i++ {
			score := tokenSeqScore(ev, src[i:i+w])
			if score > best {
				best = score
				bestSpan = Span{Start: src[i].start, End: src[i+w-1].end}
			}
		}
	}
	if best < fuzzyMinScore {
		return Span{}, false
	}
	return bestSpan, true
}

// token is a whitespace-delimited word with byte offsets [start, end) into
// the string it was tokenized from.
type token struct {
	text       string
	start, end int
}

// tokenize splits s on Unicode whitespace, returning tokens with their
// byte offsets in s.
func tokenize(s string) []token {
	var toks []token
	i := 0
	for i < len(s) {
		r, size := utf8.DecodeRuneInString(s[i:])
		if unicode.IsSpace(r) {
			i += size
			continue
		}
		start := i
		for i < len(s) {
			r, size = utf8.DecodeRuneInString(s[i:])
			if unicode.IsSpace(r) {
				break
			}
			i += size
		}
		toks = append(toks, token{text: s[start:i], start: start, end: i})
	}
	return toks
}

// tokenSeqScore returns a difflib-style similarity ratio in [0,1] between
// two token sequences: twice the summed similarity of LCS-matched token
// pairs over the total token count. Tokens pair up when identical or when
// their edit similarity is at least fuzzyTokenSim.
func tokenSeqScore(a, b []token) float64 {
	la, lb := len(a), len(b)
	if la == 0 || lb == 0 {
		return 0
	}
	// DP over LCS with weighted matches.
	prev := make([]float64, lb+1)
	cur := make([]float64, lb+1)
	for i := 1; i <= la; i++ {
		for j := 1; j <= lb; j++ {
			best := prev[j]
			if cur[j-1] > best {
				best = cur[j-1]
			}
			if sim := tokenSimilarity(a[i-1].text, b[j-1].text); sim >= fuzzyTokenSim {
				if v := prev[j-1] + sim; v > best {
					best = v
				}
			}
			cur[j] = best
		}
		prev, cur = cur, prev
	}
	return 2 * prev[lb] / float64(la+lb)
}

// tokenSimilarity returns 1 for identical tokens, otherwise 1 minus the
// normalized rune edit distance (Levenshtein) between them.
func tokenSimilarity(a, b string) float64 {
	if a == b {
		return 1
	}
	ra, rb := []rune(a), []rune(b)
	m := len(ra)
	if len(rb) > m {
		m = len(rb)
	}
	if m == 0 {
		return 1
	}
	return 1 - float64(levenshtein(ra, rb))/float64(m)
}

// levenshtein computes the edit distance between two rune slices.
func levenshtein(a, b []rune) int {
	la, lb := len(a), len(b)
	if la == 0 {
		return lb
	}
	if lb == 0 {
		return la
	}
	prev := make([]int, lb+1)
	cur := make([]int, lb+1)
	for j := 0; j <= lb; j++ {
		prev[j] = j
	}
	for i := 1; i <= la; i++ {
		cur[0] = i
		for j := 1; j <= lb; j++ {
			cost := 0
			if a[i-1] != b[j-1] {
				cost = 1
			}
			d := prev[j] + 1
			if v := cur[j-1] + 1; v < d {
				d = v
			}
			if v := prev[j-1] + cost; v < d {
				d = v
			}
			cur[j] = d
		}
		prev, cur = cur, prev
	}
	return prev[lb]
}

// Sentinel errors returned (wrapped with %w) by Validate so callers can
// branch with errors.Is without matching on message text.
var (
	// ErrUnmatched marks an Extraction whose EvidenceText could not be
	// located in the source text by any alignment strategy.
	ErrUnmatched = errors.New("evidencekit: extraction is unmatched, not grounded")
	// ErrEmptyEvidence marks an Extraction with empty EvidenceText.
	ErrEmptyEvidence = errors.New("evidencekit: empty evidence text")
	// ErrInvalidSpan marks an Extraction whose Span has negative or
	// decreasing bounds.
	ErrInvalidSpan = errors.New("evidencekit: invalid span")
)

// Validate checks that an Extraction is grounded: its AlignmentStatus is
// AlignmentExact or AlignmentNormalized (strict by default — fuzzy
// alignments are rejected; see ValidateWithOptions), its EvidenceText is
// non-empty, and its Span has non-negative, non-decreasing bounds. Callers
// implementing grounded-only ingestion should reject any Extraction that
// fails Validate.
//
// Returned errors wrap ErrUnmatched, ErrEmptyEvidence, or ErrInvalidSpan
// (see errors.Is).
func Validate(e Extraction) error {
	return ValidateWithOptions(e, ValidateOptions{})
}

// ValidateOptions tunes Validate. The zero value is strict validation.
type ValidateOptions struct {
	// AcceptFuzzy allows extractions whose AlignmentStatus is
	// AlignmentFuzzy. By default Validate rejects fuzzy alignments as
	// not grounded.
	AcceptFuzzy bool
}

// ValidateWithOptions is Validate with caller-supplied options.
func ValidateWithOptions(e Extraction, opts ValidateOptions) error {
	if e.AlignmentStatus == AlignmentUnmatched {
		return fmt.Errorf("%w", ErrUnmatched)
	}
	if e.AlignmentStatus == AlignmentFuzzy && !opts.AcceptFuzzy {
		return fmt.Errorf("%w", ErrUnmatched)
	}
	if e.EvidenceText == "" {
		return fmt.Errorf("%w", ErrEmptyEvidence)
	}
	if e.Span.Start < 0 || e.Span.End < e.Span.Start {
		return fmt.Errorf("%w [%d,%d)", ErrInvalidSpan, e.Span.Start, e.Span.End)
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
