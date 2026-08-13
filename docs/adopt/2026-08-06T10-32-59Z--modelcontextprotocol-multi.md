<!-- review: timestamp=2026-08-06T10:32:59Z  repo=danieljustus/symaira-corekit  head=2d7b776 -->
<!-- adopt: source=modelcontextprotocol/go-sdk+modelcontextprotocol/modelcontextprotocol  source_ref=main  source_url=https://github.com/modelcontextprotocol/go-sdk  depth=shallow-api  license=Apache-2.0/MIT-dual -->

# Adoption Report — symaira-corekit ← MCP ecosystem (spec, go-sdk, reference servers) — 2026-08-06

## Sources

| Field | Value |
|---|---|
| SOURCE (primary) | `modelcontextprotocol/go-sdk` (https://github.com/modelcontextprotocol/go-sdk) |
| SOURCE (context) | `modelcontextprotocol/modelcontextprotocol` spec (protocol version 2025-06-18 / 2025-11-25), `github/github-mcp-server`, `makenotion/notion-mcp-server` |
| Ref analyzed | go-sdk `main` (tag v1.7.0, post-1.0, semver) |
| Language / License | Go / Apache-2.0 for new contributions, MIT for pre-transition code (dual, mid-relicensing) |
| Health | co-maintained with Google, stable v1.x line, active examples/tests in-repo |
| Scope | README + quick_start + server/tool/resource/prompt/sampling/elicitation API surface (no clone; API-derived) |
| TARGET | `danieljustus/symaira-corekit` @ `2d7b776` |

## Verdict

`corekit/mcpserver` is not a proposed package — it already shipped (v0.1.0+) and is the working MCP-server SSOT for six ecosystem consumers (memory, seek, fetch, scope, fritz, print — 42 call sites) plus symaira-brain. That is a genuine success the ecosystem docs undersell. But it is a from-scratch, tools-only JSON-RPC 2.0 stdio implementation with no dependency on any MCP SDK, and this repo's own same-day adoption scan against `agentgateway/agentgateway` (`docs/adopt/2026-08-06T10-20-33Z--agentgateway-agentgateway.md`) already found three concrete bugs in it (replying to notifications with a JSON-RPC error, always-flattened text-only tool results, zero fuzz coverage on the hand-rolled frame parser) that are not yet filed as issues. This report does not re-file those — it asks the larger question the peer-gateway comparison structurally couldn't: given seven consumers now depend on this package and the MCP spec has grown resources, prompts, sampling, elicitation, cancellation, and progress/log notifications since `mcpserver` was written, is continuing to hand-roll the protocol layer still the right call, or should `corekit/mcpserver` v2 be built on the official, Google-co-maintained `go-sdk`? The single highest-value takeaway: run a scoped spike swapping one low-risk consumer (`symaira-fetch`, already named as the simplest migration candidate in `ECOSYSTEM.md`'s own migration-order rationale) onto a go-sdk-backed `mcpserver` v2, and decide from real numbers rather than from the README.

## What we already do as well or better

- Typed input-schema derivation from Go struct tags (go-sdk's `AddTool[In,Out]` generic pattern) → we already ship this as `RegisterTyped[T]` (`mcpserver/typed.go`), shipped in v0.7.0, with `DisallowUnknownFields` validation baked in.
- Advisory tool annotations (Title/ReadOnlyHint/IdempotentHint/OpenWorldHint/DestructiveHint) → already shipped in v0.8.0 (`ToolAnnotations`), matching the spec's `tools/list` annotation fields.
- Panic recovery inside tool handlers converting to a `-32603` internal error instead of crashing the process → already present in `mcpserver.go`, a robustness property go-sdk's README doesn't specifically advertise either way.
- Dual Content-Length-framed and newline-delimited stdio parsing (auto-detected) → already present; go-sdk's `StdioTransport` is newline-delimited only, so we're not strictly behind here, just differently shaped.

## Findings

- [ ] **[Architecture] Spike a go-sdk-backed `corekit/mcpserver` v2 on the simplest consumer before deciding whether to migrate the ecosystem**
  - **Status quo:** `mcpserver/mcpserver.go` (466 lines) is a hand-rolled JSON-RPC 2.0 stdio server with no dependency on any MCP SDK (`go.mod` lists only BurntSushi/toml, golang.org/x/net, yaml.v3, modernc.org/sqlite). It declares only the `tools` capability — no resources, prompts, sampling, elicitation, logging, or completions — and the protocol version is hardcoded to `"2024-11-05"` regardless of what the client requests. Three concrete bugs are already recorded (but not yet filed as issues) in this repo's own `docs/adopt/2026-08-06T10-20-33Z--agentgateway-agentgateway.md`: (1) unknown notifications (`notifications/cancelled`, `notifications/progress`) and `ping` fall through to a default case that replies with a JSON-RPC error even though JSON-RPC 2.0 forbids replying to notifications at all; (2) every tool result is flattened to a single `TextContent` block — no `structuredContent`/`outputSchema`, no `resource_link`, incoming `params._meta` is silently discarded; (3) the hand-rolled Content-Length/line-mode frame parser (`mcpserver.go:191-290`) has zero fuzz coverage despite the ecosystem already using Go native fuzzing elsewhere (symaira-guard). Separately, `symaira-vault` never adopted `corekit/mcpserver` at all and maintains its own parallel `internal/mcp` stack — the exact duplication corekit exists to prevent still exists there.
  - **Proposed solution:** Pattern/library adoption, not a copy: prototype a `corekit/mcpserver` v2 (new major version, old API kept until migration completes) built on `github.com/modelcontextprotocol/go-sdk/mcp` — `mcp.NewServer` + `mcp.AddTool` + `StdioTransport` for the transport/dispatch layer, replacing the hand-rolled frame parser and method-string switch. This structurally fixes all three already-known bugs as a side effect (the SDK owns notification/ping handling, supports `structuredContent`/`outputSchema` natively via typed `AddTool[In,Out]`, and is a widely-used, tested implementation rather than an unfuzzed one) while additionally unlocking resources, prompts, sampling, elicitation, cancellation (`context.Context`-based, no manual cancel-flag bookkeeping), and spec-native progress/log notifications (`ServerSession.NotifyProgress`/`.Log`) for all seven current consumers going forward. Migrate exactly one low-risk consumer first — `symaira-fetch`, already flagged in `ECOSYSTEM.md`'s original migration-order rationale as having "the simplest MCP and config structures" — behind the new major version, verify its existing test suite still passes, and only then decide whether to roll out to the other six consumers (including offering `symaira-vault` a path off its parallel stack) or reject the migration and instead patch the three known bugs in place. `go.mod` requires `go 1.25.0` minimum; corekit is already on 1.26.4, so no toolchain blocker.
  - **Effort/Impact:** High effort (a new major version + one real consumer migration + a deliberate go/no-go decision), high impact if adopted (closes 3 known bugs plus 6 unimplemented spec capabilities across 7 consumers in one move instead of one-off patches); low effort and fully reversible for the spike itself (one consumer, new major version, old API untouched).

## Considered and rejected

- **Adopt `RegisterTyped`-style schema-from-struct-tags derivation from go-sdk's `AddTool`** — gate 2 (New): already shipped as `RegisterTyped[T]` in v0.7.0.
- **Adopt tool annotations (readOnlyHint etc.)** — gate 2 (New): already shipped as `ToolAnnotations` in v0.8.0.
- **File the notification/ping bug, the flattened-text-result gap, and the missing fuzz coverage as three separate issues here** — gate 2 (New): already discovered and documented today in `docs/adopt/2026-08-06T10-20-33Z--agentgateway-agentgateway.md`; re-filing them here would double-report the same underlying gaps this report's finding already subsumes and structurally resolves.
- **Adopt `python-sdk`'s FastMCP-style decorator API** — gate 1 (Transferable): relies on Python type-hint introspection with no Go equivalent; the portable idea underneath it ("derive schema from a typed function signature") is exactly what `RegisterTyped` already does.
- **Adopt `typescript-sdk`'s Standard Schema pluggable-validation interface** — gate 4 (Worth it): `corekit` intentionally has a minimal, fixed dependency set; making tool-schema validation a pluggable interface adds abstraction weight with no current consumer asking for an alternative validator.
- **Publish `symvault`/`symmemory`/etc. to the public MCP Registry, or stand up a self-hosted registry mirror seeded with Symaira's own `server.json` entries** — gate 4 (Worth it) for corekit specifically: the registry's `server.json` schema is aimed at public package-manager-distributed servers (npm/PyPI/OCI); Symaira's MCP servers are distributed as Homebrew-tapped Go binaries invoked locally, and `symaira-scope`'s discovery output is the more natural home for a registry-shaped manifest if this is pursued (see the `symaira-scope` companion report from this same scan).
- **Adopt go-sdk's `Server.AddResource`/`AddPrompt` as a standalone finding independent of the transport migration** — gate 4 (Worth it): no consumer has asked for file-like resources or reusable prompt templates yet; bundling this into the broader v2 spike (above) avoids a second disruptive API surface change later, so it is folded into the one finding rather than listed separately.

## Open questions

- Real build-time/binary-size delta of pulling in `github.com/google/jsonschema-go` and `github.com/segmentio/encoding` (go-sdk's transitive deps) on a CGO-free, cross-compiled CLI target — needs an actual `go build` + `go list -m all` comparison during the spike, not just a README read.
- Whether `symaira-vault`'s deliberate non-adoption of `corekit/mcpserver` was a considered decision (documented somewhere) or organic drift — worth checking before assuming vault would want to join a v2 migration at all.
- Whether the MCP spec's protocol-version negotiation (client requests a version, server currently ignores it and always answers `"2024-11-05"`) is a real interop risk today, or purely theoretical until a client actually requests a newer date — go-sdk would resolve this as part of the transport swap regardless.

Single best first step: spike `corekit/mcpserver` v2 on `github.com/modelcontextprotocol/go-sdk/mcp`, migrate `symaira-fetch` only, and report real numbers (bugs fixed, dependency weight, migration effort) before deciding on the other six consumers.
