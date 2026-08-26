# Vendored cross-language contract fixtures

These files are vendored from `symaira-corekit`'s `contracts/` directory —
the Go↔Swift contracts documented in that repo's
`docs/cross-language-conventions.md`. Swift tests in this repo
(`Tests/SymairaUpdateCheckTests/ContractFixtureTests.swift`,
`Tests/SymairaMCPTests/ContractFixtureTests.swift`) assert the Swift
implementation against the same data corekit's own Go tests assert the Go
implementation against, so a port that drifts fails a build instead of
quietly diverging.

## Provenance

| File | Vendored from |
|---|---|
| `update_check_invariants.json` | `symaira-corekit` [`v0.13.0:contracts/update_check_invariants.json`](https://github.com/danieljustus/symaira-corekit/blob/v0.13.0/contracts/update_check_invariants.json) |
| `json_encoding.json` | `symaira-corekit` [`v0.13.0:contracts/json_encoding.json`](https://github.com/danieljustus/symaira-corekit/blob/v0.13.0/contracts/json_encoding.json) |
| `llm_providers.json` | `symaira-corekit` `main:contracts/llm_providers.json` (provider contract issue #172) |
| `llm_errors.json` | `symaira-corekit` `main:contracts/llm_errors.json` (provider contract issue #172) |

`exit_codes.json` and `config_paths.json` are not vendored — neither has an
appkit-side counterpart to assert against (this package has no CLI exit-code
convention, and `SymairaUpdateCheck`'s cache directory is not part of the
documented XDG contract).

## Updating

These are a deliberate copy, not a live fetch, per corekit's own
compatibility policy (`symaira-corekit/contracts/README.md`): pin to a
corekit tag and re-vendor on purpose.

1. Pick the corekit tag to vendor from (usually the version this repo is
   about to bump `SymairaUpdateCheck`/`SymairaMCP` behavior against, or the
   latest release if just refreshing).
2. `curl -sL https://raw.githubusercontent.com/danieljustus/symaira-corekit/<tag>/contracts/<file>.json -o contracts/<file>.json`
   for each vendored file.
3. Update the "Vendored from" table above with the new tag.
4. Run the Swift test suite. A content change that shifts an invariant's
   meaning should make one of the `ContractFixtureTests` fail or its
   `XCTExpectFailure` (if any) unexpectedly pass — either way, read the
   failure before adjusting the Swift code.
