"""Reviewed native SQLite reports; capture never changes this map.

Re-registered on 2026-11-10 for darwin-arm64 and linux-amd64 from pull-request
CI run 42866448038 (candidate revision 44c1c51d9ff04bbdae484aec0b41d077bf794ddb)
after the rustix requirement moved from =1.1.4 to 1.1.6 (#463), which changes
the symaira-core-sqlite lock closure through symaira-core-fs, and after the
SQLite capture harness changed (generate.py EPERM handling, test_generate.py,
test_acceptance.py; #461). Typed verdicts, checked fields and accepted
differences are unchanged; Go observations differ only in capture timestamps and
the three harness file hashes. windows-amd64 is retained unchanged as historical
evidence: Windows left the supported platform scope (#459) and no gate replays
it.
See docs/rust-port/evidence/frozen-reregistration-20261110.json (previous: docs/rust-port/evidence/frozen-reregistration-20261109.json).
"""

CAPTURES = {'darwin-arm64': {'artifact_id': 13791154739,
                  'manifest': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-candidate-source.json',
                  'manifest_sha256': 'f4ecb0fcb4ed790b71d7b94140c82f7bace7df9d76b3044e5a6e9fea10d5fb3c',
                  'report': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-report.json',
                  'report_sha256': '3916c5c9ecd0dce050f154acf8be1bab94e74cfb7b8221cd240807d1b6542290',
                  'source_commit': '44c1c51d9ff04bbdae484aec0b41d077bf794ddb',
                  'workflow_run': 42866448038},
 'linux-amd64': {'artifact_id': 13788415410,
                 'manifest': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-candidate-source.json',
                 'manifest_sha256': 'f4ecb0fcb4ed790b71d7b94140c82f7bace7df9d76b3044e5a6e9fea10d5fb3c',
                 'report': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-report.json',
                 'report_sha256': '6897838515b6c28c487289321c6d1552accd0143bec7ac7845bf99ee1741bdf8',
                 'source_commit': '44c1c51d9ff04bbdae484aec0b41d077bf794ddb',
                 'workflow_run': 42866448038},
 'windows-amd64': {'artifact_id': 12328925122,
                   'manifest': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-candidate-source.json',
                   'manifest_sha256': '9d5f9e4fc3e96b96efa811dd91edff161528c9efed59f5a88592d2eb9a799896',
                   'report': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-report.json',
                   'report_sha256': '23d0e2145549e67e74731aef64f747ec431b1e7fc1a7386691b2a25e5698e61f',
                   'source_commit': '71e3c280e51c76afb45ba46d972cd0dc8bb3d44e',
                   'workflow_run': 39560151712}}
