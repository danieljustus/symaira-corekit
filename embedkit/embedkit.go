// Package embedkit provides the shared embedding-provenance type and
// embedding-space identity guard used across Symaira tools, so a vector
// embedded by one model/quantization/dimension combination is never
// silently compared against one from a different combination.
package embedkit

// Result is a single embedding vector plus the provenance needed to decide
// whether it lives in the same embedding space as another Result.
type Result struct {
	// Vector is the embedding itself.
	Vector []float32
	// Source names where the vector came from (e.g. a provider name like
	// "ollama", or a fallback identifier like "local-hash").
	Source string
	// Model is the model name that produced Vector.
	Model string
	// Dim is the vector's dimensionality.
	Dim int
	// Quant identifies the quantization level of Model (e.g. "4bit-mlx").
	// Empty means unquantized/full precision. Two Results with the same
	// Model but different Quant are different embedding spaces even
	// though the model name is identical.
	Quant string
}

// SameSpace reports whether a and b were produced in the same embedding
// space: same model, same quantization level, and same dimensionality.
// Vectors from different spaces are not meaningfully comparable (e.g. via
// cosine similarity) even when their model name matches, because a
// quantized and an unquantized embedding of the same model occupy
// different vector spaces.
func SameSpace(a, b Result) bool {
	return a.Model == b.Model && a.Quant == b.Quant && a.Dim == b.Dim
}
