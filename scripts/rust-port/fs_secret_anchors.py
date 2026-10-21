"""Reviewed SHA-256 anchors for native FS/SEC frozen-v1 captures.

Re-registered on 2026-10-21 after ADR RUST-004 replaced the raw Cargo.lock
binding with the lockfile dependency closure. The Go observations of every new
capture are byte-identical to the 2026-10-20 registration; only the lockfile
record, harness hashes and per-run identities differ. Capture never edits this
map; replay has no historical fallback.
See docs/rust-port/evidence/frozen-reregistration-20261021.json (previous: docs/rust-port/evidence/frozen-reregistration-20261020.json).
"""

TRUSTED_CAPTURE_SHA256: dict[str, str] = {
    'darwin-arm64': '144b3b1ae84042117e6c8dcb675baf1ca2dfd4d30d8b1fdf7825cd84ad77b1f3',
    'linux-amd64': '4a780c61a7bbe1e80af7555b359bd8a4156c8072ef1447dd78e84642be69d8ed',
    'windows-amd64': '9cd98c130b84fba3eec1e5817fa9c9ba3b51b735145dbe324932decf9a1e4565'
}
