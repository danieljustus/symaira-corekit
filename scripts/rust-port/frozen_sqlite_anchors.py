"""Reviewed native SQLite reports; capture never changes this map.

Re-registered on 2026-11-26 for darwin-arm64 and linux-amd64 from pull-request
CI run 45790832085 (source commit ad7008662b69c33527d8bc65057a606f4c114700,
candidate revision e76ff4b4156a279c62b91a827ef4fcf33a5d9f37) after the Windows-only code left
symaira-core-fs and its Windows-only dependencies left the lockfile dependency
closure (#458), and after test_acceptance.py pointed at the new acceptance
capture. Typed verdicts, checked fields and accepted differences are
unchanged; Go observations differ only in capture timestamps and the
test_acceptance.py harness hash. windows-amd64 is retained unchanged as
historical evidence: Windows left the supported platform scope (#459) and no
gate replays it.
See docs/rust-port/evidence/frozen-reregistration-20261126-windows.json (previous: docs/rust-port/evidence/frozen-reregistration-20261126.json).
"""

CAPTURES = {'darwin-arm64': {'artifact_id': 15103052433,
                  'manifest': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-candidate-source.json',
                  'manifest_sha256': '24d8eef71aaf390469267a2df7a6f59cb3b6261157528ce03bcf7a340fa75b82',
                  'report': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-report.json',
                  'report_sha256': 'e64864507c4b4ffa04ac005e1d177190c071fca2fc783403352574a55b9fbbe2',
                  'source_commit': 'ad7008662b69c33527d8bc65057a606f4c114700',
                  'workflow_run': 45790832085},
 'linux-amd64': {'artifact_id': 15102338410,
                 'manifest': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-candidate-source.json',
                 'manifest_sha256': '24d8eef71aaf390469267a2df7a6f59cb3b6261157528ce03bcf7a340fa75b82',
                 'report': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-report.json',
                 'report_sha256': '0ac0121569982953974e034c6bbf1c04bfd6e21ebc188320df32b9e7048524c0',
                 'source_commit': 'ad7008662b69c33527d8bc65057a606f4c114700',
                 'workflow_run': 45790832085},
 'windows-amd64': {'artifact_id': 12328925122,
                   'manifest': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-candidate-source.json',
                   'manifest_sha256': '9d5f9e4fc3e96b96efa811dd91edff161528c9efed59f5a88592d2eb9a799896',
                   'report': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-report.json',
                   'report_sha256': '23d0e2145549e67e74731aef64f747ec431b1e7fc1a7386691b2a25e5698e61f',
                   'source_commit': '71e3c280e51c76afb45ba46d972cd0dc8bb3d44e',
                   'workflow_run': 39560151712}}
