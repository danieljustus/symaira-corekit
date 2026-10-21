# ADR RUST-004: Bind the lockfile through the dependency closure

- **Decision:** frozen FS/SEC and SQLite evidence no longer binds the raw
  `Cargo.lock` bytes. It binds `Cargo.lock#dependency-closure`: the SHA-256 of
  the canonical JSON of every lockfile package reachable from the crates under
  test, plus the lockfile format version
  (`scripts/rust-port/lock_closure.py`). The raw `Cargo.lock` hash is still
  recorded as forensic context in the SQLite manifest.
- **Reason:** the whole-file binding made every lockfile change invalidate
  native Go-oracle evidence, including changes to crates the bound code cannot
  compile against. Two consecutive TLS advisories (RUSTSEC-2026-0346..0349 in
  `rustls`, RUSTSEC-2026-0381..0383 in `rustls-webpki`/`webpki-roots`) each
  forced a full native recapture and re-registration, although no FS/SEC or
  SQLite crate depends on any TLS crate; only `symaira-core-llm` and
  `symaira-core-update` do. This is the same scope drift ADR RUST-003 removed
  for unrelated source files.
- **Retained strength:** the closure follows every lockfile dependency edge,
  including dev and build edges, so it is a superset of what the bound crates
  can resolve. Any change to a reachable package (version, source, checksum or
  its own edges) still invalidates evidence and requires a recapture. An edge
  that does not resolve to exactly one package, a missing root crate or a
  malformed lockfile fails closed. `Cargo.toml`, `rust-toolchain.toml` and the
  closure derivation itself stay enforced.
- **Roots:** SQLite binds the closure of `symaira-core-sqlite`. FS/SEC binds the
  closure of the package names declared by every crate in
  `fs_secret_oracle.RUST_INPUT_DIRS`, so adding a bound crate extends the
  closure automatically.
- **Verification:** `scripts/rust-port/sqlite/test_acceptance.py` and
  `scripts/rust-port/test_fs_secret_oracle.py` prove that a change to an
  unreachable package keeps the digest, that a change to a reachable package
  invalidates the binding, and that unresolvable or empty lockfiles are
  rejected.
- **Transition:** introducing the derived binding changes the enforced inputs
  once, so the frozen FS/SEC and SQLite records are re-registered together
  with this decision. Later lockfile updates outside the closure need no
  recapture.

## Updated file classes (SQLite)

| Class | Files | Enforced | Consequence of a change |
|---|---|---|---|
| Build inputs | `Cargo.toml`, `Cargo.lock#dependency-closure`, `rust-toolchain.toml`, `.cargo/**`, `scripts/rust-port/lock_closure.py` | yes | Recapture required |
| Raw lockfile | `Cargo.lock` bytes | no | No invalidation unless the closure digest changes |

All other classes in [ADR RUST-003](adr-rust-003-candidate-source-scope.md)
are unchanged.
