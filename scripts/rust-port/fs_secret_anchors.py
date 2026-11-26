"""Reviewed SHA-256 anchors for native FS/SEC frozen-v1 captures.

Re-registered on 2026-11-26 for darwin-arm64 and linux-amd64 after the
Windows-only code left symaira-core-fs, -secretref, -config and the FS/SEC
foundation harness, and the Windows-only cap-std/cap-primitives/same-file
dependencies left the lockfile dependency closure (#458). Both are bound
inputs. The Go observations, raw observations, case inventory and oracle of
every new capture are byte-identical to the earlier 2026-11-26 registration;
only the candidate source and lockfile-closure records, commit heads, Go
toolchain cache paths, Go module identities and per-run identities differ.
windows-amd64 is retained unchanged as historical evidence: Windows left the
supported platform scope (#459) and no gate replays it. Capture never edits
this map; replay has no historical fallback.
See docs/rust-port/evidence/frozen-reregistration-20261126-windows.json (previous: docs/rust-port/evidence/frozen-reregistration-20261126.json).
"""

TRUSTED_CAPTURE_SHA256: dict[str, str] = {
    'darwin-arm64': 'cf91336c7da45aad52e7a4622affec39e4ab86ec686848a33134f427f97f76a0',
    'linux-amd64': '13cfe96608c014f9d17faceadebd85a453435d6f78dd8bc51655e64101056c3b',
    'windows-amd64': '9cd98c130b84fba3eec1e5817fa9c9ba3b51b735145dbe324932decf9a1e4565'
}
