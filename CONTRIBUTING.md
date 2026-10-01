# Contributing to symaira-corekit

## Development setup

Requirements: Go 1.26 or newer (the module sets `go 1.26.4`), golangci-lint,
and the Rust toolchain pinned in `rust-toolchain.toml` for Rust changes.

```sh
make build    # CGO_ENABLED=0 go build ./...
make test     # CGO_ENABLED=1 go test -race ./...
make lint     # golangci-lint + gofmt check + go vet
make rust-lint
make rust-test
```

The Go build must remain CGO-free on linux, darwin, and windows (amd64+arm64).
Race tests use CGO; CI also runs tests with `CGO_ENABLED=0`. The authoritative
gate list is `.github/workflows/ci.yml`: Go test and cross-build matrices,
lint, `govulncheck`, `apidiff`, port contracts, native Rust foundation/LLM/update,
MCP, MCP-config and SQLite checks, hardening/Miri and release-manifest validation.
The full `main` matrix includes Linux, macOS and Windows. Run the affected
`rust-*-contract` Make targets before pushing Rust changes.

## Releasing

The maintainer deliberately creates and pushes a release tag. The tag-triggered
`.github/workflows/release.yml` then verifies the tagged commit and creates the
GitHub release with generated notes. It requires an exact `## vX.Y.Z` heading
in `docs/migrations.md` for that tag.

Process for a new `vX.Y.Z` release (strict SemVer; breaking changes
require a major bump and a `BREAKING CHANGE` commit trailer so the
apidiff job skips):

1. **Confirm `main` is green.** All CI checks on `main` must pass:
   all configured Go and Rust platform jobs, lint, govulncheck and apidiff.
2. **Run the full local gates:**
   ```sh
   make test
   make lint
   make build
   ```
3. **Check consumer drift** — every sibling Symaira repo that pins
   corekit and is checked out alongside this one:
   ```sh
   make consumer-drift
   ```
   The list should be empty or contain only intentional pins.
4. **Tag and push:**
   ```sh
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```
5. **Verify the release workflow and generated notes** derived from merged PRs:
   ```sh
   gh release view vX.Y.Z
   ```
   Review user-facing changes and linked PRs; edit the generated notes if
   necessary. Keep release notes in English.
6. **Verify** the release page shows the correct tag, notes, and no
   attached assets unless intended.

## Update policy for consumers

Consumers pin a corekit version in `go.mod` deliberately, but are
expected to move to the latest compatible minor release no later than
their own next release. See `docs/migrations.md` for per-release
changes since v0.3.0.
