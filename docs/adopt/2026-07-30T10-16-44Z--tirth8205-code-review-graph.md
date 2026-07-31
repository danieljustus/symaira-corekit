<!-- review: timestamp=2026-07-30T10:16:44Z  repo=danieljustus/symaira-corekit  head=ec8368b -->
<!-- adopt: source=tirth8205/code-review-graph  source_ref=90d760aa23fac0353637d2e8f2a431aa08f14366  source_url=https://github.com/tirth8205/code-review-graph  depth=clone  license=MIT -->

# Adoption Report — symaira-corekit ← tirth8205/code-review-graph — 2026-07-30

## Sources

| Field | Value |
|---|---|
| SOURCE | `tirth8205/code-review-graph` (https://github.com/tirth8205/code-review-graph) |
| Ref analyzed | `90d760aa` (main) |
| Language / License | Python 3.10+ (94%), TypeScript (VS Code ext) / MIT |
| Health | 27.7k stars, last push 2026-07-27, active PyPI releases, CI + weekly eval, 65 test fixtures |
| Scope | all facets, full clone |
| TARGET | `danieljustus/symaira-corekit` @ `ec8368b` (Go 1.26.4, shared library toolkit — 12 packages, no binary) |

## Verdict

**Nothing from `tirth8205/code-review-graph` is worth adopting into symaira-corekit.** The shape mismatch is decisive: CRG is an end-user application — a code indexer with a CLI, an MCP server, a VS Code extension and a benchmark suite — while symaira-corekit is a dependency-light Go library toolkit with no binary, no server, no retrieval surface and no user-facing product. Every substantive idea CRG has (tree-sitter parsing, the retrieval eval harness, the loopback HTTP guard, the multi-client MCP installer) belongs to a layer corekit deliberately sits below; the useful ones landed as findings in the `symaira-memory`, `symaira-seek` and `symaira-scope` reports from this same run. On the one facet where the two repos are genuinely comparable — CI and supply-chain hygiene — corekit is the stronger repo, not the weaker one.

## What we already do as well or better

- Pinned CI actions → `.github/workflows/ci.yml:34,36` pin `actions/checkout` and `actions/setup-go` to commit SHAs; CRG uses floating `actions/checkout@v7` / `actions/setup-python@v7` across all five of its workflows.
- Pinned tooling versions → `ci.yml:77` installs `govulncheck@v1.4.0`; CRG installs `apidiff`-equivalent tooling unpinned (`bandit[toml]`, `mypy` with no version constraint).
- Concurrency control → `ci.yml:21` cancels superseded runs per ref; CRG has no `concurrency:` block in any workflow, so pushes queue behind stale runs.
- API-compatibility gate → `ci.yml:82` `apidiff` against `origin/main` with an explicit opt-out for intentional breaks (`#39`/`#42`). CRG has no API-stability check at all despite publishing to PyPI.
- Vulnerability scanning → `govulncheck ./...` on every run. CRG runs `bandit` (a lint, not a CVE scanner) and has no dependency-vulnerability job.
- Least-privilege workflow permissions → `ci.yml:23` `contents: read`. CRG matches this one; parity, not a gap.
- Fast PR gate vs. full weekly suite → `c25539e`. Same split CRG uses.
- MCP protocol layer with bounded framing → `mcpserver/mcpserver.go:23` caps a single line/body at 1 MiB so a peer cannot force unbounded buffering. CRG delegates its transport to FastMCP and owns no equivalent hardening.
- Typed tool registration deriving `InputSchema` from Go types → `mcpserver/typed.go` (`#40`/`#43`), the direct analogue of FastMCP's signature-derived schemas.

## Findings

*(none)*

No candidate survived the gates. The three that came closest are recorded below with the gate that killed them.

## Considered and rejected

- **`http_origin_guard.py` — Host/Origin validation against DNS rebinding, as a reusable middleware** — gate 1 (Transferable): the closest call in this analysis. It is genuinely a library-shaped concern and corekit is the natural owner for something `symaira-memory` is missing and `symaira-seek` hand-rolls. But `mcpserver` is **stdio-only** by design (`mcpserver/mcpserver.go:2` — "implements the MCP stdio transport with Content-Length framing"); there is no HTTP transport for the guard to attach to. Adopting it means first building an HTTP transport corekit has no consumer for, which is a new feature justified by a hypothetical, not an adoption. Revisit only if a second consumer asks corekit for an HTTP MCP transport — at that point a shared loopback guard should ship with it.
- **Cross-language schema-version parity CI job** (`.github/workflows/ci.yml:52` `schema-sync`) — gate 1 (Transferable): corekit defines `versionkit.SchemaVersion` but ships no second-language client to drift against; the drifting literals live in the consumer repos (`symaira-scope`, `symaira-seek`), which cannot be checked from corekit's CI. Filed as a finding in both of those reports instead.
- **Pinned-corpus evaluation harness run weekly, report-only** (`code_review_graph/eval/`, `.github/workflows/eval.yml`) — gate 1 (Transferable): corekit has no retrieval, ranking or output-quality surface to score. `vectorkit/turboquant` has quality characteristics worth measuring, but its correctness is already covered by unit tests and the meaningful end-to-end quality signal lives in `symaira-seek`/`symaira-memory`, where it was filed.
- **Standardised error-response envelope** (`tools/_common.py:22` `_error_response`) — gate 2 (New): `exitcodes/` and the JSON-RPC error codes in `mcpserver/mcpserver.go:27-32` already provide this, with the protocol's own numbering rather than an ad-hoc `status`/`error` dict.
- **Best-effort provenance metadata read that never fails the caller** (`tools/_common.py:60` `graph_provenance`) — gate 1 (Transferable): the pattern is real, but the thing being described is a build-provenance concept belonging to whoever owns an index. `evidencekit` already covers corekit's provenance concern (evidence spans), and it is a different concept, not a weaker one.
- **Structured migration registry with a `LATEST_VERSION` derived from the migration map** (`code_review_graph/migrations.py`) — gate 2 (New): `sqlitekit` already owns migration handling for the ecosystem, and consumers (`symaira-memory/internal/db`, `symaira-seek/internal/db/migrate.go`) build on it.
- **Bandit security lint** (`.github/workflows/ci.yml:38`) — gate 1 (Transferable): Python AST linter. `golangci-lint` plus `govulncheck` are the Go equivalents and both already run.
- **`pyproject.toml` optional-dependency extras (`[dev]`, `[eval]`) to keep the default install thin** — gate 1 (Transferable): Go modules have no extras mechanism; the equivalent discipline is package-level dependency isolation, which corekit already practises (`go.mod` has exactly two direct dependencies for twelve packages).
- **Five translated READMEs, Discord, trendshift badge, issue templates, `SECURITY.md` scaffolding** — gate 4 (Worth it): 27.7k-star community infrastructure. corekit is an internal-facing library with a single consumer organisation; the maintenance cost has no reader. Scale-fit failure.
- **VS Code extension shipped in-repo** (`code-review-graph-vscode/`) — gate 1 (Transferable): corekit ships no user-facing product.

## Open questions

- Whether corekit should ever own an HTTP MCP transport is the one question this analysis surfaced but cannot answer from the outside. Today `symaira-memory/internal/mcp/http_server.go` and `symaira-seek/internal/server/server.go` each implement their own loopback HTTP MCP surface, with divergent security properties — seek validates the `Host` header, memory does not. That duplication is a real cost, and CRG's single shared guard module is what makes it visible. The evidence that would settle it: whether a third consumer needs an HTTP transport, and whether the two existing implementations have diverged for good reasons or by accident. Until then, the correct move is the per-repo fix filed against `symaira-memory`, not a speculative corekit package.

**First step:** none for this repo — the actionable output of this analysis is in the `symaira-memory`, `symaira-seek` and `symaira-scope` reports from the same run.
