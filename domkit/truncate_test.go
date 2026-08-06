package domkit

import (
	"strings"
	"testing"
)

func TestTruncateExactBudgetUntouched(t *testing.T) {
	body := strings.Repeat("a", 100)
	truncated, isTruncated := Truncate(body, 100)
	if isTruncated || truncated != body {
		t.Fatalf("truncated = %q, %v; want untouched at exact budget", truncated, isTruncated)
	}
}

func TestTruncateOneOverBudget(t *testing.T) {
	body := strings.Repeat("a", 101)
	truncated, isTruncated := Truncate(body, 100)
	if !isTruncated {
		t.Fatal("expected truncation one rune over budget")
	}
	if !strings.Contains(truncated, "[truncated:") {
		t.Fatalf("missing truncation marker: %q", truncated)
	}
}

func TestTruncateZeroAndNegativeBudgetUntouched(t *testing.T) {
	body := "some body"
	for _, budget := range []int{0, -1, -100} {
		truncated, isTruncated := Truncate(body, budget)
		if isTruncated || truncated != body {
			t.Fatalf("budget %d: truncated = %q, %v; want untouched", budget, truncated, isTruncated)
		}
	}
}

func TestTruncateOddBudgetSplit(t *testing.T) {
	// maxChars=3 keeps head of 1 and tail of 2 (maxChars-maxChars/2).
	truncated, isTruncated := Truncate("abcde", 3)
	if !isTruncated {
		t.Fatal("expected truncation")
	}
	if !strings.HasPrefix(truncated, "a") {
		t.Fatalf("head not preserved: %q", truncated)
	}
	if !strings.HasSuffix(truncated, "de") {
		t.Fatalf("tail not preserved: %q", truncated)
	}
}

func TestTruncateSingleRuneBudget(t *testing.T) {
	truncated, isTruncated := Truncate("ab", 1)
	if !isTruncated {
		t.Fatal("expected truncation")
	}
	if !strings.HasSuffix(truncated, "b") {
		t.Fatalf("tail not preserved: %q", truncated)
	}
}

func TestTruncateEmptyBody(t *testing.T) {
	truncated, isTruncated := Truncate("", 10)
	if isTruncated || truncated != "" {
		t.Fatalf("truncated = %q, %v; want empty untouched", truncated, isTruncated)
	}
}

func TestTruncateHeadTailRuneCounts(t *testing.T) {
	body := strings.Repeat("x", 50) + strings.Repeat("y", 50)
	truncated, _ := Truncate(body, 20)
	// head = 10 x's, tail = 10 y's; the marker reports 80 omitted runes.
	if !strings.Contains(truncated, "[truncated: 80 runes omitted]") {
		t.Fatalf("marker with omitted count missing: %q", truncated)
	}
	if !strings.HasPrefix(truncated, "xxxxxxxxxx") || !strings.HasSuffix(truncated, "yyyyyyyyyy") {
		t.Fatalf("head/tail wrong: %q", truncated)
	}
}
