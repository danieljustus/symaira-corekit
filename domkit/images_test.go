package domkit

import (
	"strings"
	"testing"
)

func TestMarkdownRendersImageWithAlt(t *testing.T) {
	markdown := Markdown(`<p><img src="/a.png" alt="a picture"></p>`)
	if !strings.Contains(markdown, "![a picture](/a.png)") {
		t.Fatalf("markdown = %q, want image with alt", markdown)
	}
}

func TestMarkdownRendersImageEmptyAlt(t *testing.T) {
	markdown := Markdown(`<p><img src="/a.png" alt=""></p>`)
	if !strings.Contains(markdown, "![](/a.png)") {
		t.Fatalf("markdown = %q, want image with empty alt", markdown)
	}
}

func TestMarkdownSkipsImageWithoutSrc(t *testing.T) {
	markdown := Markdown(`<p>before<img alt="x">after</p>`)
	if strings.Contains(markdown, "![") {
		t.Fatalf("markdown = %q, image without src must not render", markdown)
	}
	if !strings.Contains(markdown, "before") || !strings.Contains(markdown, "after") {
		t.Fatalf("markdown = %q, surrounding text must remain", markdown)
	}
}

func TestStripBase64ImagesMarkdownWithAlt(t *testing.T) {
	content := "![logo](data:image/png;base64,AAAA)"
	got := StripBase64Images(content)
	if got != "[IMAGE: logo]" {
		t.Fatalf("got %q, want [IMAGE: logo]", got)
	}
}

func TestStripBase64ImagesMarkdownEmptyAlt(t *testing.T) {
	content := "![](data:image/png;base64,AAAA)"
	if got := StripBase64Images(content); got != "[IMAGE]" {
		t.Fatalf("got %q, want [IMAGE]", got)
	}
}

func TestStripBase64ImagesMarkdownAltWhitespace(t *testing.T) {
	content := "![  logo  ](data:image/png;base64,AAAA)"
	if got := StripBase64Images(content); got != "[IMAGE: logo]" {
		t.Fatalf("got %q, want [IMAGE: logo] (trimmed)", got)
	}
}

func TestStripBase64ImagesHTMLWithAlt(t *testing.T) {
	content := `<img src="data:image/png;base64,AAAA" alt="hero">`
	if got := StripBase64Images(content); got != "[IMAGE: hero]" {
		t.Fatalf("got %q, want [IMAGE: hero]", got)
	}
}

func TestStripBase64ImagesHTMLEmptyAlt(t *testing.T) {
	content := `<img src="data:image/png;base64,AAAA" alt="">`
	if got := StripBase64Images(content); got != "[IMAGE]" {
		t.Fatalf("got %q, want [IMAGE]", got)
	}
}

func TestStripBase64ImagesNoDataURIUnchanged(t *testing.T) {
	content := "![logo](/img/logo.png) and <img src=\"/img/logo.png\" alt=\"logo\">"
	if got := StripBase64Images(content); got != content {
		t.Fatalf("got %q, want unchanged content", got)
	}
}

func TestStripBase64ImagesPreservesRealURLs(t *testing.T) {
	content := "![logo](https://example.test/logo.png)"
	if got := StripBase64Images(content); got != content {
		t.Fatalf("got %q, want unchanged http(s) URL", got)
	}
}

func TestStripBase64ImagesMixedContent(t *testing.T) {
	content := "text ![a](data:image/png;base64,AAAA) more ![b](data:image/gif;base64,BBBB) end"
	got := StripBase64Images(content)
	want := "text [IMAGE: a] more [IMAGE: b] end"
	if got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}
