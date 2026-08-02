package embedkit

import (
	"errors"
	"math"
	"reflect"
	"testing"
)

func TestPinDimensionTruncatesAndRenormalizes(t *testing.T) {
	original := Result{
		Vector: []float32{3, 4, 12},
		Source: "ollama",
		Model:  "qwen3-embedding:0.6b",
		Dim:    3,
		Quant:  "4bit-mlx",
	}

	pinned, err := PinDimension(original, 2)
	if err != nil {
		t.Fatalf("PinDimension error: %v", err)
	}

	wantVector := []float32{0.6, 0.8}
	if !reflect.DeepEqual(pinned.Vector, wantVector) {
		t.Errorf("Vector = %v, want %v", pinned.Vector, wantVector)
	}
	if pinned.Dim != 2 {
		t.Errorf("Dim = %d, want 2", pinned.Dim)
	}
	if pinned.Source != original.Source || pinned.Model != original.Model || pinned.Quant != original.Quant {
		t.Errorf("metadata changed: got source=%q model=%q quant=%q", pinned.Source, pinned.Model, pinned.Quant)
	}
	if !reflect.DeepEqual(original.Vector, []float32{3, 4, 12}) || original.Dim != 3 {
		t.Errorf("PinDimension modified its input: %+v", original)
	}
}

func TestPinDimensionHasUnitNormAndPreservesRelativeDirection(t *testing.T) {
	original := Result{Vector: []float32{1, -2, 3, 4}, Dim: 4}
	pinned, err := PinDimension(original, 3)
	if err != nil {
		t.Fatalf("PinDimension error: %v", err)
	}

	if got := vectorNorm(pinned.Vector); math.Abs(got-1) > 1e-6 {
		t.Errorf("pinned vector norm = %.9f, want 1", got)
	}

	// The normalized result must point in the same direction as the selected
	// prefix of the untruncated vector, even though its length changed.
	prefixNorm := vectorNorm(original.Vector[:3])
	for i, value := range original.Vector[:3] {
		want := float64(value) / prefixNorm
		if got := float64(pinned.Vector[i]); math.Abs(got-want) > 1e-6 {
			t.Errorf("pinned[%d] = %.9f, want %.9f", i, got, want)
		}
	}

	// A direction comparison is independent of the prefix's original length.
	if got := dot(pinned.Vector, original.Vector[:3]) / prefixNorm; math.Abs(got-1) > 1e-6 {
		t.Errorf("relative direction cosine = %.9f, want 1", got)
	}
}

func TestPinDimensionUnnormalizedTruncationChangesDotSimilarity(t *testing.T) {
	// Both provider vectors are unit-normalized. Truncating the first vector
	// to one coordinate leaves a length of 0.6; dot-product similarity therefore
	// changes unless the truncated vector is normalized again.
	first := Result{Vector: []float32{0.6, 0.8}, Dim: 2}
	second := Result{Vector: []float32{1, 0}, Dim: 2}

	firstPinned, err := PinDimension(first, 1)
	if err != nil {
		t.Fatalf("PinDimension(first) error: %v", err)
	}
	secondPinned, err := PinDimension(second, 1)
	if err != nil {
		t.Fatalf("PinDimension(second) error: %v", err)
	}

	unnormalizedScore := dot(first.Vector[:1], second.Vector[:1])
	normalizedScore := dot(firstPinned.Vector, secondPinned.Vector)
	if math.Abs(unnormalizedScore-0.6) > 1e-6 {
		t.Fatalf("unrenormalized score = %.9f, want 0.6", unnormalizedScore)
	}
	if math.Abs(normalizedScore-1) > 1e-6 {
		t.Fatalf("renormalized score = %.9f, want 1", normalizedScore)
	}
	if math.Abs(unnormalizedScore-normalizedScore) < 1e-6 {
		t.Fatalf("truncation without renormalization did not change similarity: %.9f vs %.9f", unnormalizedScore, normalizedScore)
	}
}

func TestPinDimensionRejectsInvalidInputs(t *testing.T) {
	tests := []struct {
		name      string
		result    Result
		targetDim int
		wantErr   error
	}{
		{
			name:      "zero target",
			result:    Result{Vector: []float32{1, 2}},
			targetDim: 0,
			wantErr:   ErrInvalidDimension,
		},
		{
			name:      "negative target",
			result:    Result{Vector: []float32{1, 2}},
			targetDim: -1,
			wantErr:   ErrInvalidDimension,
		},
		{
			name:      "target larger than source",
			result:    Result{Vector: []float32{1, 2}},
			targetDim: 3,
			wantErr:   ErrInvalidDimension,
		},
		{
			name:      "empty source",
			result:    Result{Vector: nil},
			targetDim: 1,
			wantErr:   ErrInvalidDimension,
		},
		{
			name:      "zero norm after truncation",
			result:    Result{Vector: []float32{0, 0, 1}},
			targetDim: 2,
			wantErr:   ErrZeroNorm,
		},
		{
			name:      "zero norm source",
			result:    Result{Vector: []float32{0, 0}},
			targetDim: 2,
			wantErr:   ErrZeroNorm,
		},
		{
			name:      "nan",
			result:    Result{Vector: []float32{float32(math.NaN())}},
			targetDim: 1,
			wantErr:   ErrInvalidVector,
		},
		{
			name:      "positive infinity",
			result:    Result{Vector: []float32{float32(math.Inf(1))}},
			targetDim: 1,
			wantErr:   ErrInvalidVector,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if _, err := PinDimension(tt.result, tt.targetDim); !errors.Is(err, tt.wantErr) {
				t.Fatalf("PinDimension error = %v, want errors.Is(..., %v)", err, tt.wantErr)
			}
		})
	}
}

func vectorNorm(vector []float32) float64 {
	var sum float64
	for _, value := range vector {
		sum += float64(value) * float64(value)
	}
	return math.Sqrt(sum)
}

func dot(a, b []float32) float64 {
	if len(a) != len(b) {
		panic("dot: vector length mismatch")
	}
	var sum float64
	for i := range a {
		sum += float64(a[i]) * float64(b[i])
	}
	return sum
}
