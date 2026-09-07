#!/usr/bin/env python3
"""Verify CoreKit's vendored brand-only Icon Composer family."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / "assets" / "branding" / "SymairaCoreKit"
MANIFEST = FAMILY / "icon-manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    if not MANIFEST.is_file():
        fail(f"missing {MANIFEST.relative_to(ROOT)}")
    metadata = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if metadata.get("product") != "symaira-corekit":
        fail("icon manifest identifies the wrong product")

    files = metadata.get("files")
    if not isinstance(files, dict) or not files:
        fail("icon manifest has no file checksums")
    for relative, expected in files.items():
        path = FAMILY / relative
        if not path.is_file():
            fail(f"missing vendored asset: {path.relative_to(ROOT)}")
        actual = sha256(path)
        if actual != expected:
            fail(f"checksum mismatch for {path.relative_to(ROOT)}")

    icon = json.loads((FAMILY / "AppIcon.icon" / "icon.json").read_text(encoding="utf-8"))
    groups = icon.get("groups")
    if not isinstance(groups, list) or len(groups) != 2:
        fail("CoreKit's brand icon must retain both approved layer groups")
    if len(metadata.get("renders", [])) != 6:
        fail("CoreKit's brand export matrix must contain six approved renders")
    if not (FAMILY / "exports" / "AppIcon.icns").is_file():
        fail("missing CoreKit AppIcon.icns export")

    print(f"verified {len(files)} approved CoreKit brand assets and six renders")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
