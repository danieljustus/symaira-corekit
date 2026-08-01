<!-- review: timestamp=2026-07-30T10-18-13Z  repo=danieljustus/symaira-corekit  head=ec8368b1c4c3331729f4187be0cb1df155972655 -->
<!-- adopt: source=qianniuspace/mcp-security-audit  source_ref=f8caea63debad0d9b0d01ce848375e8fcb66f932  source_url=https://github.com/qianniuspace/mcp-security-audit  depth=clone  license=MIT -->

# Adoption Report — symaira-corekit ← qianniuspace/mcp-security-audit — 2026-07-30

## Sources

| Field | Value |
|---|---|
| SOURCE | `qianniuspace/mcp-security-audit` (https://github.com/qianniuspace/mcp-security-audit) |
| Ref analyzed | `f8caea63` (main) |
| Language / License | TypeScript / MIT |
| Health | 54 stars, 9 forks, last push 2025-07-18 (~12 months stale), not archived, no GitHub releases, ~16 KB of source across 5 files |
| Scope | all facets, full clone |
| TARGET | `danieljustus/symaira-corekit` @ `ec8368b1` |

## Verdict

Zero findings. The SOURCE is a ~300-line single-tool MCP server; `corekit` is a
Go library whose `mcpserver` package already implements the same protocol with
typed schema derivation, tested error paths and documented stdio discipline.
Every candidate either does not transfer out of the npm ecosystem, or names
something this repo already does better — including the two MCP traps the
SOURCE bothered to write down, both of which are encoded in `mcpserver`'s own
code and doc comments. The only facet where the SOURCE is nominally ahead
(published-artifact provenance) does not apply: `corekit` is consumed as a Go
module by commit hash, not as a downloadable binary, so it publishes no release
artifacts to attest. Nothing here is worth an issue.

## What we already do as well or better

- Stderr-only logging so stdout stays a clean JSON-RPC channel (their `Pitfalls.md` §"MCP 规范", `src/index.ts:111`) → stated as a contract in [`mcpserver/mcpserver.go:125-128`](../../mcpserver/mcpserver.go) and enforced by [`logkit/logkit.go:71`](../../logkit/logkit.go) defaulting to `os.Stderr`.
- MCP tool registration with input schemas (`src/index.ts:61-81`, hand-written JSON literal) → [`mcpserver/typed.go`](../../mcpserver/typed.go) derives `InputSchema` from Go types via `RegisterTyped` (#40/#43, commit `ec8368b`), with tests in `typed_test.go`. Strictly better: no hand-maintained JSON to drift.
- Fixed `{"content":[...]}` response envelope (their `Pitfalls.md` §"接口规范") → handled by the `mcpserver` wire layer with `mcpserver_test.go` covering it.
- Typed protocol errors on tool failure (`McpError`/`ErrorCode`, `src/handlers/security.ts:52`) → sentinel-error conventions across the repo (e.g. `evidencekit/sentinels_test.go`, `exitcodes/`), plus an apidiff CI gate (#39/#42) the SOURCE has no analogue for.
- Dependency vulnerability scanning in CI → [`.github/workflows/ci.yml:67-80`](../../.github/workflows/ci.yml) runs `govulncheck ./...` pinned at `v1.4.0`. This is the exact capability the SOURCE's whole product exists to provide, already standing here.
- Artifact signature verification → [`updatecheck/cosign/cosign.go`](../../updatecheck/cosign/cosign.go) implements the *verifying* side of release provenance for downstream binaries; the SOURCE only produces a signature, never checks one.
- A real test suite → every package here has a `_test.go` beside it; `src/test/test.ts` upstream is a single manual script, ~80% commented out, with no assertions.

## Findings

None. No candidate from `qianniuspace/mcp-security-audit` survived the four
gates against this repo.

## Considered and rejected

- **Their dependency-audit MCP tool** (`src/index.ts:61-81`, `src/handlers/security.ts`) — gate 1 (Transferable): npm-registry-specific and product-shaped. `corekit` is a library of reusable Go packages; shipping a vulnerability-audit tool is not its role, and no consumer repo has asked for one.
- **Remote advisory-API lookup instead of a local audit subprocess** (`src/handlers/security.ts:39`, rationale in `Pitfalls.md` §"npm audit 优化") — gate 2 (New): the Go equivalent already runs in CI (`ci.yml:67-80`), and `govulncheck` is call-graph-aware, so it is also better than what they built.
- **Their per-dependency audit loop** (`src/handlers/security.ts:78-87`) — gate 3 (Better): an anti-pattern. One sequential HTTP round-trip per package against a legacy bulk endpoint, with per-package failures swallowed to `console.error`, so a partially-failed audit is indistinguishable from a clean one.
- **`npm publish --provenance` + `id-token: write`** (`.github/workflows/publish.yml:18-20,44`) — gate 1 (Transferable): `corekit` has no release workflow and publishes no binaries; Go modules are consumed by version/commit from the proxy with checksum-database verification already covering the integrity question. (The same idea *is* a live finding for `symaira-guard` and `symaira-skills`, which do ship binaries — see their reports of the same date.)
- **`Pitfalls.md` as a gotchas document** — gate 2 (New): [`AGENTS.md`](../../AGENTS.md) and [`docs/cross-language-conventions.md`](../../docs/cross-language-conventions.md) already carry these conventions at far greater depth, and both MCP traps it records are encoded in `mcpserver`'s code.
- **Smithery listing + `smithery.yaml` + Dockerfile** (`smithery.yaml:1-13`, `Dockerfile`) — gate 1 (Transferable): a distribution channel for runnable Node MCP servers. `corekit` is not runnable and ships no binary.
- **`npm install --ignore-scripts` in multi-stage Docker** (`Dockerfile:12,32`) — gate 1 (Transferable): defends against npm lifecycle-script execution, a hazard Go's build model does not have.
- **Their `bump` script wrapping `standard-version`** (`package.json:40`) — gate 3 (Better): chains `git add . ; git commit ; git push` with `;`, so each step runs regardless of the previous exit status. Releases here go through `06-gh-prerelease`/`07-gh-release` with gate reports in `.github/prerelease/`.
- **Their publish workflow's auto-tag-and-release** (`.github/workflows/publish.yml:34-48`) — gate 3 (Better): fires on every push to `main` and gates release steps on commit-message substring matches. No delta to gain.
- **CVSS/CWE fields on their vulnerability type** (`src/types/index.ts:19-24`) — gate 2/gate 3: dead code upstream — declared optional, never populated by `processVulnerabilities` (`src/handlers/security.ts:126-137`). `corekit` has no vulnerability record type to enrich.

## Open questions

None arising from this SOURCE. It is too small and too far from this repo's
domain to leave anything unresolved.

The single best first step: none — file no issues from this report, and treat
`qianniuspace/mcp-security-audit` as closed for `corekit`.
