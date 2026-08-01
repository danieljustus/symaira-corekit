<!-- review: timestamp=2026-07-30T11:28:17Z  repo=danieljustus/symaira-corekit  head=ec8368b1c4c3331729f4187be0cb1df155972655 -->
<!-- adopt: source=exa-labs/exa-mcp-server  source_ref=b4076055af28698d944b50deade80e541b7788ea  source_url=https://github.com/exa-labs/exa-mcp-server  depth=clone  license=MIT -->

# Adoption Report — symaira-corekit ← exa-labs/exa-mcp-server — 2026-07-30

## Sources

| Field | Value |
|---|---|
| SOURCE | `exa-labs/exa-mcp-server` (https://github.com/exa-labs/exa-mcp-server) |
| Ref analyzed | `b4076055af28698d944b50deade80e541b7788ea` (`main`) |
| Language / License | TypeScript / MIT |
| Health | Active-looking: latest cloned commit 2026-07-24; unit tests and CI are present. Stars and release data are unknown because the local `gh` authentication was invalid. |
| Scope | All facets, weighted to shared MCP architecture, protocol metadata, security, and testing; full clone |
| TARGET | `danieljustus/symaira-corekit` @ `ec8368b1c4c3331729f4187be0cb1df155972655` |

Repository hygiene note: `docs/adopt/` is currently not ignored in CoreKit. Suggested follow-up is to add `docs/adopt/` to `.gitignore`; this analysis did not modify `.gitignore`.

## Verdict

The SOURCE is not a useful dependency or implementation source for CoreKit, but it exposes one portable MCP protocol pattern. Exa marks tools with standard behavioral hints and tests the non-idempotent case; CoreKit's shared `mcpserver.Tool` currently emits only name, description, and input schema. Adding optional wire-level hints would give Fetch, Browse, Brain, and future Guard integrations a common interoperability signal without moving policy enforcement into CoreKit.

## What we already do as well or better

- Typed input-schema derivation → `mcpserver/RegisterTyped` in `mcpserver/typed.go:14-68` already removes much of the SOURCE's hand-maintained schema duplication.
- Server-level guidance → `mcpserver.SetInstructions` and the `initialize` response in `mcpserver/mcpserver.go:99-107,315-324` already provide a shared instruction channel.
- Transport safety → `mcpserver` keeps stdio framing and logs separate, with protocol tests in `mcpserver/mcpserver_test.go`; no SOURCE transport code is needed.
- Standalone shared-library boundary → CoreKit's `AGENTS.md` already forbids tool-specific business logic, which is a better fit than importing Exa's API/client stack.

## Findings

- [ ] **[Architecture] Carry standard MCP tool-behavior hints through the shared server**
  - **Status quo:** `mcpserver.Tool` in `mcpserver/mcpserver.go:56-67` has no annotation field, and `handleToolsList` in `mcpserver/mcpserver.go:327-347` serializes only `name`, `description`, and `inputSchema`. That means consumers cannot communicate even advisory read-only, destructive, open-world, or idempotency semantics through the common transport; this is a real ecosystem gap because `symaira-browse/AGENTS.md:35-47` requires risk classification and `symaira-guard` needs call-time decisions, while their shared wire contract has no generic hint channel. Exa attaches these hints to live tools in `src/tools/webSearch.ts:19-40` and `src/tools/agentRun.ts:534-544`, and its regression test checks the non-idempotent annotation in `tests/unit/tools/agentRun.test.ts:594-602`.
  - **Proposed solution:** Pattern adoption only; do not copy Exa's TypeScript registration code. Add an optional `ToolAnnotations` value to `mcpserver.Tool`, serialize it as the MCP `annotations` object in `tools/list`, and cover omission/presence plus round-trip behavior in `mcpserver` tests. Treat these as client-facing hints only: do not use them as a replacement for `symguard` risk classes, approvals, or call-time enforcement.
  - **Effort/Impact:** Low-medium effort / high impact. It is additive and reversible, centralizes one protocol contract for every CoreKit consumer, and enables safer client UX without forcing any existing tool to opt in.

## Considered and rejected

- **Exa's Zod validation/reflection approach** — gate 2 (New): CoreKit already has the Go-native `mcpserver.RegisterTyped` helper in `mcpserver/typed.go:14-68`.
- **Exa's provider-response sanitizer** — gate 1 (Transferable): it is coupled to Exa response shapes and does not belong in a domain-free transport library.
- **Exa's retry, rate-limit, and timeout helpers** — gate 1 (Transferable): they are service-client policy, not generic MCP transport behavior; consumers already own request budgets.
- **Exa's static tool registry with product aliases** — gate 4 (Worth it): a shared CoreKit registry would impose product-specific naming and profile policy on independent tools.
- **MCP prompts/resources and bundled skills** — gate 4 (Worth it): this is a larger protocol-surface expansion with no recorded CoreKit consumer requirement; `SetInstructions` covers the current common guidance need.
- **Exa's HTTP/Vercel deployment and OAuth plumbing** — gate 1 (Transferable): CoreKit is a local, domain-free Go library and must not acquire hosted-service infrastructure.

## Open questions

- Which exact MCP SDK/spec versions must the shared wire output support, and do the current target harnesses preserve unknown `annotations` fields? A small captured `tools/list` compatibility matrix would settle this.
- Should CoreKit expose only the four standard hints seen in the SOURCE or allow an extensible map? The protocol contract and downstream consumers should decide before the public API is frozen.

First step: add a failing `tools/list` test for an optional read-only/non-idempotent annotation pair, then define the smallest public Go type that makes that test pass.
