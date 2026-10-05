"""Reviewed original native SQLite reports; capture never changes this map.

Go/helper provenance, original Rust source manifests and typed verdicts were
independently reconstructed before registration from CI run 37110559130.
The immutable artifact identities and exact original byte hashes follow.
"""

CAPTURES = {'darwin-arm64': {'artifact_id': 11269148242,
                  'manifest': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-candidate-source.json',
                  'manifest_sha256': '2da3a16a194cd2d74a76881a314103f8053e658fc76c29041be27658e3378333',
                  'report': 'testdata/rust-port/sqlite/frozen-v1/darwin-arm64/sqlite-native-report.json',
                  'report_sha256': 'c3cb881fca5af6ac592d5f27420a1e4644ad2193cb84a92b6c8d3b74659cec9b',
                  'source_commit': 'c3f026dcf7f1c7164f3f709677cdf5b438cba1cc',
                  'workflow_run': 37110559130},
 'linux-amd64': {'artifact_id': 11269676997,
                 'manifest': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-candidate-source.json',
                 'manifest_sha256': '2da3a16a194cd2d74a76881a314103f8053e658fc76c29041be27658e3378333',
                 'report': 'testdata/rust-port/sqlite/frozen-v1/linux-amd64/sqlite-native-report.json',
                 'report_sha256': '365237b9e8100e7086dffae7fccc87d538b619b0ed0db948e94e6c80811616f4',
                 'source_commit': 'c3f026dcf7f1c7164f3f709677cdf5b438cba1cc',
                 'workflow_run': 37110559130},
 'windows-amd64': {'artifact_id': 11269736830,
                   'manifest': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-candidate-source.json',
                   'manifest_sha256': 'f4a1fc0e5136e93eacf6ec60cea604b31a7d64f0e246173fa71f6dd6f228f6c0',
                   'report': 'testdata/rust-port/sqlite/frozen-v1/windows-amd64/sqlite-native-report.json',
                   'report_sha256': 'c4b5bef4d510af3f2d74cdc1e5d784e1b09dc4e6d7d5afc5d43363415a32c174',
                   'source_commit': 'c3f026dcf7f1c7164f3f709677cdf5b438cba1cc',
                   'workflow_run': 37110559130}}
