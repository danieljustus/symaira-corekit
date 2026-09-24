package domkit

import (
	"fmt"
	"testing"
)

// referenceTruncate retains the original full-rune-slice semantics, including
// replacing each malformed UTF-8 byte only when the input is truncated.
func referenceTruncate(text string, budget int) (string, bool) {
	runes := []rune(text)
	if budget <= 0 || len(runes) <= budget {
		return text, false
	}
	head, tail := budget/2, budget-budget/2
	return fmt.Sprintf("%s\n\n… [truncated: %d runes omitted] …\n\n%s",
		string(runes[:head]), len(runes)-budget, string(runes[len(runes)-tail:])), true
}

func FuzzTruncateParity(f *testing.F) {
	for _, text := range []string{"", "abcde", "Grüße 世界 🙂", "e\u0301👩‍💻\r\n", "\xff\xfeab\xc0\xaf", "\xf0\x9f\x99", "a\x00b\xef\xbf\xbdc"} {
		for _, budget := range []int{-1, 0, 1, 2, 3, 10, 15000} {
			f.Add(text, budget)
		}
	}
	f.Fuzz(func(t *testing.T, text string, budget int) {
		want, wantTruncated := referenceTruncate(text, budget)
		got, truncated := Truncate(text, budget)
		if got != want || truncated != wantTruncated {
			t.Fatalf("Truncate(%q, %d) = (%q, %v), want (%q, %v)",
				text, budget, got, truncated, want, wantTruncated)
		}
	})
}
