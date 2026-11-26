"""Reviewed native SQLite reports; capture never changes this map.

Re-registered on 2026-11-26 for darwin-arm64 and linux-amd64 from pull-request
CI run 45772582817 (source commit e7876801f6e4381ce28a5e8f00418f3b9e52093f,
candidate revision 12535e934c1b886f9f491ad9c655fd064ef5f05c) after the Rust toolchain moved
from 1.98.0 to 1.100.0 and the optional symaira-core-mcp `toon` feature changed
the lockfile dependency closure (#495, #497, #506), and after test_acceptance.py
pointed at the new acceptance capture. Typed verdicts, checked fields and
accepted differences are unchanged; Go observations differ only in capture
timestamps and the test_acceptance.py harness hash. windows-amd64 is retained
unchanged as historical evidence: Windows left the supported platform scope
(#459) and no gate replays it.
See docs/rust-port/evidence/frozen-reregistration-20261126.json (previous: docs/rust-port/evidence/frozen-reregistration-20261111.json).
"""

CAPTURES = {'darwin-arm64': {'artifact_id': 15095061341,
                  'manifest': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-candidate-source.json',
                  'manifest_sha256': 'c5319464f77fd206e86b944cd22ed07c96f0a5d87dc715649107531840cdb04a',
                  'report': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-report.json',
                  'report_sha256': '3c4c50be9f6d1d2f14adc9c351da9e4301172a995a39ec494ddb90e66feffb0a',
                  'source_commit': 'e7876801f6e4381ce28a5e8f00418f3b9e52093f',
                  'workflow_run': 45772582817},
 'linux-amd64': {'artifact_id': 15094766928,
                 'manifest': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-candidate-source.json',
                 'manifest_sha256': 'c5319464f77fd206e86b944cd22ed07c96f0a5d87dc715649107531840cdb04a',
                 'report': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-report.json',
                 'report_sha256': 'c8e266dbc82dde10eb69999a25ab626a58ab1c580118782a2d501783cc61f385',
                 'source_commit': 'e7876801f6e4381ce28a5e8f00418f3b9e52093f',
                 'workflow_run': 45772582817},
 'windows-amd64': {'artifact_id': 12328925122,
                   'manifest': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-candidate-source.json',
                   'manifest_sha256': '9d5f9e4fc3e96b96efa811dd91edff161528c9efed59f5a88592d2eb9a799896',
                   'report': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-report.json',
                   'report_sha256': '23d0e2145549e67e74731aef64f747ec431b1e7fc1a7386691b2a25e5698e61f',
                   'source_commit': '71e3c280e51c76afb45ba46d972cd0dc8bb3d44e',
                   'workflow_run': 39560151712}}
