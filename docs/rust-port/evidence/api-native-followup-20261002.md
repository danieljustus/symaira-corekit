# API/native follow-up evidence, 2026-10-02

## Source and scope

Diagnostic candidate: branch `agent/issue367-api-20261002-091556`, HEAD `184defac1c0ee68d3771672b1baf9570c26559e4` with the reviewed fixture, SQLite capture-pointer and test-lint changes still uncommitted. This is dirty, source-bound diagnostic evidence, not final clean-head CI acceptance. Native host: Darwin/arm64. Go SDK: 1.26.6. Rust toolchain: 1.98.0. Cosign: official v3.0.5 Darwin/arm64 binary, SHA-256 `4888c898e2901521a6bd4cf4f0383c9465588a6a46ecd2465ad34faf13f09eb7`, validated by the committed installer before execution.

## Actual execution

- `TestCancelledDownloadClosesBeforeRemovingStagingFile` executed and passed through the real Go `downloadToTemp`; target content remained unchanged and no staging file remained.
- `update-swap-differential.py --write` executed the real native Go eight-case swap oracle. Only its production-source digest changed; the eight observations and helper/runner identities stayed unchanged.
- `update-native-acceptance.py` completed successfully under disposable HOME/XDG/temp roots: fresh 17-case public Go Apply capture, all update Make contract gates (including the 16-row cancellation comparison and mutation rejection), real invalid-signature/certificate Cosign test, and the update package nextest run. All four recorded commands exited zero. The regenerated canonical Apply capture changed only its production-source digest.
- The real SQLite Go/Rust differential executed six native cases. Its independently recomputed typed verdict passed, including source inventory, actual compiler/binary identity, all declared/executed IDs, success fields and candidate ancestry. The capture uses main ancestor `14c839e4c963d3365c210f748e615da2fc3f22ef`; the complete frozen source inventory separately binds the actual diagnostic bytes, so committing or squash-merging the evidence does not invalidate its ancestry.
- The full Python SQLite controls executed successfully after promotion, including co-mutated report/manifest rejection and retained historical-capture rejection. Historical captures are retained unchanged.

## Corrected Go defect and compatibility

Issue #386 fixes failed-download cleanup ordering: on Windows removal must happen after the staging file handle closes. This is a nonbreaking bug fix; failed downloads must not publish a target or leave staging residue. Error families and successful same-filesystem staging are unchanged. Rust does not reproduce the faulty cleanup behavior. Native Windows Go package tests already passed at `184defa`; final-head Go/Rust cancellation and signed acceptance are still required.

## Local environment limits

The opt-in `dev-external` launcher currently rejects a missing unrelated AppKit `.build` mapping. No AppKit path or global mapping was changed. Explicit installed SDKs and worktree-isolated build outputs on the mounted NVMe were used instead.

The first local SQLite capture correctly rejected the NVMe root's group-writable `0775` ancestor. This is not bypassed: disposable runtime roots were moved to private Hermes scratch ancestors while build/evidence outputs remained external. The failed attempt and its logs are retained separately; no filesystem-security predicate was weakened.

## Remaining gate

Do not close #367, #385 or #386 from these diagnostics alone. Require the fresh committed PR head's required CI, native Linux/macOS/Windows contracts, regular merge readback, issue closure and claim cleanup. The earlier native Linux/Windows SQLite captures are authentic but precede the changed case-ID test pointer; they are not substituted for final-source acceptance.
