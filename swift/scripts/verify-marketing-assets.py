#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.4", "pillow==12.1.0", "fonttools==4.64.0"]
# ///
"""Verify the generated marketing assets against Brand/Marketing/manifest.json.

Checks: design/font/source input hashes, every output's hash/size/mode, card sizes per format,
transparency of lockups/wordmarks/product logos, canvas colour fidelity of cards, DMG geometry
and label contrast, absence of absolute or sibling-checkout paths, the generator's numeric
topography self-check, and (with --determinism) that re-rendering AppKit reproduces the committed
bytes. Run with `uv run scripts/verify-marketing-assets.py` so the pinned NumPy is used.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import xml.dom.minidom
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MARKETING = ROOT / "Brand" / "Marketing"
failures: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"FAIL {msg}")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def luminance(rgb) -> float:
    def c(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (c(float(v)) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def hex_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--determinism", action="store_true", help="re-render AppKit + DMG and compare bytes")
    args = ap.parse_args()
    manifest = json.loads((MARKETING / "manifest.json").read_text())
    spec = json.loads((MARKETING / "identities.json").read_text())

    # 1. inputs
    for rel, digest in manifest["inputs"].items():
        p = ROOT / rel
        if not p.is_file():
            fail(f"missing input {rel}")
        elif sha(p) != digest:
            fail(f"input changed since last render: {rel}")
    provenance = json.loads((MARKETING / "source" / "identities-provenance.json").read_text())
    for ident, entry in provenance.items():
        for name, info in entry["files"].items():
            p = MARKETING / "source" / "identities" / ident / name
            if not p.is_file() or sha(p) != info["sha256"]:
                fail(f"vendored icon {ident}/{name} does not match provenance")
                continue
            im = Image.open(p)
            if im.size != (512, 512) or im.mode != "RGBA":
                fail(f"vendored icon {ident}/{name}: expected 512x512 RGBA, got {im.size} {im.mode}")
    for ident in spec["identities"]:
        if ident["source"] not in ("umbrella",) and not (MARKETING / "source" / "identities" / ident["source"]).is_dir():
            fail(f"identity {ident['id']}: source {ident['source']} not vendored")

    # 2. outputs
    canvas = {"dark": hex_rgb(manifest["colors"]["dark"]["canvas"]), "light": hex_rgb(manifest["colors"]["light"]["canvas"])}
    outputs = manifest["outputs"]
    seen = set()
    for out in outputs:
        p = ROOT / out["path"]
        seen.add(out["path"])
        if not p.is_file():
            fail(f"missing output {out['path']}")
            continue
        if sha(p) != out["sha256"]:
            fail(f"hash mismatch {out['path']}")
        if out["mode"] == "svg":
            try:
                dom = xml.dom.minidom.parse(str(p))
                svg = dom.documentElement
                if (svg.getAttribute("width"), svg.getAttribute("height")) != ("660", "420"):
                    fail("DMG svg is not 660x420")
            except Exception as exc:  # noqa: BLE001
                fail(f"DMG svg does not parse: {exc}")
            continue
        im = Image.open(p)
        if list(im.size) != out["size"] or im.mode != out["mode"]:
            fail(f"{out['path']}: {im.size} {im.mode} != manifest {out['size']} {out['mode']}")
        name = p.name
        if out.get("format"):
            want = tuple(spec["formats"][out["format"]]["size"])
            if im.size != want or im.mode != "RGB":
                fail(f"{out['path']}: card must be {want} RGB")
            arr = np.array(im.convert("RGB")).astype(float)
            mean = arr.reshape(-1, 3).mean(axis=0)
            if np.abs(mean - np.array(canvas[out["theme"]])).max() > 30:
                fail(f"{out['path']}: mean colour {mean.round()} too far from canvas")
        elif name.startswith(("lockup", "wordmark", "product-logo")):
            if im.mode != "RGBA":
                fail(f"{out['path']}: must be RGBA")
                continue
            a = np.array(im.getchannel("A"))
            if a[0, 0] != 0 or a[-1, -1] != 0 or a[0, -1] != 0 or a[-1, 0] != 0 or a.max() < 250:
                fail(f"{out['path']}: corners must be transparent and artwork opaque")
            if name.startswith("product-logo") and im.size != (1024, 1024):
                fail(f"{out['path']}: product logo must be 1024x1024")
        # nothing may be rendered at a hidden size/ratio different from its role
    # every file under exports must be in the manifest
    for p in sorted((MARKETING / "exports").rglob("*.png")):
        if str(p.relative_to(ROOT)) not in seen:
            fail(f"unmanifested export {p.relative_to(ROOT)}")

    # 3. DMG
    dmg = manifest["dmg"]
    p1, p2 = ROOT / "Brand/DMG/symaira-dmg-background.png", ROOT / "Brand/DMG/symaira-dmg-background@2x.png"
    im1, im2 = Image.open(p1), Image.open(p2)
    if im1.size != (660, 420) or im2.size != (1320, 840):
        fail(f"DMG sizes {im1.size} {im2.size}")
    gray = hex_rgb(dmg["gray"])
    for label, rgb in (("black", (0, 0, 0)), ("white", (255, 255, 255))):
        if contrast(gray, rgb) < 4.4:
            fail(f"DMG gray vs {label} Finder label contrast {contrast(gray, rgb):.2f} < 4.4")
    arr = np.array(im1.convert("RGB")).astype(float)
    for cx, cy in dmg["icon_centers"]:
        slot = arr[cy - 84 : cy + 84, cx - 84 : cx + 84]
        if slot.std(axis=(0, 1)).max() > 4 or np.abs(slot.mean(axis=(0, 1)) - np.array(gray)).max() > 6:
            fail(f"DMG icon slot ({cx},{cy}) is not plain terrain (baked icon or text?)")
    a = dmg["arrow"]
    band = arr[a["y"] - 3 : a["y"] + 4, a["x0"] : a["x1"]]
    champagne = np.array(hex_rgb(manifest["colors"]["primary"]), dtype=float)
    if np.abs(band - champagne).sum(axis=2).min() > 90:
        fail("DMG arrow not found at expected position")

    # 4. path safety
    banned = re.compile(r"/Users/|/Volumes/|/private/|\.\./symaira-|/workspace/")
    for rel in ("scripts/generate-marketing-assets.py", "scripts/verify-marketing-assets.py", "Brand/Marketing/manifest.json", "Brand/Marketing/identities.json", "Brand/Marketing/source/identities-provenance.json"):
        for n, line in enumerate((ROOT / rel).read_text().splitlines(), 1):
            if banned.search(line) and "banned = re.compile" not in line:
                fail(f"{rel}:{n} absolute/sibling path: {line.strip()[:80]}")

    # 5. numeric self-check: the committed bytes are only trustworthy if this NumPy computes the
    # height field correctly (see topo_selfcheck in the generator).
    sys.dont_write_bytecode = True  # no scripts/__pycache__ in the working tree
    gen_spec = importlib.util.spec_from_file_location("marketing_generator", ROOT / "scripts/generate-marketing-assets.py")
    gen = importlib.util.module_from_spec(gen_spec)
    gen_spec.loader.exec_module(gen)
    try:
        gen.topo_selfcheck(gen.load_params())
    except SystemExit as exc:
        fail(str(exc))

    # 6. determinism
    if args.determinism:
        with tempfile.TemporaryDirectory(prefix="marketing-det-") as tmp:
            subprocess.run([sys.executable, str(ROOT / "scripts/generate-marketing-assets.py"), "--only", "appkit", "--out", tmp, "--dmg"], check=True, stdout=subprocess.DEVNULL)
            for out in outputs:
                if out["identity"] == "appkit":
                    fresh = Path(tmp) / "appkit" / Path(out["path"]).name
                elif out["identity"] == "dmg":
                    fresh = Path(tmp) / "_dmg" / Path(out["path"]).name
                else:
                    continue
                if not fresh.is_file() or sha(fresh) != out["sha256"]:
                    fail(f"not reproducible: {out['path']}")

    print(f"{len(outputs)} outputs checked, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
