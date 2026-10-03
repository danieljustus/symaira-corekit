# ADR 0004: Retain immutable oracle source history independently of PR branches

Accepted 2026-10-03 under the maintainer's delegated implementation decisions.

CoreKit uses squash merges and automatically deletes merged PR branches. A
squash preserves the resulting files, but does not preserve the original source
commit identities recorded by native Go captures. Those identities must remain
retrievable for later SDK/source reconstruction and ancestry verification.

Preserve capture ancestry using annotated `evidence/` tags before merging its
last working branch. These are evidence references, not SemVer releases or
claims that a candidate passed acceptance. Do not move an existing evidence
tag. Keep original observations and provenance fields unchanged.

The initial references, verified through the remote after pushing, are:

| Reference | Preserved commit |
| --- | --- |
| `evidence/corekit-native-oracles-20261003` | `95e098f08c6cccca671ea5a07507a7932409e8c9` |
| `evidence/corekit-static-oracles-20261002` | `b028717ef247c1817bd9285634db7a29157e9661` |

Their ancestry retains the original FS source `5fc5299a56e96b6007fda7d8900363f3aa6ba282`,
SQLite capture source `c3f026dcf7f1c7164f3f709677cdf5b438cba1cc`, and static update
source `95cc1b5ef260a67bb989e4e5cc88a3384d9a15e4`. GitHub's release workflow only
matches `v*` tags, so these references do not publish product artifacts.

This small retention cost makes fixed Git identities usable after integration
and avoids retaining every temporary working branch indefinitely. Evidence tags
do not replace raw artifact digest checks, independent provenance reconstruction
or actual native Rust execution. Consumer dependency revisions likewise require
a durable remote reference before removing their final branch.
