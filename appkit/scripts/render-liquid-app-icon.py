#!/usr/bin/env python3
"""Render a Symaira Liquid Glass app icon around a product-owned optical engraving."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageColor, ImageFilter, ImageOps


SIZE = 1024
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


def flatten_glyph(path: Path, accent: str) -> str:
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
            result: list[ET.Element] = []
            for child in element:
                result.extend(flatten(child, style))
            return result
        element.tag = local_name(element.tag)
        for key, value in style.items():
            element.attrib.setdefault(key, value)
        return [element]

    children: list[ET.Element] = []
    for child in root:
        children.extend(flatten(child, {}))
    body = "\n".join(ET.tostring(child, encoding="unicode") for child in children)
    return body.replace("currentColor", accent)


def render_glyph(path: Path, accent: str) -> Image.Image:
    with tempfile.TemporaryDirectory(prefix="symaira-liquid-glyph-") as directory:
        temporary = Path(directory)
        svg = temporary / "glyph.svg"
        svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" '
            f'viewBox="0 0 512 512">{flatten_glyph(path, accent)}</svg>',
            encoding="utf-8",
        )
        subprocess.run(
            ["qlmanage", "-t", "-s", "512", "-o", directory, str(svg)],
            check=True,
            capture_output=True,
            text=True,
        )
        thumbnail = temporary / "glyph.svg.png"
        if not thumbnail.exists():
            raise RuntimeError("Quick Look did not produce the glyph thumbnail")
        image = Image.open(thumbnail).convert("RGBA")

    rgb = np.asarray(image)[..., :3].astype(np.int16)
    distance_from_white = 255 - rgb.min(axis=2)
    alpha = np.clip((distance_from_white - 4) * 3.5, 0, 255).astype(np.uint8)
    result = image.copy()
    result.putalpha(Image.fromarray(alpha, "L"))
    bbox = result.getchannel("A").getbbox()
    return result.crop(bbox) if bbox else result


def mark_mask(path: Path) -> Image.Image:
    source = Image.open(path).convert("RGBA").resize((983, 983), Image.Resampling.LANCZOS)
    canvas = Image.new("L", (SIZE, SIZE), 0)
    canvas.paste(source.getchannel("A"), (8, -4))
    return canvas


def superellipse_mask() -> Image.Image:
    y, x = np.mgrid[0:SIZE, 0:SIZE]
    center = SIZE / 2
    radius = SIZE / 2 - 34
    field = (np.abs((x - center) / radius) ** 5.15) + (
        np.abs((y - center) / radius) ** 5.15
    )
    alpha = np.clip((1.012 - field) / 0.028, 0.0, 1.0)
    alpha = alpha * alpha * (3.0 - 2.0 * alpha)
    return Image.fromarray((alpha * 255).astype(np.uint8), "L")


def radial_glow(
    color: tuple[int, int, int],
    center: tuple[float, float],
    radius: float,
    opacity: float,
) -> Image.Image:
    y, x = np.mgrid[0:SIZE, 0:SIZE]
    distance = np.sqrt((x - center[0]) ** 2 + (y - center[1]) ** 2) / radius
    falloff = np.clip(1.0 - distance, 0.0, 1.0) ** 2.2
    array = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
    array[..., :3] = color
    array[..., 3] = (falloff * opacity * 255).astype(np.uint8)
    return Image.fromarray(array, "RGBA")


def colorize_top(base: Image.Image, mask: Image.Image, accent: tuple[int, int, int]) -> Image.Image:
    tinted = Image.new("RGBA", (SIZE, SIZE), (*accent, 255))
    tinted.putalpha(mask.point(lambda value: int(value * 0.08)))
    return Image.alpha_composite(base, tinted)


def place_engraving(
    icon: Image.Image,
    glyph: Image.Image,
    clip_mask: Image.Image,
    accent: tuple[int, int, int],
) -> Image.Image:
    max_size = 196
    scale = min(max_size / glyph.width, max_size / glyph.height)
    glyph = glyph.resize(
        (max(1, int(glyph.width * scale)), max(1, int(glyph.height * scale))),
        Image.Resampling.LANCZOS,
    )
    glyph_alpha = glyph.getchannel("A")
    canvas_alpha = Image.new("L", (SIZE, SIZE), 0)
    x = 665 - glyph.width // 2
    y = 306 - glyph.height // 2
    canvas_alpha.paste(glyph_alpha, (x, y))

    safe_clip = clip_mask.filter(ImageFilter.MinFilter(31))
    canvas_alpha = ImageChops.multiply(canvas_alpha, safe_clip)

    refracted_alpha = canvas_alpha.filter(ImageFilter.GaussianBlur(13))
    glow = Image.new("RGBA", (SIZE, SIZE), (*accent, 0))
    glow.putalpha(refracted_alpha.point(lambda value: int(value * 0.13)))
    icon = Image.alpha_composite(icon, glow)

    shadow_alpha = ImageChops.offset(canvas_alpha, 3, 5)
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 3, 10, 0))
    shadow.putalpha(shadow_alpha.point(lambda value: int(value * 0.40)))
    icon = Image.alpha_composite(icon, shadow)

    cool = tuple(min(255, int(channel * 0.62 + 255 * 0.38)) for channel in accent)
    engraving = Image.new("RGBA", (SIZE, SIZE), (*cool, 0))
    engraving.putalpha(canvas_alpha.point(lambda value: int(value * 0.18)))
    icon = Image.alpha_composite(icon, engraving)

    sparkle = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
    sparkle.putalpha(
        ImageChops.offset(canvas_alpha.filter(ImageFilter.GaussianBlur(0.8)), -2, -2).point(
            lambda value: int(value * 0.12)
        )
    )
    return Image.alpha_composite(icon, sparkle)


def render_master(
    base: Image.Image,
    glyph: Image.Image,
    top_mask: Image.Image,
    accent: tuple[int, int, int],
    *,
    macos: bool,
) -> Image.Image:
    icon = base.copy()
    icon = Image.alpha_composite(icon, radial_glow(accent, (190, 160), 520, 0.10))
    icon = colorize_top(icon, top_mask, accent)
    icon = place_engraving(icon, glyph, top_mask, accent)

    if macos:
        icon.putalpha(superellipse_mask())
    else:
        icon = icon.convert("RGB").convert("RGBA")
    return icon


def write_reference_svg(path: Path, png_name: str) -> None:
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" '
        'viewBox="0 0 1024 1024">\n'
        f'  <image href="{png_name}" width="1024" height="1024"/>\n'
        "</svg>\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    if shutil.which("qlmanage") is None:
        print("error: macOS Quick Look 'qlmanage' is required", file=sys.stderr)
        return 2

    platforms = {item.strip() for item in args.platforms.split(",") if item.strip()}
    if not platforms or not platforms <= {"macos", "ios"}:
        print("error: --platforms accepts macos, ios, or macos,ios", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parent.parent
    sources = root / "Brand" / "AppIcon"
    base = Image.open(sources / "liquid-glass-base.png").convert("RGBA")
    base = ImageOps.fit(base, (SIZE, SIZE), method=Image.Resampling.LANCZOS)
    top_mask = mark_mask(sources / "symaira-mark-top.png")
    glyph = render_glyph(args.glyph, args.accent)
    accent = ImageColor.getrgb(args.accent)

    args.output.mkdir(parents=True, exist_ok=True)
    args.master.parent.mkdir(parents=True, exist_ok=True)
    for existing in args.output.glob("*.png"):
        existing.unlink()

    assets_catalog = args.output.parent
    catalog_contents = assets_catalog / "Contents.json"
    if not catalog_contents.exists():
        catalog_contents.write_text(
            json.dumps({"info": {"author": "xcode", "version": 1}}, indent=2) + "\n",
            encoding="utf-8",
        )

    images: list[dict[str, str]] = []
    if "macos" in platforms:
        master_png = args.master.with_suffix(".png")
        mac_master = render_master(base, glyph, top_mask, accent, macos=True)
        mac_master.save(master_png, optimize=True)
        write_reference_svg(args.master, master_png.name)
        for filename, logical_size, scale, pixels in MAC_IMAGES:
            mac_master.resize((pixels, pixels), Image.Resampling.LANCZOS).save(
                args.output / filename,
                optimize=True,
            )
            images.append(
                {
                    "filename": filename,
                    "idiom": "mac",
                    "scale": scale,
                    "size": logical_size,
                }
            )

    if "ios" in platforms:
        ios_filename = "ios-1024.png"
        ios_master = render_master(base, glyph, top_mask, accent, macos=False).convert("RGB")
        ios_master.save(args.output / ios_filename, optimize=True)
        ios_reference = (
            args.master
            if "macos" not in platforms
            else args.master.with_name(f"{args.master.stem}-ios.svg")
        )
        write_reference_svg(ios_reference, str((args.output / ios_filename).resolve()))
        images.append(
            {
                "filename": ios_filename,
                "idiom": "universal",
                "platform": "ios",
                "size": "1024x1024",
            }
        )

    (args.output / "Contents.json").write_text(
        json.dumps(
            {"images": images, "info": {"author": "xcode", "version": 1}},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
