# Rust-port harness isolation

The differential runner executes each implementation in a fresh tree containing isolated `HOME`, `USERPROFILE`, XDG config/data/cache/state/runtime roots, temp roots and working directory. It inherits only executable-discovery variables and accepts case variables from an explicit `PORT_*` / `SYMCOREKIT_*` / proxy allowlist. Reserved roots, locale, timezone, terminal and deterministic clock/seed variables cannot be overridden by a case.

The runner captures exit status and signal identity separately, raw stdout/stderr, a recursive path/type/mode/hash manifest, configured SQLite query snapshots, HTTP transcript sidecars and process-argv sidecars. Timeouts kill the process group/tree and wait for bounded cleanup. The self-test proves Go↔Go equality, deliberate-output-mutation rejection, reserved-variable rejection, side-effect capture and parent-plus-descendant cleanup on the native host.

Stdin and setup files declare their representation explicitly as UTF-8, JSON
or base64. The runner decodes them to bytes and never uses platform text-mode
writes, so NUL, invalid UTF-8 and CRLF fixtures survive unchanged. Normal
Go↔Rust parity rejects the same path, filesystem identity or executable hash;
same-binary execution exists only inside the explicit harness self-test.

This is **not an OS security sandbox**. A temporary home does not prevent network, keychain, credential-store or arbitrary absolute-path access. Package-family oracle commands must therefore inject fake HTTP, subprocess and keychain adapters; cases that cannot do so need a separately reviewed native sandbox before they become parity gates. RUST-001's foundation probe performs no network, keychain or external subprocess operation.
