"""Independently reviewed SHA-256 anchors for native FS/SEC frozen-v1 captures.

Keep empty until a parent has reviewed a real Go 1.26.6 capture and registers
its exact bytes. Capture never edits this file and replay has no historical
fallback.
"""

# Keys are native GOOS-GOARCH values, e.g. ``darwin-arm64``. These are not
# fixture self-hashes: only a separate review may add an accepted digest.
TRUSTED_CAPTURE_SHA256: dict[str, str] = {}
