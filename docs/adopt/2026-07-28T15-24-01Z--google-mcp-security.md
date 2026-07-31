<!-- review: timestamp=2026-07-28T15-24-01Z  repo=danieljustus/symaira-corekit  head=213217c66b6cfb6666179018dd7cb59a9685d1e9 -->
<!-- adopt: source=google/mcp-security  source_ref=main (shallow clone HEAD at analysis time)  source_url=https://github.com/google/mcp-security  depth=clone  license=Apache-2.0 -->

# Adoption Report — symaira-corekit ← google/mcp-security — 2026-07-28

## Sources

| Field | Value |
|---|---|
| SOURCE | `google/mcp-security` (https://github.com/google/mcp-security) |
| Ref analyzed | `main`, shallow clone (`--depth 1`) |
| Language / License | Python 3.11+ (mcp[cli]/FastMCP-based) / Apache-2.0 |
| Health | 512 stars, 126 forks, last push 2026-06-03, not archived, active release cadence |
| Scope | all facets, full shallow clone, weighted toward `architecture`/`api-dx` (TARGET is a shared library, not a CLI) |
| TARGET | `danieljustus/symaira-corekit` @ `213217c66b6cfb6666179018dd7cb59a9685d1e9` |

## Verdict

`google/mcp-security` builds its dozens of MCP tools on Python's `FastMCP`, which derives both the JSON Schema and the client-facing description of every tool automatically from the handler function's type hints and docstring — see `server/gti/gti_mcp/tools/files.py:88-96`, where `async def get_file_report(hash: str, ctx: Context) -> ...` needs no separate schema at all. `corekit`'s own `mcpserver.Tool` (`mcpserver/mcpserver.go:57-67`) has no equivalent: `InputSchema` is a raw `json.RawMessage` that every consumer must hand-author as a JSON string, kept in sync by hand with whatever Go struct the handler actually parses. This is not a hypothetical gap — it is the exact duplication happening today, right now, in the six repos that already import `corekit/mcpserver`: 42 `RegisterTool` call sites across `symaira-memory` (8), `symaira-seek` (12), `symaira-fetch` (3), `symaira-scope` (6), `symaira-fritz` (9), and `symaira-print` (4) each write a JSON Schema string that duplicates a Go struct one file below it (e.g. `symaira-scope/internal/mcptools/tools.go:42-47`: `InputSchema: json.RawMessage(`{"type":"object","properties":{"count":{"type":"integer"},...}}`)` next to `args := struct{ Count int; From int; To int }`). `symaira-vault` independently arrived at the same problem from the other direction: rather than use `corekit/mcpserver` at all, it built its own `internal/mcp` stack with a hand-rolled `schemaProperty`/`objectSchema` helper (`symaira-vault/internal/mcp/server/tool_registry.go:49-69`) purely to cut down on raw-string duplication. Three independent repos hitting the same wall is exactly the "domain-free infrastructure... otherwise duplicated across tools" problem `corekit`'s own README says it exists to solve. One finding survives the gates.

## What we already do as well or better

- `corekit`'s `mcpserver` correctly distinguishes tool failures via the MCP `isError: true` envelope (`mcpserver/mcpserver.go:394-401`, `sendToolError`). SOURCE's tools mostly return a plain `{"error": "..."}` dict as a *successful* result (e.g. `server/gti/gti_mcp/utils.py:52-56`, `fetch_object`) rather than signaling a protocol-level tool error — a client has to string-match the payload to notice failure. `corekit`'s approach is the more correct one.
- SOURCE ships four independently-versioned Python packages that must be published, tagged, and dependency-pinned separately (`.github/workflows/publish-packages.yml`). `corekit` and its consumers avoid that entire class of version-skew problems by being single-binary Go modules with no runtime package-manager dependency graph between them (`README.md` "Standalone-First Contract").

## Findings

- [ ] **[Architecture] Derive tool InputSchema (and arg parsing) from a single typed Go definition instead of hand-written JSON strings**
  - **Status quo:** `mcpserver.Tool.InputSchema` (`mcpserver/mcpserver.go:57-67`) is an opaque `json.RawMessage` with no connection to the Go type the handler actually parses. Every consumer hand-writes the schema as a JSON string literal and keeps it in sync with a separate Go struct by hand — verified live in `symaira-scope/internal/mcptools/tools.go:42-47`, `symaira-fetch/internal/mcp/tools.go:28,55` and `wayback.go:19`, and 8/12/9/4 more call sites in `symaira-memory`, `symaira-seek`, `symaira-fritz`, and `symaira-print` respectively (42 sites total across 6 repos). `symaira-vault` hit the same wall independently and built its own partial fix, `objectSchema`/`schemaProperty` (`symaira-vault/internal/mcp/server/tool_registry.go:49-69`), rather than using `corekit` at all. Upstream `google/mcp-security` solves this at the framework layer: `FastMCP`'s `@server.tool()` decorator reads the Python function signature and docstring and derives the JSON Schema and description automatically (`server/gti/gti_mcp/tools/files.py:88-96`), so there is exactly one source of truth per tool.
  - **Proposed solution:** Pattern adoption, not code adoption (Python reflection over type hints has no Go equivalent; Apache-2.0 code would need attribution regardless, but nothing here is being copied). Add a small reflection/struct-tag-based helper to `corekit/mcpserver` — e.g. `mcpserver.RegisterTyped[T any](srv *Server, name, description string, handler func(context.Context, T) (any, error))` — that derives the JSON Schema from `T`'s fields (via `json` tags plus a lightweight `desc` tag) and unmarshals `T` before calling the handler, the way `encoding/json` already derives behavior from struct tags elsewhere in this codebase. Keep the existing raw `Tool{InputSchema: json.RawMessage(...), Handler: func(ctx, json.RawMessage)}` path working unchanged — this is additive, consumers migrate opportunistically, `symaira-vault` can adopt it later or keep its own richer `RiskLevel`/`Capabilities` model if `RegisterTyped` doesn't cover those fields.
  - **Effort/Impact:** Small-to-medium effort (one new generic helper plus tests in `corekit/mcpserver`, no forced consumer migration). High impact given 42 existing call sites already carry the duplication this removes, and every future tool added to any of the six consumers avoids it by construction.

## Considered and rejected

- **FastMCP's async context-manager dependency injection per request (`server/gti/gti_mcp/server.py:41-48`, `vt_client(ctx)`)** — gate 3 (Better): Go's idiomatic equivalent — a handler closure capturing a shared client, already used throughout `symaira-scope`/`symaira-fetch` — is simpler than Python's async-context-manager indirection and has no delta to close.
- **Rich Args/Returns/Example docstring convention for tool descriptions (e.g. `server/gti/gti_mcp/tools/files.py:88-96`)** — gate 3 (Better): SOURCE's tools average far more parameters and relationship enums (see `FILE_RELATIONSHIPS`, 60+ entries) than any tool across the six `corekit` consumers, most of which take 0-3 simple parameters; the extra documentation structure would be low-value overhead here. If schema derivation (the finding above) is implemented, per-field descriptions can piggyback on its struct tags at near-zero extra cost anyway.
- **Python pytest fixtures mocking the upstream HTTP API (`server/gti/tests/conftest.py`)** — gate 1 (Transferable): Go's standard-library `net/http/httptest` already covers this exact need; nothing here is an improvement over current Go practice.
- **Multi-package independent versioning and publish workflow (`.github/workflows/publish-packages.yml`)** — gate 1 (Transferable) / scale fit: solves version coordination across 4 separately-shipped Python packages; `corekit` is one Go module with no equivalent multi-package release problem.
- **MCP `resources`/`prompts` capabilities** — gate 2 (New)/not applicable: SOURCE does not use them either (grep across the entire `server/` tree found zero `@server.resource`/`@server.prompt` usages) — nothing to learn here either way.

## Open questions

None — the duplication this finding targets is directly observable in both repos' current source, not something requiring reconstructed motivation.

The single best first step: prototype `mcpserver.RegisterTyped[T]` in `corekit/mcpserver` against one existing tool (e.g. `symaira-scope`'s `ports_suggest`, `internal/mcptools/tools.go:42-47`) to confirm the schema it derives matches the hand-written one byte-for-byte before touching the other 41 call sites.
