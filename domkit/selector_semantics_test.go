package domkit

import (
	"strings"
	"testing"
)

// TestMatchesSelectorAttributePresenceEmptyValue locks in CSS presence
// semantics: [attr] matches on attribute presence, even with an empty value.
func TestMatchesSelectorAttributePresenceEmptyValue(t *testing.T) {
	node := elementNode("div", map[string]string{"data-x": ""})
	if !matchesSelector(node, "[data-x]") {
		t.Error(`<div data-x=""> must match [data-x] (presence semantics)`)
	}
	missing := elementNode("div", nil)
	if matchesSelector(missing, "[data-x]") {
		t.Error("div without data-x must not match [data-x]")
	}
}

// TestMatchesSelectorQuotedValueWithSpace locks in quote-aware parsing:
// quoted attribute values containing spaces must survive the part split.
func TestMatchesSelectorQuotedValueWithSpace(t *testing.T) {
	node := elementNode("div", map[string]string{"title": "a b"})
	if !matchesSelector(node, `[title="a b"]`) {
		t.Error(`div[title="a b"] must match [title="a b"]`)
	}
	if !matchesSelector(node, `[title='a b']`) {
		t.Error("div[title='a b'] must match single-quoted selector")
	}
	if matchesSelector(node, `[title="a"]`) {
		t.Error(`div[title="a b"] must not match [title="a"]`)
	}
}

func TestMatchesSelectorQuotedValueUntouchedInside(t *testing.T) {
	// Quotes are delimiters only: a single-quoted selector may carry
	// double quotes inside the value, compared literally.
	node := elementNode("div", map[string]string{"title": `a "quoted" b`})
	if !matchesSelector(node, `[title='a "quoted" b']`) {
		t.Error("quotes inside the value are compared literally")
	}
}

func TestMatchesSelectorEmptyValueExactNeedsPresence(t *testing.T) {
	empty := elementNode("div", map[string]string{"data-x": ""})
	if !matchesSelector(empty, `[data-x=""]`) {
		t.Error(`<div data-x=""> must match [data-x=""]`)
	}
	missing := elementNode("div", nil)
	if matchesSelector(missing, `[data-x=""]`) {
		t.Error(`div without data-x must not match [data-x=""]`)
	}
}

func TestMatchesSelectorBlankSelector(t *testing.T) {
	node := elementNode("div", nil)
	for _, selector := range []string{"", "   ", "\t\n"} {
		if matchesSelector(node, selector) {
			t.Errorf("blank selector %q must not match any node", selector)
		}
	}
}

func TestMatchesSelectorQuotedPartsAndCombination(t *testing.T) {
	node := elementNode("div", map[string]string{"title": "a b", "data-kind": "x"})
	if !matchesSelector(node, `[title="a b"] [data-kind]`) {
		t.Error("quoted part followed by a bare part must AND on the node")
	}
}

func TestRenderSelectorPresenceEmptyValue(t *testing.T) {
	source := `<html><body><div data-x=""><p>empty</p></div><p>other</p></body></html>`
	document, err := Render(source, "t", "https://example.test/", Options{Selector: "[data-x]"})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(document.Markdown, "empty") {
		t.Fatalf("selector render must include the empty-valued element: %q", document.Markdown)
	}
	if strings.Contains(document.Markdown, "other") {
		t.Fatalf("selector render must exclude the rest: %q", document.Markdown)
	}
}

func TestRenderFilterQuotedValueWithSpace(t *testing.T) {
	source := `<html><body><p title="a b">gone</p><p>keep</p></body></html>`
	document, err := Render(source, "t", "https://example.test/", Options{Filter: `[title="a b"]`})
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(document.Markdown, "gone") {
		t.Fatalf("filter must remove the quoted-value element: %q", document.Markdown)
	}
	if !strings.Contains(document.Markdown, "keep") {
		t.Fatalf("filter must keep the rest: %q", document.Markdown)
	}
}
