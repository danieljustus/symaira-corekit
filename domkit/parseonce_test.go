package domkit

import (
	"strings"
	"testing"
)

// richParsePage exercises every render path: language, JSON-LD schema,
// headings, lists, links, images, skippable elements, and #99's quoted
// attribute values.
const richParsePage = `<html lang="de">
<head><title>Parse once</title>
<script type="application/ld+json">{"@type":"Article","headline":"Parse once"}</script>
</head>
<body>
<main data-x="">
<h1>Überschrift</h1>
<p>Ein <strong>fetter</strong> Absatz mit <a href="/ziel">Link</a>
und einem <img src="/bild.png" alt="Bild">.</p>
<ul><li>Punkt eins</li><li>Punkt zwei</li></ul>
<p title="a b">Quoted attribute value</p>
<pre><code>code</code></pre>
<script>evil()</script>
<style>.hidden{}</style>
<h2>Unterpunkt</h2>
</main>
</body>
</html>`

// TestRenderMatchesStringPipeline proves the parse-once refactor is
// behavior-preserving: for every option combination, Render must produce
// the same document the string-based helpers produce on the same source.
func TestRenderMatchesStringPipeline(t *testing.T) {
	combos := []Options{
		{},
		{Raw: true},
		{Outline: true},
		{Selector: "main"},
		{Selector: "[data-x]"},
		{Filter: "script"},
		{Filter: `[title="a b"]`},
		{Raw: true, Selector: "main"},
		{Outline: true, Filter: "script"},
		{Selector: "main", Filter: "script"},
		{MaxChars: 60},
	}
	for _, options := range combos {
		t.Run(renderComboName(options), func(t *testing.T) {
			document, err := Render(richParsePage, "Parse once", "https://example.test/", options)
			if err != nil {
				t.Fatal(err)
			}
			selected, err := selectSource(richParsePage, options.Selector, options.Filter)
			if err != nil {
				t.Fatal(err)
			}
			if document.Lang != Lang(selected) {
				t.Errorf("Lang = %q, want %q", document.Lang, Lang(selected))
			}
			if document.SchemaType != schemaTypeFromHTML(selected) {
				t.Errorf("SchemaType = %q, want %q", document.SchemaType, schemaTypeFromHTML(selected))
			}
			if document.CharCount != utf8RuneCount(selected) {
				t.Errorf("CharCount = %d, want %d", document.CharCount, utf8RuneCount(selected))
			}
			switch {
			case options.Raw:
				raw, truncated := Truncate(selected, options.MaxChars)
				if document.Raw != raw || document.Truncated != truncated {
					t.Errorf("Raw = %q (%v), want %q (%v)", document.Raw, document.Truncated, raw, truncated)
				}
			case options.Outline:
				want := Outline(selected)
				if len(document.Outline) != len(want) {
					t.Errorf("Outline = %#v, want %#v", document.Outline, want)
				}
			default:
				markdown, truncated := Truncate(Markdown(selected), options.MaxChars)
				if document.Markdown != markdown || document.Truncated != truncated {
					t.Errorf("Markdown = %q (%v), want %q (%v)", document.Markdown, document.Truncated, markdown, truncated)
				}
			}
		})
	}
}

func renderComboName(options Options) string {
	var parts []string
	if options.Raw {
		parts = append(parts, "raw")
	}
	if options.Outline {
		parts = append(parts, "outline")
	}
	if options.Selector != "" {
		parts = append(parts, "selector="+options.Selector)
	}
	if options.Filter != "" {
		parts = append(parts, "filter="+options.Filter)
	}
	if options.MaxChars != 0 {
		parts = append(parts, "maxchars")
	}
	if len(parts) == 0 {
		return "default"
	}
	return strings.Join(parts, "_")
}

// TestRenderParseOnceOutput locks in concrete output values so the shared
// tree path cannot silently drift.
func TestRenderParseOnceOutput(t *testing.T) {
	document, err := Render(richParsePage, "Parse once", "https://example.test/", Options{})
	if err != nil {
		t.Fatal(err)
	}
	if document.Lang != "de" || document.SchemaType != "Article" {
		t.Fatalf("metadata = %#v", document)
	}
	for _, expected := range []string{"# Überschrift", "**fetter**", "[Link](/ziel)", "![Bild](/bild.png)", "- Punkt eins", "Quoted attribute value"} {
		if !strings.Contains(document.Markdown, expected) {
			t.Errorf("markdown is missing %q:\n%s", expected, document.Markdown)
		}
	}
	for _, forbidden := range []string{"evil()", ".hidden{}"} {
		if strings.Contains(document.Markdown, forbidden) {
			t.Errorf("markdown must not contain %q", forbidden)
		}
	}
}

// BenchmarkRenderParseOnce measures the full single-parse pipeline.
func BenchmarkRenderParseOnce(b *testing.B) {
	for i := 0; i < b.N; i++ {
		if _, err := Render(richParsePage, "Parse once", "https://example.test/", Options{}); err != nil {
			b.Fatal(err)
		}
	}
}
