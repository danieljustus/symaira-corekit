# Code continuation: symaira-appkit

## Goal and immutable starting point

Continue the code and integration work from the published repository, without needing a local chat, private reports or installed agent skills.

- GitHub repository: `danieljustus/symaira-appkit`.
- Branch: `handoff/20260930-cloud`.
- Base code commit before this document/checkpoint: `2a6b7b5c15916c946d3c93d45fa856367d4eb022`.
- Working directory for every command below: the checked-out repository root.
- Publication does not authorize a merge, release, tag, destructive cleanup or paid service.
- Continuation PR: #157. The original publication was a draft checkpoint. The subsequent request to complete issues and merge reviewed PRs authorizes its documentation integration; required checks still apply.

No source modifications were made by this work unit. The clean shared-library state and its continuation constraints are published as a reproducible checkpoint.

## Requirements, decisions and next task

No source change is pending from this work unit. Recheck any future consumer change independently and keep exact release pins; native UI/Keychain behavior needs macOS verification.

Keep products and their optional modules standalone. Preserve exact dependency pins, snake_case contracts, data integrity, authorization and MCP stdout discipline. Keep frozen fixture evidence and original Oracle ancestry unchanged until an explicit preservation design is accepted. Do not rewrite history, force-push, bypass branch protection, delete unique work, close unproven issues or reinterpret a passing subset as complete acceptance.

- No existing candidate PR was recorded for the selected code base.

## Setup and scoped verification

Clone the existing public repository, checkout `handoff/20260930-cloud`, verify its current remote HEAD, and read this file before making changes. Never substitute another branch or silently mix the alternatives.

```sh
git clone --branch handoff/20260930-cloud https://github.com/danieljustus/symaira-appkit.git
cd symaira-appkit
git rev-parse HEAD
git ls-remote --exit-code origin refs/heads/handoff/20260930-cloud
git status --porcelain=v1 -uall
```

The original local verification used Swift 6.4 and full Xcode on macOS. Follow `AGENTS.md` and use the Makefile: it selects a full Xcode toolchain without changing the machine-wide selection. Command Line Tools alone are insufficient. Package-manager caches are rebuildable, not required private inputs.

Scoped reproduction commands, not a claim of the complete product suite:

```sh
make toolchain
make test
```

Build command (not claimed executed unless listed in verification):

```sh
make build
```

Start/help command (not executed for live services/devices):

This is a shared Swift library; it has no application or daemon start command.

Use a fresh Swift build-output directory when comparing code variants. No provider/API secret is required for these scoped mock/unit checks. Do not use real credentials or application state. Do not enable paid model fallback.

## Dependencies and exclusions

Tracked lockfiles, manifests, generators and fixtures are the reproducible input. Build outputs (`target`, `.build`, `node_modules`, `dist`), dependency caches, coverage output and generated binaries are deliberately excluded and rebuilt. Older unrelated branches, private audit/planning reports, harness settings, personal records, real credential contents, local stores and original unrelated credential-store WIP are excluded, not hidden dependencies of the checks above. No raw chat or private memory is published.

Pinned Git dependency commits found in the selected top-level manifest: none in the inspected top-level manifests. Package managers must resolve these through public repositories; a fresh-checkout failure to fetch any is a concrete reproducibility blocker, not permission to alter a pin.

Native GUI/Keychain/Touch ID, signing, notarization, and real user-permission behavior need macOS/hardware and remain unverified by generic cloud execution. Network access to GitHub and applicable package registries is required for dependency setup. Production access, signing credentials and live-service secrets must be separately supplied through approved secret management, never this repository. No cloud job is launched by this document.

## Verification record

Prepublication secret-pattern/outgoing-history scans succeeded for the selected base. Exact WIP path/byte comparison is required for checkpoint variants. Product-acceptance and target-cloud runtime are **not checked** by these records.

No new source code was changed on this branch; the fresh remote-clone command results will be recorded below.

Fresh remote-clone verification was executed locally on macOS at published checkpoint `4695b01c2f8d8473da126fcfa82336078f2eb9ea`. The repository was cloned directly from GitHub, without copied worktree files, stashes or source/configuration overrides. The following scoped command chain exited **0**:

```sh
swift test
```

The command above is a historical record, not the recommended entrypoint for new runs. Package manager dependency caches were allowed; application state and credentials were not supplied. This verifies repository-contained inputs and these scoped checks, not every native acceptance criterion. Final documentation changes do not change the tested source; the published final HEAD must still be verified before continuation. Target cloud runtime, permissions, secrets and network gates: **not checked**.

During the 2026-10-03 documentation review, comparison with `main` confirmed that this PR changes only this file. In the Linux cloud checkout, `python3 scripts/test_select_xcode.py` passed all five tests and `python3 scripts/verify-approved-icon.py` verified 25 assets and six renders. `make toolchain` failed because full Xcode is unavailable; no native Swift build/test success is claimed for that environment. GitHub macOS CI remains the native build/test gate for integration.

## Copyable continuation request

Work in `danieljustus/symaira-appkit` on `handoff/20260930-cloud`. Verify the exact remote HEAD given by the final publication record, read `docs/handoffs/end-work-cloud.md`, run the setup and scoped checks, then: No source change is pending from this work unit. Recheck any future consumer change independently and keep exact release pins; native UI/Keychain behavior needs macOS verification. Respect all preservation and integration gates above.
