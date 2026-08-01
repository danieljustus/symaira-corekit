package embedkit

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/danieljustus/symaira-corekit/ollamakit"
)

func TestHashProviderIsDeterministic(t *testing.T) {
	p := HashProvider{}

	got1, err := p.Embed(context.Background(), []string{"hello"})
	if err != nil {
		t.Fatalf("Embed error: %v", err)
	}
	got2, err := p.Embed(context.Background(), []string{"hello"})
	if err != nil {
		t.Fatalf("Embed error: %v", err)
	}

	if len(got1) != 1 || len(got2) != 1 {
		t.Fatalf("expected 1 result, got %d and %d", len(got1), len(got2))
	}
	if len(got1[0].Vector) != len(got2[0].Vector) {
		t.Fatalf("vector length mismatch")
	}
	for i := range got1[0].Vector {
		if got1[0].Vector[i] != got2[0].Vector[i] {
			t.Fatalf("hash fallback not deterministic at index %d: %v vs %v", i, got1[0].Vector[i], got2[0].Vector[i])
		}
	}
}

func TestHashProviderDistinctInputsDiffer(t *testing.T) {
	p := HashProvider{}
	results, err := p.Embed(context.Background(), []string{"hello", "world"})
	if err != nil {
		t.Fatalf("Embed error: %v", err)
	}
	if len(results) != 2 {
		t.Fatalf("expected 2 results, got %d", len(results))
	}
	if equalVectors(results[0].Vector, results[1].Vector) {
		t.Fatal("expected different inputs to produce different vectors")
	}
}

func TestHashProviderModelAndDim(t *testing.T) {
	p := HashProvider{Dim: 32}
	results, err := p.Embed(context.Background(), []string{"x"})
	if err != nil {
		t.Fatalf("Embed error: %v", err)
	}
	r := results[0]
	if r.Model != "local-hash" {
		t.Errorf("Model = %q, want local-hash", r.Model)
	}
	if r.Source != "local-hash" {
		t.Errorf("Source = %q, want local-hash", r.Source)
	}
	if r.Quant != "" {
		t.Errorf("Quant = %q, want empty (unquantized fallback)", r.Quant)
	}
	if r.Dim != 32 || len(r.Vector) != 32 {
		t.Errorf("Dim/vector length = %d/%d, want 32", r.Dim, len(r.Vector))
	}
}

func TestHashProviderDefaultDim(t *testing.T) {
	p := HashProvider{}
	results, err := p.Embed(context.Background(), []string{"x"})
	if err != nil {
		t.Fatalf("Embed error: %v", err)
	}
	if results[0].Dim != 768 || len(results[0].Vector) != 768 {
		t.Errorf("default Dim = %d, want 768", results[0].Dim)
	}
}

func equalVectors(a, b []float32) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func TestOllamaProviderWrapsClient(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"embeddings": [][]float32{{1, 2, 3}},
		})
	}))
	defer server.Close()

	client := ollamakit.New(ollamakit.Config{BaseURL: server.URL, Model: "qwen3-embedding:0.6b"})
	provider := NewOllamaProvider(client, "qwen3-embedding:0.6b", 3)

	results, err := provider.Embed(context.Background(), []string{"hello"})
	if err != nil {
		t.Fatalf("Embed error: %v", err)
	}
	if len(results) != 1 {
		t.Fatalf("expected 1 result, got %d", len(results))
	}
	r := results[0]
	if r.Model != "qwen3-embedding:0.6b" {
		t.Errorf("Model = %q, want qwen3-embedding:0.6b", r.Model)
	}
	if r.Source != "ollama" {
		t.Errorf("Source = %q, want ollama", r.Source)
	}
	if r.Dim != 3 {
		t.Errorf("Dim = %d, want 3", r.Dim)
	}
	if len(r.Vector) != 3 {
		t.Errorf("vector length = %d, want 3", len(r.Vector))
	}
}
