#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow==12.1.0"]
# ///
"""Vendor approved icon renders as inputs for the marketing generator.

Reads the Icon Composer render directory produced by the brand refresh
(`<icons-root>/<key>/exports/macOS-{Default,Dark}.png` plus `<icons-root>/manifest.json`)
and copies 512 px renders into `Brand/Marketing/source/identities/<id>/`, together with
upstream provenance (source repo/head, source file hashes). The generator itself never reads
outside the repository, so this step is only needed when an icon changes.

    python3 scripts/vendor-marketing-icons.py --icons-root /path/to/icons
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MARKETING = ROOT / "Brand" / "Marketing"
SOURCE = MARKETING / "source" / "identities"
ICON_PX = 512
# icon key in the render directory -> identity id used by Brand/Marketing/identities.json
KEYS = {
    "appkit": "appkit",
    "brain": "brain",
    "cockpit": "cockpit",
    "corekit": "corekit",
    "desktop": "desktop",
    "eraseme": "eraseme",
    "fritz": "fritz",
    "homebrew-tap": "homebrew-tap",
    "symaira-com": "symaira-com",
    "vault": "vault",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--icons-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.icons_root.resolve()
    upstream = json.loads((root / "manifest.json").read_text())
    provenance: dict[str, dict] = {}
    for key, identity in sorted(KEYS.items()):
        entry = upstream[key]
        target = SOURCE / identity
        target.mkdir(parents=True, exist_ok=True)
        files = {}
        for mode in ("Default", "Dark"):
            src = root / key / "exports" / f"macOS-{mode}.png"
            image = Image.open(src).convert("RGBA")
            if image.size != (1024, 1024):
                raise SystemExit(f"{src}: expected 1024x1024, got {image.size}")
            out = target / f"macOS-{mode}-{ICON_PX}.png"
            image.resize((ICON_PX, ICON_PX), Image.Resampling.LANCZOS).save(out, optimize=True)
            files[out.name] = {
                "sha256": sha256(out),
                "upstream_render_sha256": sha256(src),
                "upstream_render": f"{key}/exports/macOS-{mode}.png",
            }
        provenance[identity] = {
            "source_repo": entry["source_repo"],
            "source_package": entry["source_package"],
            "source_head": entry["source_head"],
            "source_files": entry["source_files"],
            "design_sha256": entry["design_sha256"],
            "background_only": entry["background_only"],
            "files": files,
        }
    (MARKETING / "source" / "identities-provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n"
    )
    print(f"vendored {len(provenance)} identities into {SOURCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
