# Current continuation (2026-10-03)

The historical unregistered checkpoint below is preserved verbatim. The new
maintainer goal authorizes completing and merging PR #398 after its gates.
Three unchanged provenance-approved captures are now registered, with a separate
full reconstruction recorded in `docs/rust-port/evidence/fs-frozen-registration-20261003.json`.
The Linux native wrapper passed on the registration working tree: 13 cases,
nine controls, exactly one named strict-v1 test, both mutations, executable
Go/Git denial controls and no forbidden invocation. POSIX replay uses native
capture umask `022`; the original cloud `077` mismatch was retained as a failure.
Ordinary three-platform CI passed at #398 head
`1e3cb58735ea07668583e8159ceab7745755db7e` in
[run 37141793738](https://github.com/danieljustus/symaira-corekit/actions/runs/37141793738).
The complete #401 candidate also passed ordinary CI and the native Go-free
aggregate on all three platforms. Integration now proceeds through cumulative
PR #401, which contains the reviewed #398–#400 changes; later heads and
integrated `main` still require their own gates. #368 and consumer/release/
Go-retirement gates stay open until their respective acceptance is verified.

# Frozen FS/SEC evidence: code and review continuation

## State and immutable code checkpoint

This is preserved **unfinished work**, not migration acceptance. Keep the pull request draft until all gates below pass. No anchor is registered, and no issue is closed by this handoff.

- Repository: `danieljustus/symaira-corekit` (public, not a fork).
- Continuation branch: `agent/issue368-fs-freeze-20261003`.
- Base code commit: `5fc5299a56e96b6007fda7d8900363f3aa6ba282`.
- Integration base: merged PR #393, `ff26856c91abca26311be8b06cd4e416a9e8cb06`.
- Primary issue: #368. Defects tracked separately in #396 (Windows checkout configuration) and #397 (embedded compilation inputs absent from source inventory).
- Continuation draft PR: [#398](https://github.com/danieljustus/symaira-corekit/pull/398). Keep it draft and auto-merge disabled. The final documentation/evidence HEAD is given by the publication record. Verify the exact remote branch before continuing; do not substitute the local or remote default branch.

Read `AGENTS.md`, `docs/product-boundaries.md`, `docs/rust-port/fs-path-contract.md`, and `docs/rust-port/work-items.json`. CoreKit remains a domain-free shared backend library, separate from AppKit and product policy. Keep consumer tools standalone and require two real consumers for shared modules. No credential crypto, browser engine or native automation is moved here.

## What changed and what remains

The frozen FS/SEC harness is in `scripts/rust-port/fs_secret_oracle.py`; its independent anchor map in `fs_secret_anchors.py` is intentionally empty. Default replay is Go/Git-free. Live capture is additive and requires explicit `GO_ORACLE=1`. The new `rust-fs-secret-frozen-contract` Make target runs real Rust FS/secretref checks and frozen replay. The existing live target remains opt-in; audit, deny and Miri security gates are not removed.

Actual native Go captures at the base code commit passed on Darwin/arm64, Linux/amd64 and Windows/amd64 in [run 37107725386](https://github.com/danieljustus/symaira-corekit/actions/runs/37107725386). Each has 13 FS/SEC cases, nine path controls, 19 command records and 38 original stdout/stderr streams. This capture-only dispatch intentionally skips the still-unanchored native Rust acceptance job. Ordinary PR/main execution requires that job. A successful capture workflow is **not** successful native Rust acceptance.

The parent independently verified source, exact fixture/probe/stream bytes, schema/types, pre/post clean identity, all six module inputs and every recorded official Go SDK/compiler input. It exercised an observation mutation against unchanged raw streams and rejected it for every target. This is provenance verification, not independent registration approval or Rust acceptance.

| Native target | Exact fixture SHA-256 | Recorded SDK inputs |
| --- | --- | ---: |
| darwin-arm64 | `802fb2e1f85d07be948ef81361953196e117ad74ef4e66749acf4cdc70deda5a` | 1134 |
| linux-amd64 | `6bb7b00fe62a957c9710ebb0dd0642c4e94000597f4fc7ad6714188ff948930a` | 1194 |
| windows-amd64 | `b6219a2cd8c83d6fddbd4b3c0956e8c7ee306012c4092f7e1e8a859f50a55cb7` | 1091 |

An earlier registration review of `b069b399d21024b89d3cdbabea83731a130d4c5f` rejected approval because it did not independently reconstruct the original raw/module bindings. Those captures additionally omitted two files actually compiled by Rust `include_str!`: `contracts/secret_refs.json` and `testdata/rust-port/fixtures/fs-secret/corpus.json`. A disposable executable counterexample proved the old preflight accepted modifications to either file. The corrected base inventories both; one cumulative regression checks mutation and restoration. The missing-anchor test now stays active after anchor registration. Do not register b069 or edit historical observations to manufacture freshness.

The corrected-source independent review has now approved all three exact digests **for native Go-capture provenance only**, after independently executing the verifier (exit 0) and reviewing the complete four-file b069-to-base delta. The [source-bound review record](evidence/2026-10-03-fs/independent-5fc-provenance-review.json) preserves the exact source, digests, execution and limited scope. Its hashes were compared to the published original fixture bytes; the reviewed harness/compiler inputs remain unchanged. This is not anchor registration, successful Rust replay or migration acceptance. No anchor was changed when recording the result.

## Published evidence and inputs

All fresh raw inputs are committed under `docs/handoffs/evidence/2026-10-03-fs/`, separate from the accepted fixture directory. Three compressed bundles contain each original fixture and all 97 original raw files, including the small compiled Go probe needed to verify its binding. These are inert evidence: do not execute the retained probe. Bundle contents and every file SHA-256 are listed in `bundle-inventory.json`. They are **not** automatic anchors.

The same directory contains the 630-file source manifest, portable stdlib verifier, relative capture locations, original embedded-input counterexample, rejected earlier review, parent results, and remote checkpoint/readback records. Pinned source snapshots are reproduced using Git objects; official SDK archives are fetched from their checksum-pinned public URLs. No local chat, memory, installed skills, private path, generated cache or developer machine is needed.

Additional preserved source checkpoints, all in this repository, are alternatives/historical inputs, not branches to merge:

| Branch | Exact preserved HEAD |
| --- | --- |
| `agent/issue368-freeze-20261002-091556` | `808965742f3bb3ee06164bbb9d554231911f4fac` |
| `agent/issue368-process-review-20261002` | `bdc55423a7cb401d31bf2005cb00af2ab34d2644` |
| `agent/issue368-static-update-20261002` | `b028717ef247c1817bd9285634db7a29157e9661` |

Prior merged work and issue readbacks are in `published-checkpoints.json`; production fixes and accepted older fixture families are already tracked in the merged repository. Worker-only prototypes were superseded by reviewed implementation but their non-identical original bytes are separately preserved, not deleted. Do not cherry-pick or merge them into the accepted source:

- `handoff/20261003-static-prototype` at `816de140e9c664b7f4c03745706b5320287e9cfe` preserves all 30 previously uncommitted worker source/diagnostic paths byte-for-byte. Its own handoff is `docs/handoffs/2026-10-03-static-prototype.md`; its per-path inventory is `docs/handoffs/static-prototype-inventory.json`. No tests or acceptance are claimed for it.
- `handoff/20261003-bounded-prototype` at `b2cc2d09d861cc3b2577bbc60711ce7ac8a41264` preserves the original committed bounded-process prototype, including its historical test log. That log is not current native acceptance.

The original worker checkout is intentionally left dirty and unchanged; its exact safe contents now have a verified remote copy. Original divergent local main and earlier September handoffs predate this work and are excluded from this continuation; no global cleanup or synchronization is authorized.

## Setup from GitHub only

Working directory for build/test commands: the repository root. Tools: Git, curl, Python **3.14**, make, Rust/Cargo **1.98.0** with rustfmt/Clippy. Locally observed: Python 3.14.2, Rust/Cargo 1.98.0, Go 1.27.1. The capture oracle uses **Go 1.26.6**, never the locally observed default. No Go compiler is executed by the evidence verifier or default replay. Install the pinned Rust toolchain if absent:

```sh
git clone --branch agent/issue368-fs-freeze-20261003 https://github.com/danieljustus/symaira-corekit.git
cd symaira-corekit
git rev-parse HEAD
git ls-remote --exit-code origin refs/heads/agent/issue368-fs-freeze-20261003
git status --porcelain=v1 -uall
rustup toolchain install 1.98.0 --profile minimal --component rustfmt --component clippy
python3 --version
```

Require Python 3.14 and compare HEAD to the final publication record. The following POSIX-shell procedure constructs a fresh private evidence workspace solely from tracked bundles, Git source objects and public SDK downloads. On Windows use Python 3.14 and equivalent Git/tar/download operations; Windows execution is not established by POSIX reproduction.

```sh
EVIDENCE=docs/handoffs/evidence/2026-10-03-fs
CHECK_DIR=$(mktemp -d)
cp "$EVIDENCE/verify-fresh-fs-captures.py" "$EVIDENCE/source-5fc5299-manifest.json" "$EVIDENCE/fresh-5fc-native-locations.json" "$CHECK_DIR/"
mkdir "$CHECK_DIR/source-5fc5299" "$CHECK_DIR/oracle-f3d3eb7-source" "$CHECK_DIR/sdk"
git archive 5fc5299a56e96b6007fda7d8900363f3aa6ba282 | tar -xf - -C "$CHECK_DIR/source-5fc5299"
git archive f3d3eb79b9b1f31b4f973d2ed518a8292cedf588 | tar -xf - -C "$CHECK_DIR/oracle-f3d3eb7-source"
for target in darwin-arm64 linux-amd64 windows-amd64; do
  tar -xzf "$EVIDENCE/$target.tar.gz" -C "$CHECK_DIR"
done
for sdk in go1.26.6.darwin-arm64.tar.gz go1.26.6.linux-amd64.tar.gz go1.26.6.windows-amd64.zip; do
  curl --fail --location "https://dl.google.com/go/$sdk" --output "$CHECK_DIR/sdk/$sdk" || exit 1
done
PYTHONDONTWRITEBYTECODE=1 python3 -B "$CHECK_DIR/verify-fresh-fs-captures.py"
```

The verifier checks every SDK archive SHA before reading its inputs. It verifies exact clean source identity, full manifest, strict capture schema, native targets, original streams, original probe digest, original case/control values, all six module manifests (including original Windows CRLF writer bytes), SDK/compiler bindings, the two embedded inputs and observation-mutation rejection. It creates only a derived verification report in the private check directory. Never run Python with `-O`, which disables assertions. Original raw evidence is not rewritten.

Scoped source commands:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -W error -m unittest discover -s scripts/rust-port -p test_fs_secret_oracle.py -v
python3 -B docs/rust-port/validate.py
cargo fmt --all --check
cargo fetch --locked
CARGO_NET_OFFLINE=true make rust-fs-secret-frozen-contract
```

At this unanchored checkpoint, the last command must fail specifically with **no independently reviewed anchor** after prerequisite checks pass. This fail-closed outcome is expected and is not acceptance. Inspect stderr; an unrelated compilation, filesystem or network failure is not an acceptable substitute. Run security tests in an OS-private temporary directory, not underneath group-writable report storage. Do not weaken filesystem ownership/permission protections to make external-volume scratch pass.

Full legacy Go checks, if required later, are `make test`, `make lint`, `make build` using the Go version compatible with `go.mod`. Full migration/security gates exceed this scoped handoff. This is a library: no server or application start command is required.

No provider, signing, vault or production credentials are needed for these checks. Optional variable names: `TMPDIR`, `CARGO_TARGET_DIR`, `CARGO_BUILD_JOBS`, `CARGO_NET_OFFLINE`, `PYTHONDONTWRITEBYTECODE`. A new live capture additionally uses the documented `GO_ORACLE`, `GO_ORACLE_BIN`, `GOTOOLCHAIN`, `GOPROXY`, `GOSUMDB`, `GOENV`, `GOWORK` controls; do not run it implicitly. Windows checkout must set `core.autocrlf=false` before checkout to match the sanitized clean-source verifier.

## Verification and limitations

Previously executed on the corrected source: 18 focused Python guard tests passed, actionlint passed, ledger validation passed. Actual Darwin CI-wrapper execution passed its real prerequisite Rust checks/Clippy and failed at the missing independent anchor; explicit Go/Git denial controls each exited 97, and the gate made no forbidden invocation. Native capture-only run 37107725386 succeeded, with all three capture jobs independently read back at the exact base SHA. Complete parent provenance verification passed for all three raw captures with observation-mutation rejection.

An actual fresh HTTPS clone at `0ccad40fa518bd3edf17572460b1b6b1b95a2f7f` reconstructed the exact source/oracle Git objects, verified every preserved bundle file, freshly downloaded all three SDK archives, and passed the portable provenance verifier, 18 guard tests, ledger validation, Cargo formatting and locked dependency fetch. The offline frozen Make target executed its real Rust prerequisites and returned exit 2 specifically for the absent independent anchor. Detailed [fresh-checkout results](evidence/2026-10-03-fs/fresh-checkout.json) are preserved. The final changes after that tested checkpoint are documentation/result records only; captured compiler and harness bytes remain unchanged.

A local clean clone proves repository completeness for the commands exercised, **not** execution in another cloud runtime. Final PR/HEAD CI is read back separately; pending or failed checks stay visible. No extra cloud job, paid model/provider, release, credential creation or deployment is authorized by this document.

Cloud runtime, permissions, secrets, network gates and native Rust acceptance: **not checked** by the local publication test. GitHub and public crate/SDK registry network are required during setup; after fetch, the frozen Rust gate runs offline. Native final Rust acceptance needs Darwin/arm64, Linux/amd64 and Windows/amd64 runners. No local GUI, native automation, physical device, private repository, LFS object or submodule is needed for the supplied provenance and focused source checks. Dependency/build caches and official downloaded SDK copies are reproducible and deliberately excluded. Private instruction/prompt/event logs, raw chat, personal data, credentials, `.env` contents and unrelated old audits are not published.

## Required next work and hard gates

1. Read the completed independent provenance review and confirm its exact source and all three approved digests still match the preserved evidence. Re-run the public verifier when reconstructing the workspace. If any captured compiler/harness input changes, repair and recapture rather than inheriting this limited approval.
2. Make the separate anchor decision, then register the **unchanged** approved fixture bytes and exact hashes in the fixture index and independent anchor map. Preserve historical evidence and raw failures. Review registration separately.
3. Exercise the default frozen entrypoint with real native Go/Git-denying shims, exactly one named strict-v1 Rust test pass, both intended mutation controls and retained raw output. Then obtain ordinary exact-head native Rust CI and independent review. Capture-only CI, cross-compilation, test-only anchors and diagnostic runs are insufficient.
4. Keep #368 open beyond this FS/SEC slice: aggregate gates and remaining oracle families still need accounting. Keep #371/#372 quarantined pending the Rust distribution-channel decision; do not repeat the unanswered question, publish crates or create/rotate credentials.
5. Use ordinary protected-branch PR integration only after exact-head gates. No admin bypass, force-push, Go removal, release, destructive cleanup or automatic closure from a worker commit. Missing or malformed evidence is `protocol-invalid`, never success.

## Copyable continuation request

Work in `danieljustus/symaira-corekit` on `agent/issue368-fs-freeze-20261003` at the final published HEAD. Read `docs/handoffs/2026-10-03-fs-frozen-cloud.md` and the completed independent provenance review. Verify HEAD, setup, source and the three approved digests; the next work is a separate anchor decision and reviewed exact-byte registration, not another incomplete capture review. Keep the PR draft, preserve historical evidence, require exact-head native Rust acceptance, keep #368 open, and do not publish or create credentials for #371/#372.
