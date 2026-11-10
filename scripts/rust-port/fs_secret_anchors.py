"""Reviewed SHA-256 anchors for native FS/SEC frozen-v1 captures.

Re-registered on 2026-11-10 for darwin-arm64 and linux-amd64 after the rustix
requirement moved from =1.1.4 to 1.1.6 in symaira-core-fs and
symaira-core-secretref (#463), which changes the lockfile dependency closure and
both crate manifests. The Go observations, raw observations and case inventory of
every new capture are byte-identical to the 2026-10-21 registration; only the
lockfile and manifest records, commit heads, Go toolchain cache paths and per-run
identities differ. windows-amd64 is retained unchanged as historical evidence:
Windows left the supported platform scope (#459) and no gate replays it. Capture
never edits this map; replay has no historical fallback.
See docs/rust-port/evidence/frozen-reregistration-20261110.json (previous: docs/rust-port/evidence/frozen-reregistration-20261021.json).
"""

TRUSTED_CAPTURE_SHA256: dict[str, str] = {
    'darwin-arm64': '000fe14cefed82271dd45b8b840a4d4061535b0e5d78a9da9f3d7073af705ae1',
    'linux-amd64': '32be440c2828440c8e13d29578eca0e752ea504bc45f5c5ff0034a0dc3515e6f',
    'windows-amd64': '9cd98c130b84fba3eec1e5817fa9c9ba3b51b735145dbe324932decf9a1e4565'
}
