# Upstream component evaluation

Research captured 2026-09-06 from current Symaira Rust workspaces and upstream project state. Versions are candidates, not permission to float dependencies; recheck and exact-pin them when each slice starts.

| Area | Candidate | Observed ecosystem evidence | Decision |
|---|---|---|---|
| Serialization | `serde` 1.0.229, `serde_json` 1.0.151 | Already exact-pinned in Browse/Desktop/Vault; Brain is slightly behind | **Adopt and converge deliberately.** Enable `raw_value` where opaque JSON bytes must survive. |
| Errors | `thiserror` 2.0.20 | Exact-pinned in Desktop | **Adopt** for library errors; `anyhow` only in fixture/CLI composition helpers. |
| TOML | `toml` 1.1.5 | Used by Fritz/Browse/Desktop | **Adopt parser only.** Own precedence, zero-value and reflection/tag compatibility logic. |
| Logging | `tracing` / `tracing-subscriber` | Standard Rust stack; consumer configuration differs | **Adopt behind a forced-stderr constructor.** Snapshot text/JSON bytes and level parsing. |
| XDG paths | `directories`/`etcetera` or owned `std::env` logic | CoreKit rules are small and exact | **Prefer owned path resolver.** A general directory crate may silently select platform-native paths instead of the existing XDG contract. |
| Filesystem | `tempfile`, `cap-std`, `fs2` | `tempfile` 3.27.0 already used in Brain | **Use focused helpers; spike `cap-std`.** Preserve symlink, descriptor, rename, mode and Windows behavior explicitly. |
| MCP | official `modelcontextprotocol/rust-sdk`, crate `rmcp` 3.2.0 | Current Go wire pins MCP `2024-11-05`; rmcp primarily targets the newer `2026-07-28` specification while advertising older compatibility | **Adopt only behind owned adapter.** Compatibility claims are not byte parity; keep a raw framing/server path unless the old negotiation, omissions and errors match. |
| JSON Schema | `schemars` plus owned compatibility layer | Go currently derives a constrained schema from types | **Conditional.** Golden schemas outrank derive defaults; reject unsupported kinds and unknown fields exactly. |
| SQLite | current `rusqlite` 0.40.2; EraseMe presently uses 0.37 with `bundled` | The ecosystem pin trails the observed current release and both differ from Go's modernc driver | **Spike first and exact-pin the reviewed result.** Verify SQLite version, DSN/pragmas on every connection, migrations, locks, NULL/time and rollback bytes. Bundled SQLite changes supply-chain/build cost. |
| HTTP | `reqwest` 0.13.4 with Rustls | Used by Fritz | **Adopt behind transport traits.** Enforce redirect policy, TLS floor, body limits, timeout and exact headers ourselves. |
| Archive | `zip` 8.6.0, `tar` 0.4.46, `flate2` 1.1.10 | Used by Brain managed slice | **Adopt behind safe-extraction adapter.** Reject absolute/traversal paths and symlinks before writes. |
| SHA-256 | `sha2` 0.11.0 | Fritz uses 0.11; Brain currently 0.10.9 | **Adopt after convergence check.** Persisted hex/hash-chain bytes must match Go. |
| Secret memory | `zeroize` 1.9, `secrecy` 0.10.3 | Evaluated for Vault | **Adopt where secret values are owned.** Secret-reference parsing itself stays small and sync. |
| Keychain / SymVault | injected process runner using `security` / `symvault` | Existing standalone-first contract | **Preserve shell-out initially.** No compile-time sibling dependency; argv, timeout and error redaction are fixtures. |
| HTML | `html5ever`, `scraper`, optionally `htmd` | Browse has not yet proved byte parity | **No selection yet.** Run complete DOM corpus; write only the missing narrow renderer behavior. |
| Fuzzy text | owned Unicode normalization + `strsim`-class primitives | EvidenceKit offsets and tie-breaking are custom contract | **Own orchestration.** A crate may supply Levenshtein primitives only after exact offsets/scores match. |
| Vector codec | owned implementation; optional `wide`/portable SIMD later | TurboQuant persisted bit packing and seeded rotation are proprietary format contracts | **Port owned safe Rust first.** Optimize only after byte parity and benchmarks; no unsafe SIMD initially. |
| Cosign | existing `cosign` subprocess | Go behavior verifies exact checksum bytes and identity regex | **Preserve subprocess adapter.** Do not embed a large Sigstore stack until it proves a smaller, safer operational contract. |
| Dependency policy | `cargo-deny`, `cargo-audit`, `cargo-semver-checks`, `cargo-hack`, `cargo-nextest`, `cargo-llvm-cov` | Standard gates in current Rust ports | **Adopt exact-pinned tooling in CI/bootstrap docs.** |

## Reuse decision

Do not adopt a foreign umbrella “core” framework. CoreKit's value is its stable Symaira contracts, not generic wrappers. Reuse focused crates behind narrow adapters and extract only after demand is proven.

## Mandatory feasibility spikes

1. **Filesystem spike:** atomic replacement, symlink/race resistance, file modes and Windows semantics. Stop if safe parity needs broad owned unsafe code.
2. **MCP spike:** Content-Length and newline compatibility, 1 MiB boundary, typed-schema output, tool-result `_meta`, cancellation and zero stdout pollution.
3. **SQLite spike:** persisted DB/pragmas/migration/locking comparison between modernc SQLite and bundled Rust SQLite on native platforms.
4. **Update spike:** redirect/TLS/body limits, safe extraction, checksum bytes, Cosign argv, atomic swap and rollback.
5. **DOM/vector spikes:** exact bytes plus p95/throughput gate before selecting parser or optimization strategy.

A private fork is acceptable only if the delta is small, upstreamable and covered by differential tests. A broad permanent fork fails the stop rule.