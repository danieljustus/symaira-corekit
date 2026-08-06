package domkit

import (
	"strings"
	"testing"

	"golang.org/x/net/html"
)

func TestMatchesSelectorTag(t *testing.T) {
	node := elementNode("ul", nil)
	if !matchesSelector(node, "ul") {
		t.Error("ul should match selector ul")
	}
	if matchesSelector(node, "p") {
		t.Error("ul must not match selector p")
	}
}

func TestMatchesSelectorClass(t *testing.T) {
	node := elementNode("div", map[string]string{"class": "a main b"})
	if !matchesSelector(node, ".main") {
		t.Error("div.a main b should match .main")
	}
	if matchesSelector(node, ".other") {
		t.Error("div must not match .other")
	}
}

func TestMatchesSelectorID(t *testing.T) {
	node := elementNode("div", map[string]string{"id": "content"})
	if !matchesSelector(node, "#content") {
		t.Error("div#content should match #content")
	}
	if matchesSelector(node, "#other") {
		t.Error("div must not match #other")
	}
}

func TestMatchesSelectorAttributePresence(t *testing.T) {
	node := elementNode("a", map[string]string{"href": "/x"})
	if !matchesSelector(node, "[href]") {
		t.Error("a[href=/x] should match [href]")
	}
	if matchesSelector(node, "[data-x]") {
		t.Error("a without data-x must not match [data-x]")
	}
}

func TestMatchesSelectorAttributeExact(t *testing.T) {
	node := elementNode("a", map[string]string{"href": "/x", "data-kind": "article"})
	if !matchesSelector(node, "[href=/x]") {
		t.Error(`a[href=/x] should match [href=/x]`)
	}
	if !matchesSelector(node, `[data-kind="article"]`) {
		t.Error(`a[data-kind=article] should match [data-kind="article"]`)
	}
	if !matchesSelector(node, `[data-kind='article']`) {
		t.Error("single-quoted attribute value should match")
	}
	if matchesSelector(node, "[href=/y]") {
		t.Error("a[href=/x] must not match [href=/y]")
	}
}

func TestMatchesSelectorCombinationOnSameNode(t *testing.T) {
	node := elementNode("a", map[string]string{"href": "/x", "data-kind": "article"})
	if !matchesSelector(node, "[href] [data-kind]") {
		t.Error("space-separated parts are ANDed on the same node")
	}
	if matchesSelector(node, "[href] [data-other]") {
		t.Error("AND combination must fail when one attribute is missing")
	}
}

func elementNode(tag string, attrs map[string]string) *html.Node {
	node := &html.Node{Type: html.ElementNode, Data: tag}
	for key, value := range attrs {
		node.Attr = append(node.Attr, html.Attribute{Key: key, Val: value})
	}
	return node
}

func TestSchemaTypeFromJSONLDDirect(t *testing.T) {
	source := `<html><head><script type="application/ld+json">{"@type":"Article","headline":"x"}</script></head></html>`
	if got := schemaTypeFromHTML(source); got != "Article" {
		t.Fatalf("schema_type = %q, want Article", got)
	}
}

func TestSchemaTypeFallsBackToTypeField(t *testing.T) {
	source := `<html><head><script type="application/ld+json">{"type":"Recipe"}</script></head></html>`
	if got := schemaTypeFromHTML(source); got != "Recipe" {
		t.Fatalf("schema_type = %q, want Recipe (type fallback)", got)
	}
}

func TestSchemaTypeMalformedJSON(t *testing.T) {
	source := `<html><head><script type="application/ld+json">{not json</script></head></html>`
	if got := schemaTypeFromHTML(source); got != "" {
		t.Fatalf("schema_type = %q, want empty for malformed JSON", got)
	}
}

func TestSchemaTypeNoJSONLD(t *testing.T) {
	if got := schemaTypeFromHTML("<html><body><p>plain</p></body></html>"); got != "" {
		t.Fatalf("schema_type = %q, want empty", got)
	}
}

func TestSchemaTypeIgnoresOtherScriptTypes(t *testing.T) {
	source := `<html><head><script type="application/json">{"@type":"NotLD"}</script></head></html>`
	if got := schemaTypeFromHTML(source); got != "" {
		t.Fatalf("schema_type = %q, want empty for non-ld+json script", got)
	}
}

func TestSchemaTypeFirstJSONLDWins(t *testing.T) {
	source := `<html><head>
<script type="application/ld+json">{"@type":"First"}</script>
<script type="application/ld+json">{"@type":"Second"}</script>
</head></html>`
	if got := schemaTypeFromHTML(source); got != "First" {
		t.Fatalf("schema_type = %q, want First", got)
	}
}

func TestSelectSourcePassthrough(t *testing.T) {
	source := "<html><body><p>x</p></body></html>"
	got, err := selectSource(source, "", "")
	if err != nil {
		t.Fatal(err)
	}
	if got != source {
		t.Fatalf("passthrough = %q, want %q", got, source)
	}
}

func TestSelectSourceSelectorSubtree(t *testing.T) {
	source := `<html><body><h1>t</h1><ul><li>a</li></ul></body></html>`
	got, err := selectSource(source, "ul", "")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "<ul>") || strings.Contains(got, "h1") {
		t.Fatalf("selected = %q, want only the ul subtree", got)
	}
}

func TestSelectSourceSelectorNoMatch(t *testing.T) {
	_, err := selectSource("<html><body><p>x</p></body></html>", "blockquote", "")
	if err == nil || !strings.Contains(err.Error(), "did not match") {
		t.Fatalf("error = %v, want a did-not-match error", err)
	}
}

func TestSelectSourceFilterRemovesMatches(t *testing.T) {
	source := `<html><body><script>evil()</script><p>keep</p></body></html>`
	got, err := selectSource(source, "", "script")
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(got, "evil") {
		t.Fatalf("filtered = %q, script must be removed", got)
	}
	if !strings.Contains(got, "keep") {
		t.Fatalf("filtered = %q, p must remain", got)
	}
}

func TestSelectSourceFilterNoMatchUnchanged(t *testing.T) {
	source := `<html><body><p>keep</p></body></html>`
	got, err := selectSource(source, "", "blockquote")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(got, "keep") {
		t.Fatalf("filtered = %q, content must be unchanged", got)
	}
}

func TestRenderSelectorErrorPropagates(t *testing.T) {
	_, err := Render("<html><body><p>x</p></body></html>", "t", "https://example.test/", Options{Selector: "zzz"})
	if err == nil || !strings.Contains(err.Error(), "did not match") {
		t.Fatalf("error = %v, want selector did-not-match", err)
	}
}
