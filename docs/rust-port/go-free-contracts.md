# Native contract verification without a Go toolchain

## Accepted integrated-main execution (2026-10-05)

The complete aggregate passed on Linux, macOS ARM64 and Windows at main
`1f3a7276500042121fe2d79a545462a15675aadc` in
[run 37331109179](https://github.com/danieljustus/symaira-corekit/actions/runs/37331109179).
[The source-bound evidence index](evidence/status-reconciliation-20261005.json)
records the original reports, archive digests, bounded-output hashes and ordinary
CI job/log identities. Both Go-absent and native Go-denied phases succeeded;
the denial control ran and the functional aggregate never called Go.
All six update lanes, the checker mutation, FS controls/mutations, Foundation,
LLM, MCP/config and SQLite corpora, and real signed-release acceptance executed.
The prior candidate/container observations below are historical, not unresolved
integrated-main gates. A later source head still needs its own exact-head CI.
This closes native library acceptance, not consumer release, observation,
standalone/rollback or Go-retirement gates.

## Running the gate

Use `make rust-contracts` for the complete native functional aggregate. It runs
Foundation/wire, FS/secret references, MCP and MCP configuration (including their
actual process corpora), LLM, SQLite, all update families and real signed-release
acceptance. The same target runs with Go absent from PATH and with a compiled
Go-denial executable. Cargo dependencies must be populated first; replay uses
offline, locked Cargo execution. Rust 1.98, Python 3.14, Make, OpenSSL, curl and
the pinned real Cosign CLI are needed. Git remains required for SQLite ancestry
verification. No operator installation is replaced.

`GO_ORACLE=1` explicitly enables live Go regeneration while Go remains. The
existing original generators and parity assertions are retained. Go-only capture
isolation tests run explicitly in regular Go CI; their skipped entry in the
Go-free helper tests is not native Rust acceptance evidence. Every frozen Rust
family still executes its actual nonzero tests and mutation controls. Security,
Miri, full workspace hardening, public API and released consumer gates retain
their separate required CI lanes; the portable functional aggregate does not
claim native Miri execution on Windows.

## Remaining update original recordings

Native capture run
[37141133260](https://github.com/danieljustus/symaira-corekit/actions/runs/37141133260)
at immutable source `8670450fbd3bd4d57a4c737f29abec113dd8eb70` executed all three
native platforms with pinned Go 1.26.6 and private HOME/XDG/TMP roots. Separate
registration downloaded every archive, checked its GitHub SHA-256, reconstructed
all Git inputs and official SDK/compiler inputs, compared original raw stdout
with every observation, and rejected changed observations. Fixed hashes are
independent of the producer and editable provenance sidecars. Original JSON,
stdout and stderr bytes are retained under `fixtures/update/native-v1` with
checkout newline conversion disabled. See
[`evidence/update-frozen-registration-20261003.json`](evidence/update-frozen-registration-20261003.json).

| Original native family | Cases per platform | Rust acceptance retained |
| --- | ---: | --- |
| Request | 13 | headers/errors; TLS 1.2 rejection, weak control and TLS 1.3 acceptance |
| Cache | 7 | actual request/expiry/forced-refresh cache behavior |
| Cache persistence | 7 | real byte normalization, modes, replacement and cache-byte mutation |
| Cosign contract | 13 | process/fetch behavior, TLS/body/redirect boundaries and body mutation |
| Apply | 17 | public replay and production Applier; all six existing filesystem mutations |
| Cancellation | 16 | pre-cancel identity, actual TLS cancellation/rollback and owned native process-tree reap |

The TLS fixtures use ephemeral test identities and loopback-only servers. Explicit
test clients trust the generated DER certificate; production TLS policy is
unchanged. A Rust native fixture replaces only the Go process-tree stand-in; it
is never used for signature acceptance. Real signed acceptance continues to
download pinned public Vault 0.22.1 bytes, run real Cosign, reject tampering and
wrong identity, and replace only a disposable target.

The implementation decision uses Python's existing standard-library TLS server
and the already available OpenSSL CLI instead of adding a server framework or
new production Cargo dependencies. This keeps test transport separate from the
shared library and preserves the captured Cargo inputs. The small native Rust
process stand-in preserves executable process-tree behavior on all three OSes;
an interpreted script would not provide the Windows ownership regression.

The untrusted certificate fixture uses RSA, matching Go's original `httptest`
certificate; the explicitly trusted protocol fixtures retain Ed25519. Native
Windows run `37144921600` accepted the trusted protocol controls but classified
the new untrusted Ed25519 identity as a generic network error. Matching the
original certificate algorithm preserves the required certificate-error
assertion; the corrected native run must confirm it. Real signed acceptance
also creates its own private HOME/XDG/TMP roots when invoked outside the aggregate,
so standalone execution cannot write verifier state into the operator's home.
The local run with the pinned real Cosign 3.0.5 passed valid, tampered,
wrong-identity and disposable installation checks.

The corrected Windows run `37145832091` passed Request, Cache/Persistence,
Cosign and Apply before exposing canonical readiness paths with the local-drive
`\\?\` prefix. The fixture now removes only that equivalent Windows drive
prefix before its existing private-root, no-symlink and exclusive-create checks.
Native controls exercise the prefixed valid path and a prefixed escape; UNC
paths do not gain access. No cancellation, rollback or process-tree assertion
is removed. Complete Windows acceptance remains pending the corrected run.

The generated sandbox roots are canonicalized before HOME/XDG/TMP are exported:
native Windows logs include the `RUNNER~1` DOS spelling, while readiness guards
resolve their private root. Resolving only the guard can reject an equivalent
generated client path. Identity creation has a separate bounded 45-second setup
budget after native OpenSSL RSA generation exceeded 15 seconds in run
`37147556899`; HTTP and cancellation deadlines are unchanged. An actual RSA TLS
preflight rejects default trust and accepts only the explicitly trusted fixture.
Failure artifacts now retain raw Cargo output as well as the outer Make log.

Regular Windows run `37148284785` rejected CRLF-converted `go.mod` before
update replay, even though the clean native aggregate passed on both Linux and
Windows. Root `go.mod` and `go.sum` now have explicit LF checkout attributes,
like the other hashed Go/Python/Cargo sources. Exact original byte guards and
all recorded hashes remain unchanged; a real CRLF-configured checkout verifies
the correction rather than normalizing changed input inside the verifier.

Linux run `37144921600` at `0c25794a9a11f4b2d4b784dc91b3086dbb86d685`
passed both complete Go-absent and Go-denied phases. The filtered PATH views
now live outside the evidence directory: uploading those system-tool symlinks
would archive installed programs rather than contract evidence. Raw contract
logs and the source-bound reports remain in the upload. This Linux result does
not replace the corrected three-platform integration-head gate.

Each native update replay binds current Rust/Cargo/helper inputs before and after
execution and retains bounded raw Cargo output. Changed fixture or raw-stream
bytes fail before Cargo starts. The combined native workflow must pass at the
actual integration head before #368 can close. Registration or local partial
preflight alone is not completion evidence.

Local Linux preflight has passed Request, Cache, Persistence, Cosign and all Apply
mutations, plus the actual 16-case TLS cancellation/rollback and its mutation.
The cloud container does not reliably reap orphan zombies, so complete native
process-tree acceptance remains a hosted-runner gate. No assertion is weakened
for this container limitation.
