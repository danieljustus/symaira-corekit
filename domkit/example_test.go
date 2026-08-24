package domkit_test

import (
	"fmt"

	"github.com/danieljustus/symaira-corekit/domkit"
)

func ExampleMarkdown() {
	html := `<p>Hello, <strong>world</strong>!</p>`
	fmt.Println(domkit.Markdown(html))
	// Output:
	// Hello,**world**!
}

func ExampleOutline() {
	html := `<h1>Title</h1><h2>Subtitle</h2>`
	headings := domkit.Outline(html)
	for _, h := range headings {
		fmt.Printf("h%d: %s\n", h.Level, h.Text)
	}
	// Output:
	// h1: Title
	// h2: Subtitle
}

func ExampleRender() {
	html := `<html><head><title>My Page</title></head><body><p>Hello</p></body></html>`
	doc, err := domkit.Render(html, "My Page", "https://example.com/page", domkit.Options{})
	if err != nil {
		fmt.Printf("error: %v\n", err)
		return
	}
	fmt.Printf("%s (%s): %s\n", doc.Title, doc.URL, doc.Markdown)
	// Output:
	// My Page (https://example.com/page): Hello
}

func ExampleLang() {
	html := `<html lang="de"><body>Hallo</body></html>`
	fmt.Println(domkit.Lang(html))
	// Output:
	// de
}
