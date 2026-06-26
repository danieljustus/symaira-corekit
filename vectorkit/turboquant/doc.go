// Package turboquant implements TurboQuant-style scalar quantization for
// approximate nearest-neighbor vector search. It applies a deterministic
// random rotation (a Walsh-Hadamard transform with random sign flips)
// followed by per-block scalar quantization to 2, 3, or 4 bits, plus
// optional 2.5-bit and 3.5-bit channel-split modes. The package is
// standalone and CGO-free (standard library only) so it can be embedded in
// any tool's vector-search or storage pipeline.
//
// It exposes a small, stable surface:
//
//   - Codec / NewCodec — configure dimension, bit width, rotation seed.
//   - Encode / Decode — quantize a float32 vector and reconstruct it.
//   - Score / ScoreCosine — estimate inner-product / cosine similarity
//     directly from a packed code without full reconstruction.
//   - Metadata + MarshalMetadata / UnmarshalMetadata / CodecFromMetadata —
//     deterministic codec configuration that survives serialization.
//   - SidecarMeta + EncodeSidecar / DecodeSidecar / UnpackSidecarBlob /
//     ValidateSidecarMeta — a self-describing blob+JSON layout consumers can
//     persist alongside their own records (e.g. a database sidecar column).
//   - RunBenchmark and friends — a reproducible recall/compression/MSE harness.
//
// Storage layout is owned by the consumer. SidecarMeta carries JSON tags so a
// consumer can map it onto its own storage schema; this package deliberately
// does not depend on any database, persistence, or search engine.
//
// Design decisions vs. the full TurboQuant paper (arXiv:2504.19874):
//
//   - A Walsh-Hadamard transform with random sign flips is used instead of a
//     full random orthogonal matrix. This is O(d log d) and spreads vector
//     energy uniformly, which is the paper's key goal; a Gaussian random
//     orthogonal matrix would be O(d^3) to construct.
//
//   - Per-block scalar quantization with uniform (min-max) bins is used rather
//     than the paper's product-quantization codebooks. This is simpler to
//     implement and reason about, and for 2-4 bits the recall difference is
//     modest. The trade-off is measured by the benchmark harness.
//
//   - The paper's asymmetric distance computation and full reranking pipeline
//     are not implemented beyond the inner-product estimator; an exact-rerank
//     comparison mode is included in the benchmark for reference.
//
//   - The optional 2.5-bit and 3.5-bit modes use channel splitting (half the
//     dimensions at one bit width, half at the next) rather than true
//     fractional bits, keeping the implementation clear and testable.
//
// Origin and license: this is an original, first-party implementation written
// for the Symaira tools. It implements ideas from the public TurboQuant paper
// (arXiv:2504.19874) but copies no external source code, so it is distributed
// under this repository's Apache-2.0 license without third-party obligations.
package turboquant
