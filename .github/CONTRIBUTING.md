# Contributing to symaira-corekit

Thank you for your interest in contributing!

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## How to Contribute

### Reporting Issues

- Search [existing issues](https://github.com/danieljustus/symaira-corekit/issues) before opening a new one.
- Use the issue templates (bug report / feature request) to provide complete information.
- For security vulnerabilities, see [SECURITY.md](SECURITY.md) instead of opening a public issue.

### Pull Request Process

1. Fork the repository and create a feature branch from `main`.
2. Follow the existing code style: run `gofmt -w -s .` before committing.
3. Ensure `go build ./...` and `go test -race ./...` pass for all packages.
4. Keep PRs focused on a single concern. Split unrelated changes into separate PRs.
5. Reference the issue number in your PR description (`Closes #N`).
6. All commits must be signed.
7. PRs are squash-merged into `main`.

### Development Setup

```bash
git clone https://github.com/danieljustus/symaira-corekit
cd symaira-corekit
go build ./...
go test ./...
```

### Commit Style

- Use conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `ci:`, `refactor:`.
- Breaking changes: add `BREAKING CHANGE` or `!` after the type prefix.
- Keep commits atomic and descriptive.

## License

By contributing, you agree that your contributions will be licensed under the
[Apache License 2.0](../LICENSE).
