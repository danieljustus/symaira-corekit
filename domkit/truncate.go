package domkit

import (
	"strings"
	"unicode/utf8"
)

// DefaultMaxChars is the per-page character budget for truncation. It matches
// symfetch's default char_limit (15000).
const DefaultMaxChars = 15000

// Truncate applies symfetch's truncate-and-store window semantics to a body:
// when the rune count exceeds maxChars the head and tail halves of the budget
// are kept and the omitted middle is marked. The result reports whether the
// body was truncated. (Persisting the full text to the cache is owned by the
// token-budget issue, B-19.)
func Truncate(text string, maxChars int) (string, bool) {
	if maxChars <= 0 {
		return text, false
	}
	total := utf8.RuneCountInString(text)
	if total <= maxChars {
		return text, false
	}
	head := takeRunes(text, maxChars/2)
	tail := takeRunesFromEnd(text, maxChars-maxChars/2)
	omitted := total - maxChars
	marker := "\n\n… [truncated: " + itoa(omitted) + " runes omitted] …\n\n"
	return head + marker + tail, true
}

func takeRunes(text string, count int) string {
	if count <= 0 {
		return ""
	}
	var builder strings.Builder
	seen := 0
	for _, r := range text {
		if seen >= count {
			break
		}
		builder.WriteRune(r)
		seen++
	}
	return builder.String()
}

func takeRunesFromEnd(text string, count int) string {
	if count <= 0 {
		return ""
	}
	start := len(text)
	for seen := 0; seen < count && start > 0; seen++ {
		_, size := utf8.DecodeLastRuneInString(text[:start])
		start -= size
	}
	if start == 0 {
		return text
	}
	// Convert only the retained suffix, preserving replacement of invalid UTF-8.
	return string([]rune(text[start:]))
}

func itoa(value int) string {
	if value == 0 {
		return "0"
	}
	negative := value < 0
	if negative {
		value = -value
	}
	var digits []byte
	for value > 0 {
		digits = append([]byte{byte('0' + value%10)}, digits...)
		value /= 10
	}
	if negative {
		return "-" + string(digits)
	}
	return string(digits)
}
