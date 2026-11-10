# ADR 0006: Merge the AppKit repository into CoreKit

Status: accepted, 2026-11-10, by the maintainer. Supersedes the "separate
CoreKit/AppKit repositories" rule of PB-2026-09-09 revisions 1 to 5
(revision 6 records this decision).

## Decision

`symaira-appkit` is merged into `symaira-corekit`. CoreKit becomes the single
shared-library repository for Symaira: Rust crates for the backends and the
Swift package for the native clients.

- **History:** the complete AppKit history (165 non-merge commits up to
  `d936070`) was rewritten into the `appkit/` subdirectory and replayed
  linearly onto CoreKit `main`, so `git log -- appkit/` shows every original
  change with its original author and date. The resulting `appkit/` tree is
  byte-identical to AppKit `d936070` before the integration commit.
- **Layout:** Swift sources, tests, scripts, brand assets and GUI rules live
  under `appkit/`. `Package.swift` sits at the repository root because SwiftPM
  resolves a remote package only from the repository root; its targets point
  into `appkit/` with explicit paths.
- **Package identity:** consumers depend on
  `https://github.com/danieljustus/symaira-corekit` and reference products
  with `package: "symaira-corekit"`. Product and module names are unchanged
  (`SymairaTheme`, `SymairaCLIRunner`, `SymairaToolKit`, `SymairaKeychain`,
  `SymairaUpdateCheck`, `SymairaDaemonKit`, `SymairaIngestContract`,
  `SymairaMCP`, `SymairaProviderKit`). The SwiftPM resource bundle is now
  `symaira-corekit_SymairaTheme.bundle`; packaging scripts that copy the old
  `symaira-appkit_SymairaTheme.bundle` must be updated with the pin.
- **Versioning:** one tag series for the whole repository. The first release
  containing the Swift package is `v0.20.0`; SwiftPM accepts the `v` prefix,
  so Swift consumers pin `exact: "0.20.0"`. Rust consumers keep pinning a
  40-character revision (ADR 0002). A tag does not force Rust and Swift
  consumers to move together. AppKit's own tags (`0.1.0` to `0.18.1`) stay in
  the archived AppKit repository and are not imported.
- **Contracts:** the vendored `appkit/contracts/` copies are removed. Swift
  contract tests read the authoritative `contracts/*.json` directly. The
  bundled `llm_providers.json` resource of `SymairaProviderKit` stays, and its
  test now compares it with the canonical fixture.
- **CI:** `.github/workflows/swift.yml` runs the former AppKit gates on the
  self-hosted Apple Silicon runner (label `macbook-corekit`) whenever
  `Package.swift`, `appkit/**`, `contracts/**` or the workflow changes. Fork
  pull requests never reach the self-hosted runner. The Rust CI is unchanged.
  CodeQL analyzes Swift on the same runner.
- **Module rules:** unchanged. A Swift module still needs two genuine
  consumers, no product-domain views, no third-party dependencies and no
  cloud/SaaS code.
- **AppKit repository:** after the first CoreKit release with the Swift
  package, open AppKit issues are transferred to CoreKit, the AppKit README
  points here and the repository is archived. Archived tags remain resolvable,
  so consumers that have not yet switched keep building.

## Reasoning

AppKit and CoreKit already shared conventions, contracts and release
discipline, and AppKit's update-check, MCP and provider modules are Swift
twins of CoreKit contracts. Two repositories meant vendored fixture copies,
two issue trackers, two release processes and cross-repo PR pairs for one
contract change. One repository makes a contract change and both language
implementations one reviewable commit.

## Consequences

- Swift consumers switch URL, package name and exact version in one change
  per consumer and update any packaging step that copies the theme resource
  bundle.
- SwiftPM and Cargo clone the whole repository; Rust consumers also fetch the
  AppKit sources and brand assets, Swift consumers the Rust workspace. Both
  only build what they reference.
- `docs/consumers.json` keeps tracking the Rust/Go consumers its verifier
  understands; Swift pins are listed in `docs/migrations.md` for `v0.20.0`.
