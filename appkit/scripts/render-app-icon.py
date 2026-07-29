#!/usr/bin/env python3
"""Render the shared Symaira app-icon shell around a repository-owned glyph."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


MAC_IMAGES = (
    ("mac-16.png", "16x16", "1x", 16),
    ("mac-16@2x.png", "16x16", "2x", 32),
    ("mac-32.png", "32x32", "1x", 32),
    ("mac-32@2x.png", "32x32", "2x", 64),
    ("mac-128.png", "128x128", "1x", 128),
    ("mac-128@2x.png", "128x128", "2x", 256),
    ("mac-256.png", "256x256", "1x", 256),
    ("mac-256@2x.png", "256x256", "2x", 512),
    ("mac-512.png", "512x512", "1x", 512),
    ("mac-512@2x.png", "512x512", "2x", 1024),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glyph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--master", type=Path, required=True)
    parser.add_argument("--platforms", default="macos")
    parser.add_argument("--accent", default="#71D9F0")
    return parser.parse_args()


def inner_svg(path: Path) -> str:
    root = ET.parse(path).getroot()
    inherited_attributes = {
        "fill",
        "fill-opacity",
        "opacity",
        "stroke",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-opacity",
        "stroke-width",
    }

    def local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def flatten(element: ET.Element, inherited: dict[str, str]) -> list[ET.Element]:
        style = dict(inherited)
        style.update(
            {key: value for key, value in element.attrib.items() if key in inherited_attributes}
        )
        if local_name(element.tag) == "g":
            flattened: list[ET.Element] = []
            for child in element:
                flattened.extend(flatten(child, style))
            return flattened

        element.tag = local_name(element.tag)
        for key, value in style.items():
            element.attrib.setdefault(key, value)
        return [element]

    children: list[ET.Element] = []
    for child in root:
        children.extend(flatten(child, {}))
    return "\n".join(ET.tostring(child, encoding="unicode") for child in children)


def render_svg(template: Path, glyph: str, accent: str) -> str:
    rendered = (
        template.read_text(encoding="utf-8")
        .replace("__GLYPH__", glyph)
        .replace("__ACCENT__", accent)
    )
    # ImageMagick's SVG renderer does not reliably inherit CSS currentColor
    # through the injected group. Resolve it explicitly for deterministic PNGs.
    return rendered.replace("currentColor", accent)


def rasterize_svg(svg: Path, png: Path, size: int) -> None:
    subprocess.run(
        [
            "magick",
            "-background",
            "none",
            str(svg),
            "-resize",
            f"{size}x{size}",
            "-strip",
            str(png),
        ],
        check=True,
    )


def resize_png(source: Path, png: Path, size: int) -> None:
    subprocess.run(
        [
            "magick",
            str(source),
            "-resize",
            f"{size}x{size}",
            "-depth",
            "8",
            "-type",
            "TrueColorAlpha",
            "-define",
            "png:color-type=6",
            "-strip",
            str(png),
        ],
        check=True,
    )


def remove_alpha(png: Path) -> None:
    """App Store icons must not retain an alpha channel."""
    subprocess.run(
        [
            "magick",
            str(png),
            "-alpha",
            "off",
            "-depth",
            "8",
            "-type",
            "TrueColor",
            "-define",
            "png:color-type=2",
            "-strip",
            str(png),
        ],
        check=True,
    )


def rasterize_glyph(svg: Path, png: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="symaira-glyph-quicklook-") as directory:
        result = subprocess.run(
            ["qlmanage", "-t", "-s", "512", "-o", directory, str(svg)],
            check=True,
            capture_output=True,
            text=True,
        )
        thumbnail = Path(directory) / f"{svg.name}.png"
        if not thumbnail.exists():
            raise RuntimeError(f"Quick Look did not render {svg}: {result.stdout}")
        subprocess.run(
            [
                "magick",
                str(thumbnail),
                "-alpha",
                "on",
                "-fuzz",
                "5%",
                "-transparent",
                "white",
                "-strip",
                str(png),
            ],
            check=True,
        )


def compose_icon(shell_svg: Path, glyph_png: Path, png: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="symaira-icon-") as directory:
        temporary = Path(directory)
        shell_png = temporary / "shell.png"
        rasterize_svg(shell_svg, shell_png, 1024)
        subprocess.run(
            [
                "magick",
                str(shell_png),
                str(glyph_png),
                "-geometry",
                "+256+256",
                "-composite",
                "-depth",
                "8",
                "-type",
                "TrueColorAlpha",
                "-define",
                "png:color-type=6",
                "-strip",
                str(png),
            ],
            check=True,
        )


def main() -> int:
    args = parse_args()
    if shutil.which("magick") is None:
        print("error: ImageMagick 'magick' is required to render icon exports", file=sys.stderr)
        return 2
    if shutil.which("qlmanage") is None:
        print("error: macOS Quick Look 'qlmanage' is required to render glyphs", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parent.parent
    templates = root / "Brand" / "AppIcon"
    platforms = {item.strip() for item in args.platforms.split(",") if item.strip()}
    if not platforms <= {"macos", "ios"}:
        print("error: --platforms accepts macos, ios, or macos,ios", file=sys.stderr)
        return 2

    glyph = inner_svg(args.glyph)
    args.output.mkdir(parents=True, exist_ok=True)
    args.master.parent.mkdir(parents=True, exist_ok=True)
    for existing in args.output.glob("*.png"):
        existing.unlink()
    assets_catalog = args.output.parent
    assets_catalog.mkdir(parents=True, exist_ok=True)
    catalog_contents = assets_catalog / "Contents.json"
    if not catalog_contents.exists():
        catalog_contents.write_text(
            json.dumps({"info": {"author": "xcode", "version": 1}}, indent=2) + "\n",
            encoding="utf-8",
        )

    mac_template = templates / "icon-shell-macos.svg"
    ios_template = templates / "icon-shell-ios.svg"
    mac_svg = render_svg(mac_template, glyph, args.accent)
    args.master.write_text(mac_svg, encoding="utf-8")

    images: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="symaira-icon-source-") as directory:
        temporary = Path(directory)
        glyph_svg = temporary / "glyph.svg"
        glyph_svg.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" '
            f'viewBox="0 0 512 512">{glyph.replace("currentColor", args.accent)}</svg>',
            encoding="utf-8",
        )
        glyph_png = temporary / "glyph.png"
        rasterize_glyph(glyph_svg, glyph_png)

        if "macos" in platforms:
            shell_svg = temporary / "shell-macos.svg"
            shell_svg.write_text(
                render_svg(mac_template, "", args.accent), encoding="utf-8"
            )
            master_png = args.master.with_suffix(".png")
            compose_icon(shell_svg, glyph_png, master_png)
            for filename, logical_size, scale, pixels in MAC_IMAGES:
                resize_png(master_png, args.output / filename, pixels)
                images.append(
                    {
                        "filename": filename,
                        "idiom": "mac",
                        "scale": scale,
                        "size": logical_size,
                    }
                )

        if "ios" in platforms:
            ios_svg_path = args.master.with_name(f"{args.master.stem}-ios.svg")
            ios_svg_path.write_text(
                render_svg(ios_template, glyph, args.accent),
                encoding="utf-8",
            )
            ios_shell_svg = temporary / "shell-ios.svg"
            ios_shell_svg.write_text(
                render_svg(ios_template, "", args.accent), encoding="utf-8"
            )
            ios_filename = "ios-1024.png"
            compose_icon(ios_shell_svg, glyph_png, args.output / ios_filename)
            remove_alpha(args.output / ios_filename)
            images.append(
                {
                    "filename": ios_filename,
                    "idiom": "universal",
                    "platform": "ios",
                    "size": "1024x1024",
                }
            )

    contents = {
        "images": images,
        "info": {"author": "xcode", "version": 1},
    }
    (args.output / "Contents.json").write_text(
        json.dumps(contents, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
