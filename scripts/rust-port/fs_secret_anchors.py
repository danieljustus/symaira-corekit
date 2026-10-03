"""Reviewed SHA-256 anchors for native FS/SEC frozen-v1 captures.

Registered from unchanged original Go 1.26.6 bytes after independent
provenance review and a separate source/raw/SDK reconstruction. Capture
never edits this map; replay has no historical fallback.
See docs/rust-port/evidence/fs-frozen-registration-20261003.json.
"""

TRUSTED_CAPTURE_SHA256: dict[str, str] = {
    'darwin-arm64': '802fb2e1f85d07be948ef81361953196e117ad74ef4e66749acf4cdc70deda5a',
    'linux-amd64': '6bb7b00fe62a957c9710ebb0dd0642c4e94000597f4fc7ad6714188ff948930a',
    'windows-amd64': 'b6219a2cd8c83d6fddbd4b3c0956e8c7ee306012c4092f7e1e8a859f50a55cb7'
}
