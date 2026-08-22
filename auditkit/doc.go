// Package auditkit provides the shared audit-log infrastructure for Symaira
// tools: a tamper-evident hash chain over JSONL entries and an append-only
// file sink with size-based rotation.
//
// Scope (deliberately narrow — no tool-specific logic):
//   - HashEntry / VerifyChain: SHA-256 chaining over entry lines
//   - ChainAnchor checkpoints (separate file, atomic replace) to detect
//     truncation of the log tail — chaining alone only detects modification
//   - Sink: append-only JSONL writer with rotation and fsync semantics
//
// Domain models stay with the consumers: brain's redacting gateway logger
// and guard's case bundles enrich the sink entries with their own schemas.
//
// Standalone-first: standard library only.
package auditkit
