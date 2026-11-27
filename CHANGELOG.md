# Changelog

The GitHub Releases page is the authoritative source for complete release notes.

## Unreleased

- Swift design kit: iOS type roles are 15 / 13.5 larger instead of 17 / 13.5,
  so body text is 15 pt at the default Dynamic Type size (#523); the 17 pt of
  v0.28.0 read as oversized in dense screens. `symairaFormRowControl()` now
  changes nothing outside macOS, where a stacked iOS form row let the control
  overlap its label (#524).

## v0.28.0 — 2026-11-27

- Swift design foundation, after a review against the UI literature
  (Refactoring UI, Practical UI, Thinking with Type, Designing with the Mind in
  Mind): readable running text (`proseMeasure`, token line heights), a 3:1
  `control-outline` for control boundaries, a token-based destructive button
  role, iOS type at Apple's 17 pt body size, and token spec, guidelines and code
  aligned again (#512 to #516). Details in `swift/CHANGELOG.md`.
- Consumers: `dependabot-corekit` also aligns nested Swift packages. When a
  root `Package.swift` depends on a local package (`.package(path:)`) that pins
  CoreKit too, Dependabot can move only the local package and the root stops
  resolving (seen in symaira-cockpit #435). `corekit_pins.py --fix` now raises
  every tracked `Package.swift` to the highest CoreKit pin and rewrites a
  tracked `Package.resolved` next to it with the release tag's commit.
- Consumers: `dependabot-corekit` repairs partly moved Cargo lockfiles. For
  `[workspace.dependencies]` pins Dependabot moved one of seven crates in
  `Cargo.lock` (symaira-desktop #1412) and never touches a second workspace
  such as `fuzz/`. `corekit_pins.py --fix` now sets every CoreKit tag to the
  highest one found and lets `cargo metadata` re-resolve each stale
  `Cargo.lock` minimally; only the CoreKit `source` lines move.
- Rust migration: Desktop v0.13.3 is recorded as a Git-pinned Rust-only
  consumer in `docs/consumers.json` (Go retired, standalone report pinned;
  #370). Brain and Vault releases are still pending.
- Swift design kit: the web catalogue test no longer races the dialog's queued
  `close` event and documents its server root (#517).

## v0.27.1 — 2026-11-26

- Consumers: composite action `.github/actions/dependabot-corekit` lands a
  CoreKit-only Dependabot pull request. It copies the new version into the
  files Dependabot never edits (XcodeGen `project.yml`, a
  `[workspace.dependencies]` tag in `Cargo.toml`), pushes that commit with a
  repository deploy key so the pull request's CI runs on it, and enables
  auto-merge behind the consumer's required checks. Its
  `corekit_pins.py` also rejects `rev`/`branch` Cargo pins, which Dependabot
  cannot move. Setup and templates: `docs/consumer-dependabot.md`.

## v0.27.0 — 2026-11-26

- Swift: three control tiers (GUIDELINES CTRL-1). `SymairaControlTier` and
  `.symairaControlTier(_:)` separate page actions (36 pt capsules, glass
  secondary) from workbench tools (native solid `.large` controls, 28 pt);
  `SymairaPage` sets both, the workspace shell stays the navigation tier.
  `SymairaSegmentedControl` is the native segmented picker with the Symaira
  tint again, secondary buttons are native Liquid Glass, and
  `.symairaFormRowControl()` centres a tall control on a grouped form row.
  See `swift/CHANGELOG.md` and `docs/migrations.md`.
- Swift: the `SymairaIconButton` deprecation message, GUIDELINES ICON-2 and
  the UI catalog E04 note name an `Image(symairaIcon:)` label; the previous
  `Label(_:symairaIcon:)` recipe renders an empty glass circle on macOS (#510).

## v0.26.0 — 2026-11-26

- Rust: Windows-only code leaves `symaira-core-fs`, `-secretref`, `-config`,
  `-update` and `-mcpcfg`, together with the Windows-only `cap-primitives`,
  `cap-std` and `same-file` dependencies and the Windows-only tests (#458).
  Windows has been outside the supported platform scope since #456/#459 and
  every consumer has removed its Windows code. `chmod_windows` is gone;
  `default_path_for_roots` keeps its `userprofile` parameter for source
  compatibility and ignores it. Non-Unix targets keep failing closed. The
  frozen FS/SEC and SQLite evidence is re-captured against the Go oracle with
  byte-identical Go observations
  (`docs/rust-port/evidence/frozen-reregistration-20261126-windows.json`).

## v0.25.0 — 2026-11-26

- Rust 1.100.0: `rust-toolchain.toml` is the single toolchain pin and every
  workflow installs from it; Dependabot proposes new stable releases through
  the `rust-toolchain` ecosystem. 1.98.0 had a trait-object vtable
  miscompilation (#495). ADR RUST-003 documents the Go-oracle recapture that
  a toolchain or lockfile update needs (#497); the frozen FS/SEC and SQLite
  evidence is re-registered with byte-identical Go observations
  (`docs/rust-port/evidence/frozen-reregistration-20261126.json`).
- Rust (`symaira-core-mcp`): the optional `toon` feature adds
  `Server::set_adaptive_toon` for text-only results that are at least 5 %
  smaller as TOON and decode to the same value (#506). It pulls in
  `toon-format` 0.7.0 (MIT), which enables `serde_json/preserve_order`, a mode
  the crate already tests in CI.
- Swift: Apple platforms move to native controls per the UI catalog decision
  of 2026-11-25 (`swift/design/ui-catalog/`, 33 elements with real macOS and
  iPhone screenshots). Nine Symaira controls are deprecated with named native
  replacements (forms, segments, switch, filter menu, icon button, progress,
  loading, sheet scaffold, stat tile); the appearance picker, badge and status
  label keep their API with the chosen look. GUIDELINES gain NATIVE-1, checked
  by `gui-review.py`.
- Swift: button labels stay on one line (#507), `symairaButtonStyle(_:onPressChange:)`
  reports press and release (#493), `Image(symairaIcon:)` is a template image
  (#491), inactive dark workspace windows keep sidebar contrast (#504), the
  text field style shows its focus ring by itself and `SymairaTextField` offers
  an `ink3` prompt (#502), `SymairaFormRow` centers controls on the label line
  (#503), and the provider settings view is a native grouped form that confirms
  key removal (#501). GUIDELINES: feedback motion with spring tokens (MOTION-5,
  #489), English and German with `swift/scripts/check-strings.py` (COPY-1,
  #492); `gui-review.py` no longer flags Swift ranges as three dots (#494).
- Rust (`symaira-core-mcp`): `Server::catalog_json()` returns the exact
  `tools/list` result, and `symaira_core_mcp::catalog_gate` checks a committed
  catalog-size record (tool count, at most 10 % byte drift) (#500).
- Rust (`symaira-core-llm`): the cancellation contract tests separate fixture
  startup from the cancellation deadline and no longer fail under load (#498).
- CI: Miri jobs use the dated `nightly-2026-10-29` instead of floating
  `nightly` (#496); CodeQL actions 4.39.4 (#499).
- `docs/consumers.json` records EraseMe v0.17.1 with its standalone evidence (#370).

## v0.24.0 — 2026-11-22

- Swift (tvOS): `.symairaTopography(_:)` is available on tvOS. The Liquid
  Topography is drawn at the tvOS platform scale (terrain, lines and ripples
  twice their point size) and follows the focus engine instead of a pointer:
  the focused item bends the lines and every focus move sends a ripple.
  GUIDELINES gain TV-1 to TV-3. macOS and iOS are unchanged.
- CI runs the SymairaTheme tests on a tvOS simulator.
- Rust: the lockfile moves `url` to 2.5.9 and `form_urlencoded` to 1.2.3
  (RUSTSEC-2026-0592, stack overflow in `Url::origin()` on nested `blob:`
  URLs), reached through `reqwest` in `symaira-core-llm` and
  `symaira-core-update`.

## v0.23.1 — 2026-11-18

- Swift: `SymairaIconView` pauses its animation timeline once a hover blend
  or click motion has settled. The pause was only re-checked on the next hover
  or click, so every icon that had been hovered kept redrawing at display
  rate; a long-running menu-bar app accumulated tens of percent of CPU.
- `make consumer-drift` lists every CoreKit pin of the sibling checkouts
  (Cargo `rev`/`tag`, `Package.swift`, XcodeGen `project.yml`, Xcode
  `project.pbxproj`/`Package.resolved`, Go) with the releases each trails and
  flags repositories that mix pins; it previously listed Go pins only (#490).
- ADR 0002 amendment: Rust consumers may pin CoreKit by immutable release tag
  (`tag = "vX.Y.Z"`) so Dependabot can bump it; `port/consumer/verify.py`
  accepts `rust.tag` records and checks tag, manifest and `Cargo.lock` source.
  Release tags `v*` are protected against deletion and moves.

## v0.23.0 — 2026-11-15

- Swift: Figtree replaces Inter for all running text, labels, captions and
  readouts. Google Sans Flex remains only on the largest headings and the
  wordmark. Sizes, weights and tabular digits stay unchanged; text widths can
  differ. Secondary and caption text gain slight tracking in dark appearance.
- Swift API: `SymairaFont.Family.opticalSize` is now `Double?` because Figtree
  has no optical-size axis. `SymairaFont.textOpticalSize` and the bundled Inter
  files are removed.
- Swift: 18 new `SymairaIcon` cases for meanings SymDesk still drew with SF
  Symbols: `blocks`, `usage`, `userVerified`, `userUnknown`,
  `notificationOff`, `journal`, `number`, `previousMatch`, `nextMatch`,
  `diff`, `embed`, `audioOff`, `language`, `invoice`, `receipt`, `tip`,
  `quote` and `skipped` (160 cases). The other reported gaps map to existing
  cases (#485).
- Swift: `SymairaIconView`, `Label(_:symairaIcon:)` and `SymairaIconButton`
  scale their icon with Dynamic Type relative to `.body` on iOS, so icons grow
  with the text next to them; `size` stays the base size (#484).
- Swift: `SymairaPage` without a toolbar no longer reserves an empty 44 pt
  toolbar row and its gap above the first section (#488).
- `gui-review.py` STATE-1 accepts an `accessibilityLabel` on the same line as
  `ProgressView()` (#481).

## v0.22.4 — 2026-11-14

- Swift: `SymairaTheme` compiles in Xcode 26.6 Release (whole-module)
  builds again. The topography Metal pipeline no longer captures its render
  encoder in closures, which that compiler rejected as a data race and which
  stopped the signed SymDesk archive (#486). Rendering is unchanged.

## v0.22.3 — 2026-11-13

- Swift, tvOS: `symairaButtonStyle(.primary/.secondary/.toolbar)` uses the
  system `borderedProminent` and `bordered` styles, so the remote's focus is
  visible (lift and highlight); the drawn Symaira styles showed none there.
- Swift, tvOS: `SymairaPage` toolbar and content and every `symairaCard` are
  focus sections, so the remote reaches a button at the right end of a row
  below a field or a row of stars.
- Swift: `SymairaIconView` and `SymairaIconButton` default sizes and the
  switch track follow `SymairaMetrics.platformScale` (doubled on tvOS only).

## v0.22.2 — 2026-11-13

- Swift: on tvOS every Symaira size doubles through the new
  `SymairaMetrics.platformScale`: `SymairaSpacing`, `SymairaRadius`,
  `SymairaMetrics`, `SymairaPageLayout` and the bundled font roles. Body text
  is 27 pt on the 1920 pt wide screen instead of 13.5 pt, close to the 29 pt
  of tvOS body text. macOS and iOS are unchanged (factor 1).

## v0.22.1 — 2026-11-13

- Swift: the native Liquid Topography draws the height field once per 4 pt
  grid cell and the contour lines per pixel from a B-spline through it, about
  a seventh of the GPU time per frame (0.26 ms instead of 1.88 ms at iPhone
  size on an M4 Pro). Ripples run at the display maximum until they fade, and
  the surface never blocks the main thread waiting for a drawable (#482).
- Swift: `SymairaSettingsButton` shows the gear on iOS instead of the word
  "Settings" (#482).
- The lockfile moves `quinn-proto` to 0.11.19 and `quinn-udp` to 0.5.16
  (RUSTSEC-2026-0523, -0524, -0538), both reached through `reqwest` in
  `symaira-core-llm` and `symaira-core-update`. Only the two package entries
  change; the frozen FS/SEC and SQLite lock-closure digests stay the same.

## v0.22.0 — 2026-11-12

- `symaira-core-mcp`: queued tool calls no longer block the reader. At most 16
  handlers still run at once, but further calls wait in a FIFO (up to 1024)
  while `ping`, `tools/list` and protocol errors keep being answered; before,
  `ping` waited behind every running call. Result objects and input schemas are
  written with sorted keys, so the response bytes no longer change when a
  consumer build enables `serde_json/preserve_order` (#480).
- New [docs/rust-port/go-compatibility.md](docs/rust-port/go-compatibility.md)
  records which differences from the retired Go library are intended in
  `-mcp`, `-fs`, `-secretref`, `-log`, `-llm` and `-config` (#480).
- Swift CI runs the SymairaTheme tests, including the UIKit Metal topography
  tests, on an existing iOS Simulator device on `main` and the weekly schedule
  (#479).
- The workspace requires `serde_json = "1.0.151"` (caret range, still locked to
  1.0.151) instead of `=1.0.151`, so consumers with their own serde_json
  requirement can resolve newer 1.0.x releases together with CoreKit crates
  (#475). The workspace manifest is a bound FS/SEC and SQLite input, so both
  frozen evidence lanes are re-captured natively; the lockfile closure is
  unchanged.
- Swift: `SymairaProgressStyle` draws the empty track as a `raised` groove with
  a 1 pt `line` outline instead of `ink3`, so a meter at 0 % no longer reads as
  full in dark or light; new shared `SymairaStatTile` summary tile (#476).
- Swift: the iOS and tvOS topography renders through the shared `CAMetalLayer`
  surface with a `CADisplayLink` (20 fps idle) instead of a 20 fps SwiftUI
  `TimelineView`; macOS is unchanged (#477).
- The Go maintenance branch `release/v0.18` is removed; `v0.18.3` is the
  final Go release (ADR 0005 amendment).

## v0.21.0 — 2026-11-10

- Swift shared icons add `operate`, `restart`, `memory`, `battery`,
  `keepAwake`, `expired` and `externalDrive`.
- Swift switches honor hidden labels; GUI review flags menu labels that should
  use `Image(symairaIcon:)` instead of `SymairaIconView` (#470).
- Add tvOS 17 builds for SymairaTheme and SymairaKeychain, with CI coverage.
- `symaira-core-fs` and `symaira-core-secretref` now require `rustix = "1.1.6"`
  (caret range, locked to 1.1.6) instead of `=1.1.4`, so consumers that pull
  these crates as Git dependencies can move their own workspace to newer 1.x
  rustix releases (#463). The SQLite capture harness no longer fails a clean run
  when macOS `killpg` returns `EPERM` after the child exited (#461). FS/SEC and
  SQLite frozen evidence is re-captured natively for the new lockfile closure.
- The Swift package directory is renamed from `appkit/` to `swift/`
  (ADR 0006 amendment). No consumer change: package identity, products,
  modules and the resource bundle name stay the same.

## v0.20.0 — 2026-11-10

- **AppKit merged into CoreKit** ([ADR 0006](docs/adr/0006-appkit-merged-into-corekit.md)).
  The complete `symaira-appkit` history now lives under `appkit/`; the Swift
  package (`SymairaTheme`, `SymairaCLIRunner`, `SymairaToolKit`,
  `SymairaKeychain`, `SymairaUpdateCheck`, `SymairaDaemonKit`,
  `SymairaIngestContract`, `SymairaMCP`, `SymairaProviderKit`) is resolved from
  the repository root `Package.swift`. Swift consumers pin
  `https://github.com/danieljustus/symaira-corekit.git`, `exact: "0.20.0"`,
  `package: "symaira-corekit"`; see `docs/migrations.md` and
  `appkit/CHANGELOG.md`. The archived AppKit repository keeps its `0.1.0` to
  `0.18.1` tags.
- Swift contract tests read `contracts/*.json` directly (vendored copies
  removed). New `swift.yml` workflow on the self-hosted Apple Silicon runner;
  CodeQL also analyzes Swift. Root `make swift-build|swift-test|swift-lint|swift-format`.
- PB-2026-09-09 revision 6 records the merge.
- Rust crates: no API change; `rusqlite` 0.41.1 for RUSTSEC-2026-0459 (#464).

## v0.19.0 — 2026-11-02

- **Go library retired from `main`** ([ADR 0005](docs/adr/0005-go-library-retirement.md)).
  All Go packages, `go.mod`/`go.sum`, Go CI, the Go release gate and the Go
  consumer-pin drift tooling are removed. `v0.18.3` is the last Go release from
  `main`; Go patch releases ship only from the `release/v0.18` branch. Go
  consumers keep their exact `v0.18.x` pins.
- CoreKit on `main` is the Rust workspace (`symaira-core-*` crates, exact Git
  revision pins per ADR 0002) plus the language-neutral `contracts/` fixtures.
- CI: `test` and `lint` now run the Rust workspace; `govulncheck` is replaced by
  `audit` (`cargo audit` + `cargo deny`); `apidiff` and the Go cross-build jobs
  are removed; CodeQL analyzes Rust and Python instead of Go.
- Frozen Go fixture provenance reads retired Go sources from the immutable
  `v0.18.3` commit (`scripts/rust-port/retired_go.py`).
- Docs: required platforms are Linux amd64/arm64 and macOS arm64; Windows and
  macOS Intel are no longer supported (#459).

## v0.18.3 — 2026-10-28

- `mcpserver`: on Unix, a stdout write failure now interrupts the blocked
  read on an inherited stdin, so `ServeIO` returns instead of waiting for
  input that never arrives. In-flight handlers still drain (#426).
- Security: `golang.org/x/net` v0.62.0 (GO-2026-6866, GO-2026-6860 in the
  `html` parser and renderer used by `domkit`) and `golang.org/x/sys` v0.49.0.
  `go.mod` now recommends the Go 1.26.9 toolchain; CI and release builds use
  Go 1.26.10 for GO-2026-6809 (crypto/x509). The minimum `go` directive stays
  1.26.4.
- Rust crates (Git-pinned): rustls, rustls-webpki and webpki root updates for
  RUSTSEC-2026-0346 to -0349 and -0381 to -0383; tokio 1.53.3 for
  RUSTSEC-2026-0386.

## v0.18.2 — 2026-10-07

- `mcpserver`: `ServeIO` reports a caller cancellation (or response write
  failure) that happens while in-flight tool calls drain after input EOF.
  Since v0.18.0 it returned `nil` in that case; v0.17 returned
  `context.Canceled`.

## v0.18.1 — 2026-10-07

- `mcpserver`: `ServeIO` keeps serving after a parse or invalid-request error.
  In v0.18.0 the first malformed frame was answered with an error and every
  later request on the stream was silently dropped (#410).

## v0.18.0 — 2026-10-06

- `configkit`: explicitly present TOML `false`, `0`, and `""` values now override
  earlier sources and defaults. An explicitly set empty string environment
  variable also clears a string field; an unset variable still leaves it alone.
- `symaira-core-config`: the Rust loader now follows that current zero-value
  precedence. The original v0.17.0 Go oracle fixture remains immutable as
  historical evidence of the previous behavior.
- **Consumer migration:** review existing configuration files that relied on
  zero-value skipping before raising the CoreKit pin. In particular, Symaira
  Desktop's `TestTOMLFalseValueIgnored` asserts the former behavior and must
  change with the consumer pin.
- `mcpserver`: the stdio transport bounds `Content-Length` and line-delimited
  reads before allocating, validates JSON-RPC envelopes, IDs, params, framing
  headers and notifications strictly, serializes concurrent responses without
  stalling the read loop, propagates write failures, and keeps in-flight
  handlers running on a normal EOF.
- `updatecheck`: the HTTP redirect policy also refuses non-HTTPS redirects;
  `CheckWithForce(true)` bypasses the persistent cache as well as the
  in-memory one.
- `updatecheck/updateapply`: the staged temporary file is removed on every
  failure path.
- `fsutil`: `SafeRemove` closes its descriptor exactly once.
- `domkit`: truncation allocates only the retained suffix.

## v0.17.0 — 2026-09-03

- `mcpserver`: a failed `tools/call` now publishes its structured error under
  the tool result's `_meta` key `symaira.dev/tool_error` — `code`, `message`,
  `retryable`, `requires_confirmation`, `resume_hint`, `hint`, `details` — built
  from optional interfaces on the returned error (`ErrorCode`,
  `RetryableError`, `RequiresConfirmation`, `ResumeGuidance`, `ErrorHint` /
  `Hint`, `ErrorDetails`), resolved through `errors.As`. Published as
  `contracts/mcp_tool_errors.json`.
- Consumer action: none required — an error that implements none of the
  interfaces produces no `_meta`, leaving its result byte-identical. A tool
  whose errors already carry this metadata (symbrowse's daemon proxy does)
  stops having to render it into the message text once the pin is raised.

## v0.16.3 — 2026-08-31

- `updatecheck/updateapply`: added the optional `Applier.ValidateBinary` hook
  for post-swap executable validation. A failed validation restores the previous
  binary, or removes the failed installation when no previous binary exists.
- Consumer action: configure `ValidateBinary` when the installed executable
  must pass a startup check such as `--version`; consumers that do not set it
  retain the existing behavior.

## v0.16.1 — 2026-08-29

- `configkit`: honors `XDG_CONFIG_HOME` by default, with an explicit legacy-path opt-out.
- `updatecheck`: persists its once-per-24-hour cache across checker instances.
- `ollamakit`: delegates Ollama transport to `llmkit` while preserving the compatibility API.
- `auditkit`: fingerprints checkpointed logs and validates the chain during recovery.
- Consumer action: update the exact `corekit` pin; existing APIs remain compatible.

## v0.16.2 — 2026-08-30

- `secretref`: added the shared Go resolver for `symvault://`, `keychain://`,
  `env://`, and bare environment-variable references, with a default
  subprocess timeout and documented fallback behavior. Existing
  `llmkit.ResolveCredential` callers remain compatible through its deprecated
  forwarder.
- `mcpserver`: published the cross-language MCP tool-annotation contract and
  conformance tests.
- Consumer action: update the exact `corekit` pin; consumers adopting
  `secretref` should use the package instead of maintaining a local resolver.

## v0.16.0 — 2026-08-26

- `llmkit`: added `WithStreamFinished` for provider terminal finish/stop reasons, `WithAPIKey` for consumers that resolve credentials in their own secret store, and `WithEmbedDimensions` for Matryoshka embedding dimension pinning (#187).
- Consumer action: update the `corekit` pin and adopt these options where needed; existing `llmkit` calls remain compatible and require no code change.

See the [v0.16.0 release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.16.0).

## v0.15.0 — 2026-08-26

- `llmkit`: added `ChatOptions.ResponseFormat` for OpenAI-wire structured output and the additive `WithGenerateSystem` / `WithGenerateFormat` options for native Ollama generation (#186).
- Consumer action: update the `corekit` pin and pass the new options when structured output is required; existing calls remain compatible and require no migration.

See the [v0.15.0 release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.15.0).

## v0.14.0 — 2026-08-26

- `llmkit`: added the shared provider layer with descriptor-driven OpenAI-compatible and Anthropic transports, streaming, tool use, embeddings, model discovery, credential references, and a contract error taxonomy (#179–#184).
- `ollamakit`: became a thin deprecated shim as Ollama support moved into the `llmkit` provider descriptors (#180).
- Consumer action: update the `corekit` pin; existing `ollamakit` consumers can migrate incrementally, while new provider integrations should use `llmkit` and plan to leave the deprecated shim before its removal.

See the [v0.14.0 release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.14.0).

## v0.13.0 — 2026-08-26

- `configkit`, `exitcodes`, and `updatecheck`: added cross-language contract fixtures and Go conformance tests for config paths, exit codes, update-check invariants, and JSON encoding/stdio rules (#170).
- Consumer action: no Go API migration is required; consumers maintaining Swift or Python ports should use `contracts/*.json` as the shared behavior reference and verify their implementations against it.

See the [v0.13.0 release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.13.0).

## v0.12.1 — 2026-08-25

- `sqlitekit`: updated the shared pure-Go SQLite dependency from `modernc.org/sqlite` 1.56.0 to 1.57.0 (#162).
- Documentation and repository hygiene were updated, including the shared README structure and linked changelog (#167, #169); no runtime package API changed.
- Consumer action: update the `corekit` pin and run SQLite-related tests; no source migration is required, and documentation-only and CI-maintenance changes require no consumer action.

See the [v0.12.1 release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.12.1).

## v0.12.0 — 2026-08-24

See the [v0.12.0 release notes](https://github.com/danieljustus/symaira-corekit/releases/tag/v0.12.0).

[View all releases](https://github.com/danieljustus/symaira-corekit/releases).
