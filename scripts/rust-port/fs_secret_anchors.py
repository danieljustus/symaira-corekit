"""Reviewed SHA-256 anchors for native FS/SEC frozen-v1 captures.

Re-registered on 2026-11-26 for darwin-arm64 and linux-amd64 after the Rust
toolchain moved from 1.98.0 to 1.100.0 and the optional symaira-core-mcp `toon`
feature changed the lockfile dependency closure (#495, #497, #506). Both are
bound inputs. The Go observations, raw observations, case inventory and oracle
of every new capture are byte-identical to the 2026-11-11 registration; only the
toolchain and lockfile-closure records, commit heads, Go toolchain cache paths,
Go module identities and per-run identities differ. windows-amd64 is retained
unchanged as historical evidence: Windows left the supported platform scope
(#459) and no gate replays it. Capture never edits this map; replay has no
historical fallback.
See docs/rust-port/evidence/frozen-reregistration-20261126.json (previous: docs/rust-port/evidence/frozen-reregistration-20261111.json).
"""

TRUSTED_CAPTURE_SHA256: dict[str, str] = {
    'darwin-arm64': '8708417c66e1b4e2a3c2245346e6c7e1f6b8f1598ead104b4b2ba299fe94fcdd',
    'linux-amd64': '1a315da2080dba23a70998102ca553b50f49f5143327b6d9cc5d596f99e9e554',
    'windows-amd64': '9cd98c130b84fba3eec1e5817fa9c9ba3b51b735145dbe324932decf9a1e4565'
}
