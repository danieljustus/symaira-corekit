# Security Policy

## Supported Versions

| Version  | Supported          |
| -------- | ------------------ |
| v0.21.x  | :white_check_mark: |
| v0.20.x  | :white_check_mark: |
| v0.19.x  | :white_check_mark: |
| <= v0.18 | :x:                |

Rust and Swift releases are covered by security updates for 3 months after the
next minor release. v0.18.3 is the final release of the retired Go library; the
Go maintenance line has ended ([ADR 0005](../docs/adr/0005-go-library-retirement.md)),
so v0.18.x and earlier receive no further fixes.

## Reporting a Vulnerability

To report a security vulnerability:

1. **Do NOT open a public GitHub issue.**
2. Use GitHub's **Private Vulnerability Reporting** (PVR): navigate to the
   [advisories page](https://github.com/danieljustus/symaira-corekit/security/advisories/new)
   and submit a report. GitHub will route it to the maintainer.
3. Alternatively, email `security@symaira.com` with a description of the issue,
   steps to reproduce, and any relevant proof-of-concept code.

You will receive an acknowledgment within 48 hours. If the issue is confirmed,
a fix will be prepared and a release will be coordinated. Please do not
publicly disclose any details until a fix is available.
