# ADR RUST-003: Frozen candidate-source scope

- **Decision:** the frozen SQLite candidate manifest keeps recording the full
  forensic source set, but verification binds only the *enforced* port inputs:
  the workspace build inputs (`Cargo.toml`, `Cargo.lock`,
  `rust-toolchain.toml`, `.cargo/**` when present), the crate under test
  (`rust/symaira-core-sqlite/**`), its workspace path dependencies
  (`rust/symaira-core-fs/**`) and the Go oracle, migration corpus and harness
  (`scripts/rust-port/sqlite/**`). Everything else that `snapshot()` records is
  context, not a build input, and cannot invalidate retained evidence by itself.
- **Reason:** the previous whole-class scope also enforced
  `.github/workflows/ci.yml`, `.gitattributes` and every unrelated Rust crate,
  so a workflow-only or unrelated-crate edit failed 10 of the acceptance tests
  with `frozen source manifest is not bound to the current candidate source`.
  None of those files can change the built example's bytes or the compared
  observations, so the failure was scope drift, not a quality signal, and it
  forced a full Go/Rust recapture for routine dependency maintenance.
- **Retained strength:** `Cargo.toml`, `Cargo.lock` and `rust-toolchain.toml`
  stay enforced because they change the compiled artifact; a lockfile or
  toolchain change therefore still requires a recapture. The harness's own
  files stay enforced, so acceptance tests cannot be weakened without an
  explicit, reviewed re-freeze. `validate_scope()` walks the transitive path
  dependencies of the crate under test and rejects a manifest that does not
  cover them, so a new workspace path dependency forces a scope decision
  instead of silently verifying an incomplete input set.
- **Caller contract:** `snapshot()` remains the freeze operation
  (`scripts/rust-port/sqlite/candidate.py`); `enforced()` is its binding view.
  A genuine port-input change is handled by the documented recapture path
  `make rust-sqlite-refreeze`, which regenerates the manifest and writes a new
  differential capture to a new file. Generation is never approval: the new
  manifest and capture require independent review, and the acceptance tests are
  repointed in a separate reviewed change.
- **Verification:** `scripts/rust-port/sqlite/test_acceptance.py` asserts the
  enforced class (build inputs, port sources) and the forensic class
  (CI workflow, `.gitattributes`, unrelated crates) explicitly, proves that
  forensic-class drift still passes the current capture, proves that
  co-mutated enforced-class drift is rejected, and controls the
  dependency-closure guard.

## File classes

| Class | Files | Enforced | Consequence of a change |
|---|---|---|---|
| Build inputs | `Cargo.toml`, `Cargo.lock`, `rust-toolchain.toml`, `.cargo/**` | yes | Recapture required (changes the built artifact) |
| Port under test | `rust/symaira-core-sqlite/**`, `rust/symaira-core-fs/**` | yes | Recapture required |
| Oracle and harness | `scripts/rust-port/sqlite/**` | yes | Recapture required |
| CI orchestration | `.github/workflows/ci.yml` | no | No invalidation; recorded for forensics |
| Checkout attributes | `.gitattributes` | no | No invalidation; effects appear through the hashed files |
| Unrelated crates | `rust/symaira-core-{config,env,exit,log,mcp,secretref,version}/**`, `rust/test-support/**` | no | No invalidation; recorded for forensics |
