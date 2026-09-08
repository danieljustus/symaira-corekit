# RUST-014 release contract

RUST-014 adds a release plan at [`../../port/release/manifest.json`](../../port/release/manifest.json) and a safe verifier at [`../../port/release/verify.py`](../../port/release/verify.py).

## Tag and version rules

- Repository `vMAJOR.MINOR.PATCH` tags continue to mean Go module releases.
- Rust crates do not receive a second repository tag. The manifest's `planned_publish_order` records the only permitted future Rust publication ordering; it is not a tag namespace or an authorization to publish.
- Every workspace package is classified in the manifest. Only adopted crates may appear in `planned_publish_order`; private test-support crates and non-adopted crates remain non-publishable.
- The manifest records the exact Cargo manifest path and version for every workspace package and checks both against `cargo metadata`.

The checked-in plan maps the current stable repository release (`v0.17.0`) to the adopted `symaira-core-version` crate at `0.1.0`. That crate has public crates.io metadata and `publish = true`, while the release plan's top-level `publish = false` and `publication_status = "not-run"` keep this PR non-publishing. All non-adopted workspace crates, including test-support crates, remain `publish = false`.

## Verification

Run:

```sh
cargo semver-checks check-release --package symaira-core-version \
  --baseline-rev HEAD^ --release-type minor
python3 port/release/verify.py --dry-run
cargo publish --dry-run --locked --allow-dirty --package symaira-core-version
python3 -m unittest discover -s port/release -p 'test_*.py'
```

The verifier performs all local checks without `cargo publish` or tag writes. Its
focused tests also exercise the fail-closed public/private metadata and release
state rules:

1. validates the stable Go tag namespace and rejects Rust-specific repository tags;
2. validates manifest schema, adoption evidence, planned publish order and fail-closed publication state;
3. compares every listed package with locked Cargo metadata, checks public metadata for the publish candidate, and requires every other crate to remain private;
4. packages each adopted candidate into a temporary target directory and hashes the resulting `.crate` archive;
5. records the resolved source revision, input digests and Cargo metadata as dry-run provenance/SBOM evidence.

CI additionally runs `cargo publish --dry-run --locked -p symaira-core-version` as the registry-package validation gate. This command performs no upload.

`source_revision: HEAD` is allowed only for this local dry-run. A future publication change must replace it with the immutable commit being released, set publication state explicitly in a separately reviewed change, and add public crates.io read-back evidence.

## Status and external gate

Local RUST-014 tooling is complete and wired into normal CI only. The Go-only tag workflow does not run an unpublished Rust release plan. The following are deliberately **not** claimed here:

- no `cargo publish`, repository tag creation, or GitHub release publication was performed;
- crates.io ownership, index visibility, downloaded public bytes and registry checksums cannot be verified locally before publication;
- signing/provenance attestations from an external registry or GitHub OIDC run remain release-time evidence.

Those external checks are the hard gate before changing the manifest from `not-run` or moving any consumer from exact Git revisions to an exact crates.io version. Go build, test, lint, API compatibility, tags and consumer support remain independent and unchanged.
