# Rust-port harness isolation

Generic fixture regeneration updates only files emitted by its pinned Go
generator. It merges into the existing fixture tree and does not delete
independently owned corpora such as `fs-secret`, `llm` or `update`. Removed or
obsolete artifacts need an explicit owner-reviewed cleanup, never a blanket
tree replacement. Read-only checks still reject missing or changed emitted
artifacts. `make port-fixture-source-check` exercises the real default writer
in a disposable tree, verifies sibling corpus bytes, and rejects an owned-file
mutation; tracked fixture trees are not regeneration-test destinations.

The differential runner executes each implementation in a fresh tree containing isolated `HOME`, `USERPROFILE`, XDG config/data/cache/state/runtime roots, temp roots and working directory. It inherits only executable-discovery variables and accepts case variables from an explicit `PORT_*` / `SYMCOREKIT_*` / proxy allowlist. Reserved roots, locale, timezone, terminal and deterministic clock/seed variables cannot be overridden by a case.

The runner captures exit status and signal identity separately, raw stdout/stderr, a recursive path/type/mode/hash manifest, configured SQLite query snapshots, HTTP transcript sidecars and process-argv sidecars. Timeouts kill the process group/tree and wait for bounded cleanup. The self-test proves Go↔Go equality, deliberate-output-mutation rejection, reserved-variable rejection, side-effect capture and parent-plus-descendant cleanup on the native host.

Stdin and setup files declare their representation explicitly as UTF-8, JSON
or base64. The runner decodes them to bytes and never uses platform text-mode
writes, so NUL, invalid UTF-8 and CRLF fixtures survive unchanged. Normal
Go↔Rust parity rejects the same path, filesystem identity or executable hash;
same-binary execution exists only inside the explicit harness self-test.

This is **not an OS security sandbox**. A temporary home does not prevent network, keychain, credential-store or arbitrary absolute-path access. Package-family oracle commands must therefore inject fake HTTP, subprocess and keychain adapters; cases that cannot do so need a separately reviewed native sandbox before they become parity gates. RUST-001's foundation probe performs no network, keychain or external subprocess operation.

## Frozen MCP process observations

`mcp-differential.py --check` and `mcpcfg-differential.py --check` execute the
current Rust production-facing fixture binaries against immutable, native Go
observations. They preserve every existing corpus input, exit/stdout byte check,
stderr policy and NUL check. Base64 output fields retain raw process bytes.
Each run must execute all 46 MCP or 24 MCP-config cases and reject a changed
expected stdout against actual Rust output, not just against another JSON file.

MCP-011 declares a bounded request/response exchange in the same server
process. Its three original requests retain identical byte representations;
each reply must arrive before the next request is sent. This proves that the
server recovers from the panic and serves the subsequent ping without making
an arbitrary assumption about burst-input thread scheduling. Output is never
sorted or canonicalized. The original burst observations remain in historical
captures; all other corpus cases retain their original full-stream exchange.

`frozen_process_anchors.py` pins independently reviewed whole-capture digests.
Captures bind the original Go Git commit/tree, exact toolchain and binary,
oracle helper, input corpus, per-case stdin, generator and capture-helper code.
Native output sets are selected by OS; capture architecture is recorded, not
claimed as execution evidence for another architecture. Frozen verification
does not require Git, Go or the original Go helper file. It fails closed if a
native capture is missing or its identity, provenance or bytes are changed.

For explicit fresh Go verification use `GO_ORACLE=1` with `--check`. For a new
capture use `GO_ORACLE=1 python scripts/rust-port/mcp-differential.py --capture
/absolute/new-output.json` (and the corresponding MCP-config command). Capture
uses exclusive creation and never overwrites accepted history. Native CI
recapture is a `workflow_dispatch` input `go_oracle=true`; uploaded captures
are diagnostic until their source, complete case set and actual Rust replay
have been reviewed and the trusted anchors updated. Ordinary MCP CI remains
Go-free. The Go, update, security, Miri and distribution gates are unchanged.
