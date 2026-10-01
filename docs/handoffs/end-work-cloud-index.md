# Repository continuation index

The following public branches preserve the relevant code candidates and independent incomplete variants. Read the repository-local continuation document before editing. Nothing in this index authorizes a merge, tag, release or destructive cleanup. All scoped local checks passed on fresh GitHub clones; target-cloud runtime is not checked. Product acceptance and required CI are separate gates.

The table records the verified code/document checkpoint immediately before this index was added. For the CoreKit `handoff/20260930-cloud` branch, this index is a later documentation-only commit; obtain its final current HEAD with `git ls-remote`. This avoids a circular self-commit reference.

| Repository | Branch | Verified checkpoint | Draft PR | Continuation document |
|---|---|---|---|---|
| `danieljustus/symaira-corekit` | `handoff/20260930-cloud` | `218d9a07a7ca5ae4b3049e6f0ca09ee1e81b59d6` | #358 | `docs/handoffs/end-work-cloud.md` |
| `danieljustus/symaira-desktop` | `handoff/20260930-cloud` | `96a465b6a3ab2f3ed05c55e0859235102fe38523` | #1129 | `docs/handoffs/end-work-cloud.md` |
| `danieljustus/symaira-appkit` | `handoff/20260930-cloud` | `53725628129dcc21a77512154cfc127ee2fa3736` | #157 | `docs/handoffs/end-work-cloud.md` |
| `danieljustus/symaira-fritz` | `handoff/20260930-cloud` | `28e62c323d47c1897e43ca1d772b180739507b34` | #275 | `docs/handoffs/end-work-cloud.md` |
| `danieljustus/scoop-bucket` | `handoff/20260930-cloud` | `84439363c524c0255194799c4c153ea482eb7afa` | #2 | `docs/handoffs/end-work-cloud.md` |
| `danieljustus/symaira-brain` | `handoff/20260930-cloud` | `6c108530e229e7cface7e5f4fb44b44cecd19e64` | #756 | `docs/handoffs/end-work-cloud.md` |
| `danieljustus/homebrew-tap` | `handoff/20260930-cloud` | `ebab20e4bc603f0340686c8fbbba19dc70e0ad63` | #38 | `docs/handoffs/end-work-cloud.md` |
| `danieljustus/symaira-cockpit` | `handoff/20260930-cloud` | `7169441f800b5f5f26d2f531516e309770469d80` | #299 | `docs/handoffs/end-work-cloud.md` |
| `danieljustus/symaira-eraseme` | `handoff/20260930-cloud` | `61c08d8c1a5aa070debe19fe694f60f3570554c0` | #1115 | `docs/handoffs/end-work-cloud.md` |
| `danieljustus/symaira.com` | `handoff/20260930-cloud` | `bd96e6d7e4bf99c56000f0648a71248e4b8d94ad` | #78 | `docs/handoffs/end-work-cloud.md` |
| `danieljustus/symaira-vault` | `handoff/20260930-cloud` | `f165397f4b81d30f15b3325ddbe6a407d8f1d817` | #1235 | `docs/handoffs/end-work-cloud.md` |
| `danieljustus/symaira-corekit` | `handoff/20260930-signed-acceptance` | `c7ff0869bdd808052be01e30c3c8d9c5b9246e72` | #359 | `docs/handoffs/end-work-cloud.md` |
| `danieljustus/symaira-corekit` | `handoff/20260930-provider-repair` | `f33920eb9a0938dd7cc0bfad326834f4d56a04f1` | #360 | `docs/handoffs/end-work-cloud.md` |

## Immediate next work

1. CoreKit: compare the cache-only and provider/cache alternatives, establish parity and native Windows evidence before selecting a fix. The two broader snapshots remain separately recorded; do not mix branches automatically.
2. Desktop and credential service: keep Oracle ancestry/reachability holds until an accepted preservation design survives the integration policy. No tag or policy bypass is authorized.
3. Brain and website: review existing candidate PRs separately, not as automatically merged changes.
4. Cockpit: native VoiceOver/keyboard and migration acceptance require actual macOS/hardware evidence. Unit tests are not that evidence.
5. EraseMe and distribution: reconcile issue/acceptance and immutable-release requirements individually. Do not perform real broker requests, device actions, deployments or package releases.

## Reproduction and continuation

Clone the selected repository directly from GitHub, checkout its listed branch, compare `git rev-parse HEAD` against `git ls-remote --exit-code origin refs/heads/<branch>`, then read its document and execute the documented scoped commands. Use a fresh build-output directory for each code variant. Manifests and lockfiles resolve public dependencies; private audit reports, chat history, source-worktree files, real stores and credentials are not required for these checks. Native GUI and signing prerequisites remain explicit in each document.

PR/check snapshots at publication were pending or queued on the code branches; Scoop had no exact-HEAD Actions run. Re-read required checks at the exact final HEAD. GitHub availability is not CI success, acceptance, release readiness or proof of the target-cloud permissions/secrets/network environment. No cloud-agent job or paid model is launched.
