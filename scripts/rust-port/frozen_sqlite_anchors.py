"""Reviewed native SQLite reports; capture never changes this map.

Re-registered on 2026-10-20 from native CI on candidate e445d30695bebfc4b88b5457af2da70ca910a639
after the rustls lockfile update and an acceptance-harness pointer change
invalidated the original registration (CI run 37110559130). Typed verdicts,
checked fields and accepted differences are unchanged; Go observations differ
only in capture timestamps and the harness file hash. See docs/rust-port/evidence/frozen-reregistration-20261020.json.
"""

CAPTURES = {'darwin-arm64': {'artifact_id': 12228721216,
                  'manifest': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-candidate-source.json',
                  'manifest_sha256': '54e58d7a931ea6f477d3b52edfbcb0d0561b83abaeab09d1e3be8e41903e2c4e',
                  'report': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-report.json',
                  'report_sha256': '2fac0b753b2694a3e33ae070f58ae145f2e959edef5df7c4d747a97c4383e7c8',
                  'source_commit': 'e445d30695bebfc4b88b5457af2da70ca910a639',
                  'workflow_run': 39308889944},
 'linux-amd64': {'artifact_id': 12214703294,
                 'manifest': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-candidate-source.json',
                 'manifest_sha256': '54e58d7a931ea6f477d3b52edfbcb0d0561b83abaeab09d1e3be8e41903e2c4e',
                 'report': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-report.json',
                 'report_sha256': '4c1fec0016cc524ba4452ba6645aef53fdac5d0936bef036b9a947b6d73a0374',
                 'source_commit': 'e445d30695bebfc4b88b5457af2da70ca910a639',
                 'workflow_run': 39308896259},
 'windows-amd64': {'artifact_id': 12214534136,
                   'manifest': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-candidate-source.json',
                   'manifest_sha256': '7dfc924b696c8925b509a0cc4fc8f99f3de2c1c14c0a37eaf684241f047f7620',
                   'report': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-report.json',
                   'report_sha256': 'a92a2be1aa8e51d2172492d5708efcc8b64fb48f6fa42db61a6dec53194bb8c4',
                   'source_commit': 'e445d30695bebfc4b88b5457af2da70ca910a639',
                   'workflow_run': 39308896259}}
