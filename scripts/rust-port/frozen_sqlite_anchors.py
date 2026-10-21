"""Reviewed native SQLite reports; capture never changes this map.

Re-registered on 2026-10-21 from pull-request CI run 39560151712 (candidate
revision 408cd01b8d8e4bbf4a088da3e6b396e52aa68af2, an ancestor of main) after
ADR RUST-004 changed the lockfile binding to the dependency closure. Typed
verdicts, checked fields and accepted differences are unchanged; Go observations
differ only in capture timestamps and two harness file hashes.
See docs/rust-port/evidence/frozen-reregistration-20261021.json (previous: docs/rust-port/evidence/frozen-reregistration-20261020.json).
"""

CAPTURES = {'darwin-arm64': {'artifact_id': 12343598020,
                  'manifest': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-candidate-source.json',
                  'manifest_sha256': '62c1fa5425500fc587300019d82f95895d6ed09d2e2dfff15999a4e85a485b78',
                  'report': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-report.json',
                  'report_sha256': 'f3e2932ada9214f02bc361b71a68bafa624ddd3fec8d991e3e5572b01e918e1e',
                  'source_commit': '71e3c280e51c76afb45ba46d972cd0dc8bb3d44e',
                  'workflow_run': 39560151712},
 'linux-amd64': {'artifact_id': 12329255761,
                 'manifest': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-candidate-source.json',
                 'manifest_sha256': '62c1fa5425500fc587300019d82f95895d6ed09d2e2dfff15999a4e85a485b78',
                 'report': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-report.json',
                 'report_sha256': 'b70fa10a2d4e14712faec3b5d07f2ce90eaf90bbac2fdf83d416c34c8ed933a8',
                 'source_commit': '71e3c280e51c76afb45ba46d972cd0dc8bb3d44e',
                 'workflow_run': 39560151712},
 'windows-amd64': {'artifact_id': 12328925122,
                   'manifest': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-candidate-source.json',
                   'manifest_sha256': '9d5f9e4fc3e96b96efa811dd91edff161528c9efed59f5a88592d2eb9a799896',
                   'report': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-report.json',
                   'report_sha256': '23d0e2145549e67e74731aef64f747ec431b1e7fc1a7386691b2a25e5698e61f',
                   'source_commit': '71e3c280e51c76afb45ba46d972cd0dc8bb3d44e',
                   'workflow_run': 39560151712}}
