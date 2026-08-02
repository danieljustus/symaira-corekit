package embedkit

import (
	"errors"
	"fmt"
	"math"
)

var (
	// ErrInvalidDimension reports a target dimension that is not a positive
	// prefix of the input vector.
	ErrInvalidDimension = errors.New("embedkit: invalid target dimension")
	// ErrInvalidVector reports a vector containing a non-finite value.
	ErrInvalidVector = errors.New("embedkit: invalid vector")
	// ErrZeroNorm reports a vector whose selected prefix has no length and
	// therefore cannot be L2-normalized.
	ErrZeroNorm = errors.New("embedkit: zero-norm vector")
)

// PinDimension truncates result.Vector to targetDim dimensions and L2-normalizes
// the truncated vector. The returned Result preserves the source, model, and
// quantization metadata and updates Dim to targetDim.
//
// targetDim must be in [1, len(result.Vector)]. A target larger than the
// provider vector is rejected rather than padded, because padding would
// invent embedding coordinates. The input Result and its vector are never
// modified. Non-finite values and a zero-norm selected prefix are rejected.
func PinDimension(result Result, targetDim int) (Result, error) {
	if targetDim <= 0 || targetDim > len(result.Vector) {
		return Result{}, fmt.Errorf("%w: target=%d, source=%d", ErrInvalidDimension, targetDim, len(result.Vector))
	}

	prefix := result.Vector[:targetDim]
	normSquared := 0.0
	for i, value := range prefix {
		value64 := float64(value)
		if math.IsNaN(value64) || math.IsInf(value64, 0) {
			return Result{}, fmt.Errorf("%w: non-finite value at index %d", ErrInvalidVector, i)
		}
		normSquared += value64 * value64
	}
	if normSquared == 0 {
		return Result{}, ErrZeroNorm
	}

	norm := math.Sqrt(normSquared)
	if math.IsInf(norm, 0) || math.IsNaN(norm) {
		return Result{}, fmt.Errorf("%w: norm is not finite", ErrInvalidVector)
	}

	pinned := make([]float32, targetDim)
	for i, value := range prefix {
		pinned[i] = float32(float64(value) / norm)
	}

	result.Vector = pinned
	result.Dim = targetDim
	return result, nil
}
