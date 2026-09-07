#!/usr/bin/env python3
"""Verify the vendored approved Icon Composer family and its exports."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / "Brand" / "AppIcon" / "SymairaAppKit"
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
    if metadata.get("product") != "symaira-appkit":
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
            fail(f"checksum mismatch for {path.relative_to(ROOT)}: {actual} != {expected}")

    icon = json.loads((FAMILY / "AppIcon.icon" / "icon.json").read_text(encoding="utf-8"))
    groups = icon.get("groups")
    if not isinstance(groups, list) or len(groups) != 2:
        fail("the approved icon must retain its two Icon Composer layer groups")
    for group in groups:
        for layer in group.get("layers", []):
            image_name = layer.get("image-name")
            if image_name and not (FAMILY / "AppIcon.icon" / "Assets" / image_name).is_file():
                fail(f"Icon Composer layer is missing {image_name}")

    renders = metadata.get("renders", [])
    expected_renders = {
        "macOS-Default",
        "macOS-Dark",
        "macOS-TintedDark",
        "iOS-Default",
        "iOS-Dark",
        "iOS-TintedDark",
    }
    actual_renders = {item.get("platform") + "-" + item.get("mode") for item in renders}
    if actual_renders != expected_renders:
        fail(f"render matrix mismatch: {sorted(actual_renders)}")
    if not (FAMILY / "exports" / "AppIcon.icns").is_file():
        fail("missing macOS AppIcon.icns export")

    print(f"verified {len(files)} approved AppKit icon assets and {len(renders)} renders")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
