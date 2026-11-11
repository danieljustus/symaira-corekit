"""Reviewed SHA-256 anchors for native FS/SEC frozen-v1 captures.

Re-registered on 2026-11-11 for darwin-arm64 and linux-amd64 after the
workspace serde_json requirement moved from =1.0.151 to the caret range 1.0.151
(#475). The lockfile dependency closure is unchanged; the workspace Cargo.toml is
a bound input. The Go observations, raw observations and case inventory of every
new capture are byte-identical to the 2026-11-10 registration; only the workspace
manifest record, commit heads, Go toolchain cache paths and per-run identities
differ. windows-amd64 is retained unchanged as historical evidence: Windows left
the supported platform scope (#459) and no gate replays it. Capture never edits
this map; replay has no historical fallback.
See docs/rust-port/evidence/frozen-reregistration-20261111.json (previous: docs/rust-port/evidence/frozen-reregistration-20261110.json).
"""

TRUSTED_CAPTURE_SHA256: dict[str, str] = {
    'darwin-arm64': '523ace09f23c5dc95084f7649cdf2b87e434e7d90dd20458b3f9a83bcd97b5fe',
    'linux-amd64': 'afa4687c46eb2771b5697f805212ded2e093a5c702a6d6621d53317110167200',
    'windows-amd64': '9cd98c130b84fba3eec1e5817fa9c9ba3b51b735145dbe324932decf9a1e4565'
}
