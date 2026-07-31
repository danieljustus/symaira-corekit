# Agent Instructions — symaira-appkit

Shared public Swift library (Apache-2.0) for Symaira macOS clients. GUI counterpart to `symaira-corekit`. Consumed by the per-tool client apps as a pinned SPM dependency.

## Build & Test

```bash
swift build
swift test
```

- macOS 14+, Swift 6 (strict concurrency). No Xcode project — pure SPM.
- Local toolchain note: Command Line Tools lack XCTest. Run tests with the Xcode toolchain (same workaround as symaira-operate/tune):
  ```bash
  DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer swift test
  ```
- Keychain code is intentionally untested beyond compilation (headless CI has no keyring).

## Architecture & Boundaries

- **No tool-specific code.** A module belongs here only if ≥2 apps need it. App-specific views, models, and IPC stay in the app's repo. Record each "should this move here?" assessment — including the ones answered "no" — in [`docs/module-boundary-decisions.md`](docs/module-boundary-decisions.md), so the question is not re-litigated from scratch.
- **No Cloud/SaaS code** (no Stripe, Firebase, Pro concepts) — same boundary as corekit.
- **No third-party dependencies.** Foundation, SwiftUI, Security only.
- Consumers pin exact versions (`.package(url:…, exact: "x.y.z")`). Local development may use `path:` dependencies, but merged app code must reference a tag.
- `SymairaToolRegistry` is the single source of truth for tool metadata (binary names, Homebrew formulae, MCP args). Update it here, never fork it into an app.
- The version handshake expects cores to answer `version --json` with `{"version": "...", "schema_version": N}`. Cores without it are detected with `schemaVersion == 0` (usable, no contract guarantees).
- Subprocess execution must always have a timeout (loose-coupling rule: runtime detection with timeout and graceful fallback).

## Release

1. Update `CHANGELOG.md` with the new version entry following Keep-a-Changelog format. Gather changes from `git log` since the last tag and categorize them as Added, Changed, Deprecated, Removed, Fixed, Security, or Breaking.
2. Tag `vX.Y.Z` on main. Strict SemVer — breaking API changes bump the minor pre-1.0, per-app migration is explicit (each app updates its pin deliberately).
