# Contributing to symaira-corekit

## Development setup

Requirements: the Rust toolchain pinned in `rust-toolchain.toml` and Python 3.12
or newer for the contract harness. No Go toolchain is needed on `main`; the Go
library was retired after v0.18.3 ([ADR 0005](docs/adr/0005-go-library-retirement.md)).

```sh
make build    # cargo build --workspace --all-targets --locked
make test     # cargo test --workspace --all-features --locked
make lint     # cargo fmt --check + clippy -D warnings
make rust-contracts
make rust-hardening
```

The authoritative gate list is `.github/workflows/ci.yml`: Rust build/test,
format, dependency audit, port contracts, native Rust foundation/LLM/update,
MCP, MCP-config and SQLite checks, hardening/Miri and release-manifest
validation. PR and `main` native matrices cover Linux and Apple Silicon macOS.
Windows and macOS Intel are unsupported and have no CI or release targets.
Run the affected `rust-*-contract` Make targets before pushing Rust changes.

The Go module is no longer maintained: `v0.18.3` is its final release, and
the `release/v0.18` maintenance branch has been removed.

## Releasing

The maintainer deliberately creates and pushes a release tag. The tag-triggered
`.github/workflows/release.yml` then verifies the tagged commit and creates the
GitHub release with generated notes. It requires an exact `## vX.Y.Z` heading
in `docs/migrations.md` for that tag.

1. **Confirm `main` is green.** All CI checks on `main` must pass, including
   the `merge gate` context.
2. **Run the full local gates:**
   ```sh
   make build test lint rust-contracts
   ```
3. **Check consumers:**
   ```sh
   make consumer-drift
   ```
4. **Tag and push:**
   ```sh
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```
5. **Verify the release workflow and generated notes:**
   ```sh
   gh release view vX.Y.Z
   ```
   Keep release notes in English and check the page has no unintended assets.

## Update policy for consumers

Rust consumers pin an exact Git revision plus `Cargo.lock` (ADR 0002) and are
expected to move to the latest CoreKit revision no later than their own next
release. Go consumers stay on `v0.18.x`. See `docs/migrations.md`.
