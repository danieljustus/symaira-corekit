"""Reviewed native SQLite reports; capture never changes this map.

Re-registered on 2026-11-11 for darwin-arm64 and linux-amd64 from pull-request
CI run 43104032164 (source commit 5c625553cc6dc895c9cf28d87cae65988f68c247,
candidate revision e40b132905a840abf5a213eae231b193218fe4e5) after the workspace
serde_json requirement moved from =1.0.151 to the caret range 1.0.151 (#475),
which changes the bound workspace Cargo.toml, and after test_acceptance.py
pointed at the new acceptance capture. The lockfile dependency closure is
unchanged. Typed verdicts, checked fields and accepted differences are
unchanged; Go observations differ only in capture timestamps and the
test_acceptance.py harness hash. windows-amd64 is retained unchanged as
historical evidence: Windows left the supported platform scope (#459) and no
gate replays it.
See docs/rust-port/evidence/frozen-reregistration-20261111.json (previous: docs/rust-port/evidence/frozen-reregistration-20261110.json).
"""

CAPTURES = {'darwin-arm64': {'artifact_id': 13892494283,
                  'manifest': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-candidate-source.json',
                  'manifest_sha256': 'a8ea5f16a107cc5926958e6b1452b5d63b145e9580ea68a6f35e7320bf2991bb',
                  'report': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-report.json',
                  'report_sha256': 'e2876d5a4a262db92aa97655cc0ec678d8381f9fb40180673083f36c5c2cee0c',
                  'source_commit': '5c625553cc6dc895c9cf28d87cae65988f68c247',
                  'workflow_run': 43104032164},
 'linux-amd64': {'artifact_id': 13892009096,
                 'manifest': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-candidate-source.json',
                 'manifest_sha256': 'a8ea5f16a107cc5926958e6b1452b5d63b145e9580ea68a6f35e7320bf2991bb',
                 'report': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-report.json',
                 'report_sha256': '75dd2f20721399c8219b16b6b33e8a0a74a1fcbb22d7d90c2ce6674b547a3057',
                 'source_commit': '5c625553cc6dc895c9cf28d87cae65988f68c247',
                 'workflow_run': 43104032164},
 'windows-amd64': {'artifact_id': 12328925122,
                   'manifest': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-candidate-source.json',
                   'manifest_sha256': '9d5f9e4fc3e96b96efa811dd91edff161528c9efed59f5a88592d2eb9a799896',
                   'report': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-report.json',
                   'report_sha256': '23d0e2145549e67e74731aef64f747ec431b1e7fc1a7386691b2a25e5698e61f',
                   'source_commit': '71e3c280e51c76afb45ba46d972cd0dc8bb3d44e',
                   'workflow_run': 39560151712}}
