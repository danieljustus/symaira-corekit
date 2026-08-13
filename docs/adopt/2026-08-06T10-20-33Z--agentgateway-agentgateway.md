<!-- review: timestamp=2026-08-06T10:20:33Z  repo=danieljustus/symaira-corekit  head=2d7b776bbcde9e2fbc10e636eb77042391773e0b -->
<!-- adopt: source=agentgateway/agentgateway  source_ref=db62d60a8f5868afc3f9c46b327e7b08c6e4c452  source_url=https://github.com/agentgateway/agentgateway  depth=clone  license=Apache-2.0 -->

# Adoption Report — symaira-corekit ← agentgateway/agentgateway — 2026-08-06

## Sources

| Field | Value |
|---|---|
| SOURCE | `agentgateway/agentgateway` (https://github.com/agentgateway/agentgateway) |
| Ref analyzed | `db62d60a8f5868afc3f9c46b327e7b08c6e4c452` (main) |
| Language / License | Rust (plus TS UI, Go controller) / Apache-2.0 — code adoption permitted with attribution; nothing below proposes it |
| Health | 4.2k stars, last push 2026-08-05, not archived, `v1.4.1` released 2026-07-29 — healthy, multi-maintainer, MCP-spec-current |
| Scope | all facets, weighted to `architecture` (the `mcpserver` package) |
| TARGET | `danieljustus/symaira-corekit` @ `2d7b776` |

## Verdict

Only one corekit package overlaps this SOURCE: `mcpserver`. agentgateway is the opposite side of the
same protocol — a proxy that must survive every server's quirks — which makes it a good conformance
mirror for a library that every Symaira MCP server inherits. Three gaps show up, all in
`mcpserver/mcpserver.go`, all cheap: the dispatcher answers JSON-RPC notifications (which the spec
forbids and which `symaira-brain`'s own client code carefully avoids doing), `ping` is not answered
at all, and a tool result can only ever be one text block. Nothing else transfers: the rest of the
SOURCE is proxy, LLM-routing and Kubernetes machinery with no counterpart in a leaf-server library.

## What we already do as well or better

- Bounded framing → `mcpserver/mcpserver.go:22-25` caps a line and a framed body at 1 MiB, and the cap is documented as the reason `symaira-brain`'s client uses the same number; upstream applies equivalent caps only per-policy (`ext_authz.rs:60-67`).
- Panic containment per request → `mcpserver/mcpserver.go:311-317` recovers and answers `-32603`; upstream gets this class for free from Rust and has no analogue to copy.
- Tool behavior hints → `mcpserver/mcpserver.go:56-77` already emits standard `annotations` (adopted from the exa-mcp-server report, 2026-07-30).
- Dual framing support (Content-Length *and* line mode) → `mcpserver/mcpserver.go:191-250`; upstream's stdio path speaks line mode only.
- Zero stdio pollution → `logkit` to stderr by contract; upstream has the same rule but only for its stdio upstreams.

## Findings

- [ ] **[Architecture] Never answer a JSON-RPC notification, and answer `ping`**
  - **Status quo:** `mcpserver/mcpserver.go:322-334` dispatches purely on `req.Method`, and every method outside the four known ones falls through to `sendError(w, req.ID, CodeMethodNotFound, …)`. Since `jsonRPCResponse.ID` has no `omitempty` (`mcpserver/mcpserver.go:100-105`), a *notification* — which by definition carries no id — is answered with `{"jsonrpc":"2.0","id":null,"error":{…}}`. JSON-RPC 2.0 forbids replying to a notification, and MCP clients routinely send `notifications/cancelled` and `notifications/progress`; only `notifications/initialized` is swallowed today (`mcpserver.go:325`). `ping`, which several clients use as a liveness probe, also returns "Method not found". Every Symaira MCP server inherits both behaviors, and the ecosystem already knows the rule on the other side of the wire: `symaira-brain/internal/broker/protocol.go:17-24` uses `*int64` with `omitempty` specifically so that notifications never send `"id":null`. Upstream keeps requests and notifications strictly apart, with an explicit list of client *request* methods and a comment recording why drift in that list cannot 404 a typed request (`crates/agentgateway/src/mcp/mod.rs:56-80`).
  - **Proposed solution:** Pattern adoption (no code copied). Branch on a missing id before the method switch: a request without an id is a notification — dispatch it if known, drop it otherwise, and write nothing either way. Add `ping` returning an empty result. Unknown *requests* keep answering `-32601`. Add a test asserting that a notification produces zero bytes on the writer.
  - **Effort/Impact:** Low effort / high impact. One function, one struct tag, one test; it fixes a spec violation in six-plus shipped binaries at once and is fully reversible.

- [ ] **[Architecture] Let a tool return a real MCP result instead of a stringified one**
  - **Status quo:** `mcpserver/mcpserver.go:404-432` (`sendToolResponseRaw`) marshals the handler's return value and, when the result is not a JSON string, embeds the raw JSON *as the `text`* of a single `TextContent` block. The comment there records this as a fix for a schema violation — and it is — but it fixed the violation by flattening: `structuredContent`/`outputSchema` cannot be produced, and no non-text content (image, audio, `resource_link`, embedded resource) can be expressed at all, so a consumer that needs one has to leave the shared server or smuggle JSON through a text field. The cost is already visible downstream, where `symaira-brain` flattens the same result a second time (`symaira-brain/internal/gateway/server.go:208-218`). `params._meta` on `tools/call` is likewise discarded (`mcpserver/mcpserver.go:379-383`), removing the spec's out-of-band channel. Upstream treats a tool result as a typed structure it can inspect and rewrite item by item — resource URIs (`crates/agentgateway/src/mcp/handler.rs:895-925`) and `_meta` (`crates/agentgateway/src/mcp/apps.rs:54-90`) — and never collapses it to text in transit.
  - **Proposed solution:** Pattern adoption, strictly additive. Introduce an optional result type (a content-block slice plus an optional `structuredContent`) that a handler may return; when a handler returns anything else, keep today's `any` → text behavior byte-for-byte. Optionally expose the incoming `_meta` to handlers through the context. No consumer has to change.
  - **Effort/Impact:** Medium effort / medium impact. Additive and reversible; it unblocks `symaira-brain`'s result pass-through, which is filed in that repo's report from the same batch.

- [ ] **[Architecture] Fuzz the hand-rolled frame parser**
  - **Status quo:** `mcpserver/mcpserver.go:191-290` implements Content-Length framing, framed-vs-line-mode detection and a length-limited line reader by hand, over bytes from a peer the library does not control — a child process for `symaira-brain`, and an untrusted upstream server once `symguard`'s proxy exists. `rg 'func Fuzz'` across corekit returns nothing: the 787-line test file covers the cases the authors thought of, which is precisely the class of coverage a malformed-header or truncated-body input escapes. The technique is already established in the ecosystem — `symaira-guard/internal/config/fuzz_test.go`, `internal/model/fuzz_test.go` and `internal/policy/fuzz_test.go` all use Go's native fuzzing — just not on the one parser every Symaira tool shares. Upstream maintains a dedicated fuzz workspace whose targets are exactly its untrusted-input parsers, with a checked-in corpus (`fuzz/fuzz_targets/proxy_protocol.rs`, `cel_expression.rs`, `llm_request_conversions.rs`, `fuzz/corpus/`).
  - **Proposed solution:** Pattern adoption. Add `FuzzReadRequest` in `mcpserver`, seeded with framed, line-mode, truncated, header-only, oversized-`Content-Length` and non-UTF-8 inputs; assert only that it neither panics nor blocks. The seed corpus runs as an ordinary test in CI (Go replays seeds without `-fuzz`), so no CI time budget is needed.
  - **Effort/Impact:** Low effort / medium impact. One test file; additive, no production change.

## Considered and rejected

- **Generating a JSON Schema and a markdown reference for config from the type definitions** (`schema/config.json`, `schema/config.md`, the `schema!` macro, `crates/xtask`) — gate 4 (Worth it): Rust gets it from a derive macro; in Go it means a reflection-based generator plus doc-comment extraction, for a `configkit` schema that is small and mostly defined in the consumer repos anyway. Revisit if one consumer's TOML surface grows past what a hand-written table can track.
- **CEL as a shared expression language** (`crates/celx`, `crates/cel-fork`) — gate 1 (Transferable) and gate 4 (Worth it): no corekit consumer evaluates user-supplied expressions today, and the same candidate was rejected on cost in the `symaira-guard` report from this batch.
- **Server-initiated notifications and the `listChanged` capability** (`crates/agentgateway/src/mcp/handler.rs:1427-1431`) — gate 3 (Better): every consumer registers a static tool set at startup, so there is no change to announce; the one plausible consumer (`symaira-brain`) has catalog refresh explicitly out of scope in `symaira-brain#182`.
- **Streamable HTTP and SSE transports** (`crates/agentgateway/src/mcp/streamablehttp.rs`, `sse.rs`) — gate 3 (Better): every consumer is a local stdio server spawned by the harness, and no consumer has asked for an HTTP transport. Adding one would put session state, auth and CORS into a library that currently has none of it.
- **Session management, idle TTLs, prefix modes, multiplexed merge streams** (`crates/agentgateway/src/mcp/session.rs`, `mergestream.rs`) — gate 1 (Transferable): `mcpserver` is a leaf server, not a proxy; the multiplexing counterpart lives in `symaira-brain`.
- **Prompts and resources support** (`crates/agentgateway/src/mcp/handler.rs:840-930`) — gate 3 (Better): no consumer exposes either, and speculative protocol surface in a shared library is maintenance without a user. Add it when a consumer needs it.
- **OAuth/OIDC/JWT and RBAC** (`crates/agentgateway/src/mcp/auth.rs`, `rbac.rs`) — gate 1 (Transferable): local stdio servers authenticated by process ownership; ecosystem policy belongs to `symguard`/`symbrain` by architectural decision.
- **Their crate-per-concern workspace split** (`crates/*`) — gate 2 (New): corekit is already one package per concern with an explicit standalone-first contract.
- **Their `deny.toml` / `osv-scanner.toml` supply-chain config** — gate 2 (New): `govulncheck` and Dependabot already cover this; pinning the tool version is separately tracked in #95.

## Open questions

- Which protocol version `mcpserver` should advertise. `ProtocolVersion` is pinned to `2024-11-05` (`mcpserver/mcpserver.go:20`) and `handleInitialize` (`mcpserver/mcpserver.go:338-352`) ignores whatever the client requested. Upstream negotiates because it must bridge mixed client/server versions; a leaf server echoing a version it does not implement would be worse than pinning. The evidence that would settle it: a real client that refuses `2024-11-05` — none observed so far.
- Whether `_meta` should be surfaced to handlers or only preserved. `symaira-brain` may want it as the identity channel (see that repo's report); until a consumer reads it, preserving it costs nothing and exposing it commits to an API.

**First step:** fix the notification reply in `mcpserver/mcpserver.go` — it is a one-branch change that removes a spec violation from every Symaira MCP server at once.
