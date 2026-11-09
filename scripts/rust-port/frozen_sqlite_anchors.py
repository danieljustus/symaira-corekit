"""Reviewed native SQLite reports; capture never changes this map.

Re-registered on 2026-11-09 for darwin-arm64 and linux-amd64 from pull-request
CI run 42704539632 (candidate revision 726fc2a17b531249173c1cd21b8a9bfa72057e79,
main) after rusqlite 0.40.2 -> 0.41.1 (RUSTSEC-2026-0459) changed the
symaira-core-sqlite lock closure. Typed verdicts, checked fields and accepted
differences are unchanged; Go observations differ only in capture timestamps and
the test_acceptance.py harness hash. windows-amd64 is retained unchanged as
historical evidence: Windows left the supported platform scope (#459) and no
gate replays it.
See docs/rust-port/evidence/frozen-reregistration-20261109.json (previous: docs/rust-port/evidence/frozen-reregistration-20261021.json).
"""

CAPTURES = {'darwin-arm64': {'artifact_id': 13712833517,
                  'manifest': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-candidate-source.json',
                  'manifest_sha256': 'ec74dbf7614feaaa849b7068c9e0b7b464ff8c379817749c95696cf665f4846f',
                  'report': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-report.json',
                  'report_sha256': '8cf304f5fdff6c54952696172d574a4f95758208f73ff693a25a1cf6bc247d6b',
                  'source_commit': 'c32b62e914da8d85cbf0274fa9aefa6aebce7aa1',
                  'workflow_run': 42704539632},
 'linux-amd64': {'artifact_id': 13713795889,
                 'manifest': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-candidate-source.json',
                 'manifest_sha256': 'ec74dbf7614feaaa849b7068c9e0b7b464ff8c379817749c95696cf665f4846f',
                 'report': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-report.json',
                 'report_sha256': '22f71628c527e794fe2d3d208ac01b4171a756e75835f9542c805d211f969fd2',
                 'source_commit': 'c32b62e914da8d85cbf0274fa9aefa6aebce7aa1',
                 'workflow_run': 42704539632},
 'windows-amd64': {'artifact_id': 12328925122,
                   'manifest': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-candidate-source.json',
                   'manifest_sha256': '9d5f9e4fc3e96b96efa811dd91edff161528c9efed59f5a88592d2eb9a799896',
                   'report': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-report.json',
                   'report_sha256': '23d0e2145549e67e74731aef64f747ec431b1e7fc1a7386691b2a25e5698e61f',
                   'source_commit': '71e3c280e51c76afb45ba46d972cd0dc8bb3d44e',
                   'workflow_run': 39560151712}}
