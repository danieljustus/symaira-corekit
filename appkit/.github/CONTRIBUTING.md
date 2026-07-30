# Contributing to symaira-appkit

Thanks for your interest! This is a solo-maintainer library, but PRs and issues are welcome.

## Questions & Discussions

Open a [GitHub Discussion](https://github.com/danieljustus/symaira-appkit/discussions) for questions, ideas, or general chat.

## Reporting Bugs

Open a [Bug Report issue](https://github.com/danieljustus/symaira-appkit/issues/new?template=bug_report.yml). Include:
- Swift version and Xcode version
- macOS version
- What you expected vs what happened
- A minimal reproduction, if possible

## Feature Requests

Open a [Feature Request issue](https://github.com/danieljustus/symaira-appkit/issues/new?template=feature_request.yml).

## Pull Requests

1. Fork the repo and create your branch from `main`.
2. Run `swift build` to verify compilation.
3. Run `swift test` to verify existing tests pass.
4. Keep the scope focused — one PR per feature/fix.
5. Update the CHANGELOG if your change is user-facing.
6. Open the PR against `main`.

### SPM Dependency Policy

Consumers pin exact versions (`.package(url:…, exact: "x.y.z")`). Never introduce a third-party dependency — Foundation, SwiftUI, and Security only.

### Code Style

- Swift 6 strict concurrency (`Sendable`, `@MainActor` where appropriate).
- No force-unwraps (`!`) outside of tests.
- Document public API with doc comments.
- Match the existing project conventions.

## Release Process

Managed by the maintainer. See `CHANGELOG.md` for version history.
