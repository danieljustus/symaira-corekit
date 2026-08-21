package mcpcfgkit

import "strings"

// JSONCStrip removes // line comments and /* block comments from JSONC text,
// preserving strings (so URLs like "https://" survive) and their escapes.
// This is the minimal scanner shared by all MCP-config consumers.
func JSONCStrip(input string) string {
	var out strings.Builder
	out.Grow(len(input))
	runes := []rune(input)
	i := 0
	n := len(runes)
	inString := false
	escaped := false
	for i < n {
		c := runes[i]
		if inString {
			out.WriteRune(c)
			if escaped {
				escaped = false
			} else if c == '\\' {
				escaped = true
			} else if c == '"' {
				inString = false
			}
			i++
			continue
		}
		if c == '"' {
			inString = true
			out.WriteRune(c)
			i++
			continue
		}
		if c == '/' && i+1 < n {
			next := runes[i+1]
			if next == '/' {
				for i < n && runes[i] != '\n' {
					i++
				}
				continue
			}
			if next == '*' {
				i += 2
				for i+1 < n && !(runes[i] == '*' && runes[i+1] == '/') {
					i++
				}
				i += 2
				continue
			}
		}
		out.WriteRune(c)
		i++
	}
	return out.String()
}
