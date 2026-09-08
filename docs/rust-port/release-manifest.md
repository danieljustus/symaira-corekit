# RUST-014 release contract

RUST-014 adds a release plan at [`../../port/release/manifest.json`](../../port/release/manifest.json) and a safe verifier at [`../../port/release/verify.py`](../../port/release/verify.py).

## Tag and version rules

- Repository `vMAJOR.MINOR.PATCH` tags continue to mean Go module releases.
- Rust crates do not receive a second repository tag. The manifest's `planned_publish_order` records the only permitted future Rust publication ordering; it is not a tag namespace or an authorization to publish.
- Every workspace package is classified in the manifest. Only adopted crates may appear in `planned_publish_order`; private test-support crates and non-adopted crates remain non-publishable.
- The manifest records the exact Cargo manifest path and version for every workspace package and checks both against `cargo metadata`.

The checked-in plan maps the current stable repository release (`v0.17.0`) to the adopted `symaira-core-version` crate. Its Cargo version remains `0.0.0` and `publish = false` while exact Git-revision consumption is the supported path. This is intentional: RUST-014 prepares the publication contract without changing consumer pins or pretending that a registry release exists.

## Verification

Run:

```sh
cargo semver-checks check-release
python3 port/release/verify.py --dry-run
python3 -m unittest discover -s port/release -p 'test_*.py'
```

The verifier performs all local checks without `cargo publish` or tag writes:

1. validates the stable Go tag namespace and rejects Rust-specific repository tags;
2. validates manifest schema, adoption evidence, planned publish order and fail-closed publication state;
3. compares every listed package with locked Cargo metadata and checks the pinned workspace;
4. packages each adopted candidate into a temporary target directory and hashes the resulting `.crate` archive;
5. records the resolved source revision, input digests and Cargo metadata as dry-run provenance/SBOM evidence.

`source_revision: HEAD` is allowed only for this local dry-run. A future publication change must replace it with the immutable commit being released, set publication state explicitly in a separately reviewed change, and add public crates.io read-back evidence.

## Status and external gate

Local RUST-014 tooling is complete and wired into normal CI only. The Go-only tag workflow does not run an unpublished Rust release plan. The following are deliberately **not** claimed here:

- no `cargo publish`, repository tag creation, or GitHub release publication was performed;
- crates.io ownership, index visibility, downloaded public bytes and registry checksums cannot be verified locally before publication;
- signing/provenance attestations from an external registry or GitHub OIDC run remain release-time evidence.

Those external checks are the hard gate before changing the manifest from `not-run` or moving any consumer from exact Git revisions to an exact crates.io version. Go build, test, lint, API compatibility, tags and consumer support remain independent and unchanged.
