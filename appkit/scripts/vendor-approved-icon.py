#!/usr/bin/env python3
"""Vendor one approved Icon Composer product family into AppKit Brand assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--product", default="symaira-appkit")
    parser.add_argument("--destination", type=Path, default=Path("Brand/AppIcon/SymairaAppKit"))
    args = parser.parse_args()

    release_manifest_path = args.release_root / "manifest.json"
    manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
    product = next(item for item in manifest["products"] if item["id"] == args.product)
    source_dir = args.release_root / args.product
    args.destination.mkdir(parents=True, exist_ok=True)

    for relative in product["files"]:
        source = source_dir / relative
        destination = args.destination / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    local_manifest = {
        "product": product["id"],
        "name": product["name"],
        "source": "symaira-icons-release/manifest.json",
        "files": product["files"],
        "renders": product["renders"],
    }
    (args.destination / "icon-manifest.json").write_text(
        json.dumps(local_manifest, indent=2) + "\n", encoding="utf-8"
    )

    for relative, expected in product["files"].items():
        actual = sha256(args.destination / relative)
        if actual != expected:
            raise SystemExit(f"checksum mismatch after copy: {relative}")
    print(f"vendored {len(product['files'])} assets for {product['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
