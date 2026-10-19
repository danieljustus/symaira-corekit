"""Reviewed SHA-256 anchors for native FS/SEC frozen-v1 captures.

Re-registered on 2026-10-20 after a lockfile and symaira-core-fs change
invalidated the candidate binding of the original 2026-10-03 registration.
The Go observations of every new capture are byte-identical to the original
registered captures; only candidate source hashes and per-run identities
differ. Capture never edits this map; replay has no historical fallback.
See docs/rust-port/evidence/frozen-reregistration-20261020.json (previous: docs/rust-port/evidence/fs-frozen-registration-20261003.json).
"""

TRUSTED_CAPTURE_SHA256: dict[str, str] = {
    'darwin-arm64': '522de6658d35b27779acbf87a11bb642cdcdeb726acc5d740ddea1a9679966ed',
    'linux-amd64': 'ad23a0d0b0248913ba87d02a3eedc56efdd729d85f2b34d6688f7f4a07ee74d3',
    'windows-amd64': '753a27641554dfac67ebfdf19e46dc7405476b6e0c84451564533d8315f6b3af'
}
