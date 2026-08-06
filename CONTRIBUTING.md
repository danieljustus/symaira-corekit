# Contributing to symaira-corekit

## Development setup

Requirements: Go 1.26 or newer (the module sets `go 1.26.4`).

```sh
make build    # CGO_ENABLED=0 go build ./...
make test     # CGO_ENABLED=0 go test -race ./...
make lint     # gofmt check + go vet
```

All checks must stay green on linux, darwin, and windows (amd64+arm64)
with `CGO_ENABLED=0`. The CI pipeline (`ci.yml`) runs the same gates plus
`govulncheck` and `apidiff` (API compatibility against `main`).

## Releasing

Releases are cut manually; this is an intentional decision to keep the
release step under human control for a shared library. There is no
tag-triggered workflow in CI.

Process for a new `vX.Y.Z` release (strict SemVer; breaking changes
require a major bump and a `BREAKING CHANGE` commit trailer so the
apidiff job skips):

1. **Confirm `main` is green.** All CI checks on `main` must pass:
   test matrix (ubuntu + macos), lint, govulncheck, apidiff.
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
5. **Create the release with notes** derived from the merged PRs since
   the previous tag:
   ```sh
   gh release create vX.Y.Z --title "vX.Y.Z" --notes "…"
   ```
   Summarize user-facing changes (new packages, behavior changes,
   fixes) and link the relevant PRs. Keep the notes in English.
6. **Verify** the release page shows the correct tag, notes, and no
   attached assets unless intended.

## Update policy for consumers

Consumers pin a corekit version in `go.mod` deliberately, but are
expected to move to the latest compatible minor release no later than
their own next release. See `docs/migrations.md` for per-release
changes since v0.3.0.
