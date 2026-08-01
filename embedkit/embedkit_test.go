package embedkit

import "testing"

func TestSameSpace(t *testing.T) {
	base := Result{Vector: []float32{1, 2, 3}, Source: "ollama", Model: "qwen3-embedding:0.6b", Dim: 768, Quant: ""}

	tests := []struct {
		name string
		a, b Result
		want bool
	}{
		{
			name: "identical model and quantization",
			a:    base,
			b:    base,
			want: true,
		},
		{
			name: "same model name, different quantization (4bit MLX vs unquantized Ollama)",
			a:    Result{Model: "qwen3-embedding:0.6b", Quant: "", Dim: 768},
			b:    Result{Model: "qwen3-embedding:0.6b", Quant: "4bit-mlx", Dim: 768},
			want: false,
		},
		{
			name: "different model, same quantization",
			a:    Result{Model: "qwen3-embedding:0.6b", Quant: "", Dim: 768},
			b:    Result{Model: "mxbai-embed-large", Quant: "", Dim: 768},
			want: false,
		},
		{
			name: "same model and quantization, different dimension",
			a:    Result{Model: "qwen3-embedding:0.6b", Quant: "", Dim: 768},
			b:    Result{Model: "qwen3-embedding:0.6b", Quant: "", Dim: 1024},
			want: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := SameSpace(tt.a, tt.b); got != tt.want {
				t.Errorf("SameSpace(%+v, %+v) = %v, want %v", tt.a, tt.b, got, tt.want)
			}
		})
	}
}
