package embedkit

import (
	"context"
	"hash/fnv"
	"strconv"

	"github.com/danieljustus/symaira-corekit/ollamakit"
)

// Provider embeds input strings and returns a Result per input, in order.
type Provider interface {
	Embed(ctx context.Context, inputs []string) ([]Result, error)
}

// defaultHashDim is used by HashProvider when Dim is left at its zero value.
const defaultHashDim = 768

// HashProvider is a deterministic, dependency-free fallback embedder. It
// never calls a network service; the same input always produces the same
// vector. Its Model is always "local-hash" so SameSpace never conflates a
// fallback embedding with a real model's output, regardless of which real
// model name was configured elsewhere.
type HashProvider struct {
	// Dim is the target vector width. Zero uses defaultHashDim.
	Dim int
}

// Embed implements Provider.
func (h HashProvider) Embed(_ context.Context, inputs []string) ([]Result, error) {
	dim := h.Dim
	if dim == 0 {
		dim = defaultHashDim
	}
	results := make([]Result, len(inputs))
	for i, in := range inputs {
		results[i] = Result{
			Vector: hashVector(in, dim),
			Source: "local-hash",
			Model:  "local-hash",
			Dim:    dim,
		}
	}
	return results, nil
}

// hashVector deterministically derives a dim-length vector from s using
// FNV-1a, seeding each dimension with the input plus its index so the
// dimensions are not simply repeats of one hash value.
func hashVector(s string, dim int) []float32 {
	vec := make([]float32, dim)
	for i := 0; i < dim; i++ {
		h := fnv.New32a()
		h.Write([]byte(s))               //nolint:gosec // best-effort write; error not actionable
		h.Write([]byte(strconv.Itoa(i))) //nolint:gosec // best-effort write; error not actionable
		sum := h.Sum32()
		// Map uint32 to [-1, 1].
		vec[i] = float32(sum)/float32(1<<31) - 1
	}
	return vec
}

// OllamaProvider adapts an ollamakit.Client to the Provider interface,
// pinning a model name and target dimension (0 = the model's native
// dimensionality, forwarded via ollamakit.Client.EmbedWithDim).
type OllamaProvider struct {
	client *ollamakit.Client
	model  string
	dim    int
}

// NewOllamaProvider returns a Provider backed by client, embedding with
// model at the given dim (0 = native dimensionality).
func NewOllamaProvider(client *ollamakit.Client, model string, dim int) *OllamaProvider {
	return &OllamaProvider{client: client, model: model, dim: dim}
}

// Embed implements Provider.
func (p *OllamaProvider) Embed(ctx context.Context, inputs []string) ([]Result, error) {
	vectors, err := p.client.EmbedWithDim(ctx, p.model, inputs, p.dim)
	if err != nil {
		return nil, err
	}
	results := make([]Result, len(vectors))
	for i, v := range vectors {
		results[i] = Result{
			Vector: v,
			Source: "ollama",
			Model:  p.model,
			Dim:    len(v),
		}
	}
	return results, nil
}
