package domkit

import (
	"fmt"
	"strings"
	"testing"
)

// Generated local text, not a captured web page or a network benchmark.
func truncationPage(paragraphs int) (string, string) {
	const paragraph = "A document paragraph with evidence, links and Unicode: Grüße 世界 🙂. "
	body := strings.Repeat(paragraph, paragraphs)
	return body, `<html lang="de"><body><h1>Document</h1><p>` + body + `</p></body></html>`
}

func BenchmarkTruncate(b *testing.B) {
	for _, paragraphs := range []int{10, 1000, 16000} {
		body, _ := truncationPage(paragraphs)
		b.Run(fmt.Sprintf("paragraphs=%d", paragraphs), func(b *testing.B) {
			want, wantTruncated := referenceTruncate(body, DefaultMaxChars)
			b.ReportAllocs()
			b.SetBytes(int64(len(body)))
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				got, truncated := Truncate(body, DefaultMaxChars)
				if got != want || truncated != wantTruncated {
					b.Fatal("truncation differs from reference")
				}
			}
		})
	}
}

func BenchmarkRenderTruncated(b *testing.B) {
	for _, paragraphs := range []int{10, 1000, 16000} {
		_, page := truncationPage(paragraphs)
		for _, raw := range []bool{false, true} {
			b.Run(fmt.Sprintf("paragraphs=%d/raw=%t", paragraphs, raw), func(b *testing.B) {
				body := page
				if !raw {
					body = Markdown(page)
				}
				want, wantTruncated := referenceTruncate(body, DefaultMaxChars)
				b.ReportAllocs()
				b.SetBytes(int64(len(page)))
				b.ResetTimer()
				for i := 0; i < b.N; i++ {
					doc, err := Render(page, "Document", "https://example.test/", Options{Raw: raw})
					if err != nil {
						b.Fatal(err)
					}
					got := doc.Markdown
					if raw {
						got = doc.Raw
					}
					if got != want || doc.Truncated != wantTruncated || doc.Lang != "de" {
						b.Fatal("render differs from reference")
					}
				}
			})
		}
	}
}
