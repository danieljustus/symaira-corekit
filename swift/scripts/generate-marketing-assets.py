#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.5.4", "pillow==12.1.0", "fonttools==4.64.0"]
# ///
"""Deterministic Liquid Topography marketing asset generator.

Renders social/OpenGraph cards, transparent product lockups/wordmarks and the DMG background
for the Symaira public identities. Design inputs are read from this repository only:

* design/liquid-topography/DESIGN.md      colours (canvas, ink, primary)
* design/liquid-topography/topo.json      topography parameters (idle state)
* design/liquid-topography/web/symaira-topo.js
                                           reference shader; `topo_alpha` below is a numpy port of
                                           its fragment shader at a fixed idle frame (FLOW_T)
* Sources/SymairaTheme/Resources/Fonts/GoogleSansFlex.ttf   original font, opsz 18
* Brand/Marketing/source/                  vendored, approved K1v2 icon renders (see manifest.json)

No model, no sibling checkout. Dependencies are pinned in the inline script metadata above, so
`uv run` renders byte-identical output on every machine:

    uv run scripts/generate-marketing-assets.py                 # everything
    uv run scripts/generate-marketing-assets.py --only appkit   # one identity (+ DMG with --dmg)
    uv run scripts/generate-marketing-assets.py --out DIR       # write elsewhere (determinism check)

Every run starts with `topo_selfcheck()`: NumPy 2.2 on Python 3.14 silently corrupts arithmetic on
arrays above its temporary-elision threshold (>= 32768 elements), which turned the contour lines
into jagged lattice steps. The check renders the same field in one large and in many small arrays
and refuses to write anything if they differ or the field is not continuous.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MARKETING = ROOT / "Brand" / "Marketing"
DESIGN = ROOT / "design" / "liquid-topography"
FONT_PATH = ROOT / "Sources" / "SymairaTheme" / "Resources" / "Fonts" / "GoogleSansFlex.ttf"
GENERATOR_VERSION = 1

# --- design tokens (DESIGN.md colors; keep in sync, verified by hash in manifest) -------------
THEMES = {
    "light": {"canvas": "#EEEDEA", "ink": "#141413", "ink2": "#2B2B2A", "ink3": "#62615D", "topo": "#2B2B2A", "dark": False},
    "dark": {"canvas": "#1C1C1B", "ink": "#EEEDEA", "ink2": "#B0AEA9", "ink3": "#97958F", "topo": "#E1E0DA", "dark": True},
}
PRIMARY = "#E0D2BA"
# Neutral mid gray for the DMG: black (light mode) and white (dark mode) Finder labels both
# reach >= 4.4:1 against it. Same warm-gray family as the palette, not a new accent.
DMG_GRAY = "#767572"

FLOW_T = 38.0  # fixed idle frame (runtime picks a random start; marketing art uses this one)
# Marketing art shows more terrain than the app: same shader and line weight, smaller features.
TOPO_ZOOM = 1.6
# Legibility halo (CSS px): instead of the shader's centred basin, lines are attenuated by
# topo.json `basinOpen` behind the text block and the logo and recover over this distance.
HALO_RADIUS = 110
CARD_DPR = 1.5  # line weight of the shader at a 1280 px wide card
TEXT_SS = 4  # text supersampling
OPSZ = 18


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- topography (numpy port of symaira-topo.js fragment shader, idle state) -------------------
# float64 on purpose: the shader hash multiplies to ~1e5 and then takes fract(), so float32 results
# depend on FMA/rounding of the device. float64 makes the marketing frame identical on every machine.
def _fract(x):
    return x - np.floor(x)


def _hash(px, py, pz):
    f32 = np.float64
    px = _fract(px * f32(0.3183099) + f32(0.1))
    py = _fract(py * f32(0.3183099) + f32(0.1))
    pz = _fract(pz * f32(0.3183099) + f32(0.1))
    px, py, pz = px * f32(17), py * f32(17), pz * f32(17)
    return _fract(px * py * pz * (px + py + pz))


def _n3(x, y, z):
    f32 = np.float64
    ix, iy, iz = np.floor(x), np.floor(y), np.floor(z)
    fx, fy, fz = x - ix, y - iy, z - iz
    fx, fy, fz = fx * fx * (f32(3) - f32(2) * fx), fy * fy * (f32(3) - f32(2) * fy), fz * fz * (f32(3) - f32(2) * fz)

    def h(dx, dy, dz):
        return _hash(ix + f32(dx), iy + f32(dy), iz + f32(dz))

    def mix(a, b, t):
        return a + (b - a) * t

    return mix(
        mix(mix(h(0, 0, 0), h(1, 0, 0), fx), mix(h(0, 1, 0), h(1, 1, 0), fx), fy),
        mix(mix(h(0, 0, 1), h(1, 0, 1), fx), mix(h(0, 1, 1), h(1, 1, 1), fx), fy),
        fz,
    )


def _fbm(x, y, z):
    f32 = np.float64
    return (
        _n3(x, y, z) * f32(0.62)
        + _n3(x * f32(2.03) + f32(7), y * f32(2.03) + f32(7), z * f32(2.03) + f32(7)) * f32(0.26)
        + _n3(x * f32(4.1) + f32(3), y * f32(4.1) + f32(3), z * f32(4.1) + f32(3)) * f32(0.12)
    )


def _fwidth(v):
    """GPU-style quad derivatives (2x2 blocks) so line anti-aliasing matches the shader."""
    h, w = v.shape
    dx = np.zeros_like(v)
    dy = np.zeros_like(v)
    dx[:, 0::2] = v[:, 1::2] - v[:, 0::2]
    dx[:, 1::2] = dx[:, 0::2]
    dy[0::2, :] = v[1::2, :] - v[0::2, :]
    dy[1::2, :] = dy[0::2, :]
    return np.abs(dx) + np.abs(dy)


def _smoothstep(a, b, x):
    t = np.clip((x - a) / np.maximum(b - a, np.float64(1e-9)), 0, 1)
    return t * t * (np.float64(3) - np.float64(2) * t)


def _iso(v, w, s):
    f = _fract(v)
    d = np.minimum(f, np.float64(1) - f)
    a = _fwidth(v)
    return np.float64(1) - _smoothstep(a * max(w - s, 0.0), a * (w + s), d)


def _height(px, py, params, flow_t=FLOW_T, zoom=1.0):
    """Idle-state height field at CSS-pixel coordinates (shader lines 34-36).

    zoom > 1 zooms out (divides topo.json `scale`); line weight is unaffected because the
    contour width comes from the screen-space derivative in `_iso`.
    """
    f32 = np.float64
    scale = f32(params["scale"]) / f32(zoom)
    qx, qy = px / scale, py / scale
    t = f32(flow_t)
    wx = _fbm(qx * f32(0.7), qy * f32(0.7), np.full_like(qx, t * f32(0.6)))
    wy = _fbm(qx * f32(0.7) + f32(5.2), qy * f32(0.7) + f32(5.2), np.full_like(qx, t * f32(0.6)))
    warp = f32(params["states"]["idle"]["warp"])
    return _fbm(qx + wx * warp, qy + wy * warp, np.full_like(qx, t))


def topo_selfcheck(params):
    """Fail closed if this NumPy build cannot compute the height field correctly.

    256 x 256 = 65536 elements crosses NumPy's temporary-elision threshold; each 256-element row
    stays below it. A correct build gives identical values both ways, and neighbouring pixels of
    the smooth field never differ by more than a small fraction of one contour interval.
    """
    side = 256
    grid = (np.arange(side, dtype=np.float64) + 0.5) * 3.0
    px, py = np.meshgrid(grid, grid)
    whole = _height(px, py, params)
    rows = np.stack([_height(px[i].copy(), py[i].copy(), params) for i in range(side)])
    step = max(np.abs(np.diff(whole, axis=0)).max(), np.abs(np.diff(whole, axis=1)).max())
    interval = 1.0 / params["levels"]
    if not np.array_equal(whole, rows) or step > 0.25 * interval:
        raise SystemExit(
            f"topography self-check failed (numpy {np.__version__}, max neighbour step {step:.4f}, "
            f"large/small array mismatch {np.abs(whole - rows).max():.4f}). "
            "Run with `uv run scripts/generate-marketing-assets.py` to use the pinned NumPy."
        )


def _sd_box(px, py, rx, ry, rw, rh, rad):
    """Signed distance to a rounded rectangle (shader sdBox), all in CSS px."""
    cx, cy = rx + rw * 0.5, ry + rh * 0.5
    dx = np.abs(px - cx) - rw * 0.5 + rad
    dy = np.abs(py - cy) - rh * 0.5 + rad
    return np.sqrt(np.maximum(dx, 0) ** 2 + np.maximum(dy, 0) ** 2) + np.minimum(np.maximum(dx, dy), 0) - rad


def topo_alpha(width, height, dpr, params, rects, dark, halo, flow_t=FLOW_T):
    """Alpha coverage (0..1) of the topography at the idle frame.

    rects: list of (x, y, w, h, radius, is_hill) in output pixels. They become protected zones
    (shader `data-topo=protect`) and, when is_hill, a gentle hill (`data-topo=hill`).
    halo: list of (x, y, w, h) in output pixels (text block, logo). Marketing deviation from the
    shader: its centred basin is replaced by a soft fade around these, see HALO_RADIUS.
    """
    f32 = np.float64
    cols = (np.arange(width, dtype=f32) + f32(0.5)) / f32(dpr)
    rows = (np.arange(height, dtype=f32) + f32(0.5)) / f32(dpr)
    px, py = np.meshgrid(cols, rows)
    h = _height(px, py, params, flow_t, TOPO_ZOOM)

    mask = np.ones_like(px)
    hill = np.zeros_like(px)
    for rx, ry, rw, rh, rad, is_hill in rects:
        sd = _sd_box(px, py, *(f32(v / dpr) for v in (rx, ry, rw, rh, rad)))
        if is_hill:
            hill = np.maximum(hill, f32(0.025) * np.exp(-np.maximum(sd, 0) / f32(24)))
        mask = np.minimum(mask, _smoothstep(f32(2), f32(8), sd))
    h = h + hill

    v = h * f32(params["levels"])
    line = _iso(v, 0.65 * dpr, 0.5)
    idx = _iso(v / f32(params["indexEvery"]), 1.0 * dpr, 1.6)
    near = np.full_like(px, np.inf)
    for rx, ry, rw, rh in halo:
        near = np.minimum(near, _sd_box(px, py, *(f32(v / dpr) for v in (rx, ry, rw, rh)), f32(0)))
    basin = f32(params["basinOpen"])
    vis = f32(1) + (_smoothstep(f32(0), f32(HALO_RADIUS), near) - f32(1)) * basin
    k = f32(1.0 if dark else params["lightModeFactor"])
    a = np.minimum(np.maximum(line * f32(params["lineAlpha"]), idx * f32(params["indexAlpha"])) * vis, f32(params["maxAlpha"]))
    return (a * mask * k).astype(np.float64)


def composite_topo(canvas_rgb, alpha, topo_rgb):
    base = np.array(canvas_rgb, dtype=np.float64)
    col = np.array(topo_rgb, dtype=np.float64)
    out = np.empty(alpha.shape + (3,), dtype=np.float64)
    out[...] = base
    out = out * (1 - alpha[..., None]) + col * alpha[..., None]
    # 8x8 Bayer ordered dither: the lines are only a few 8-bit levels high; plain rounding would
    # stair-step their anti-aliased edges. Ordered dither is deterministic and compresses well.
    bayer = _bayer(8)
    h, w = alpha.shape
    thr = np.tile(bayer, (h // 8 + 1, w // 8 + 1))[:h, :w, None]
    return Image.fromarray(np.clip(np.floor(out + thr), 0, 255).astype(np.uint8), "RGB")


def _bayer(n):
    m = np.array([[0]])
    while m.shape[0] < n:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return (m + 0.5) / (n * n)


# --- typography ---------------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _pil_font(size_px, weight):
    f = ImageFont.truetype(str(FONT_PATH), size_px)
    f.set_variation_by_axes([OPSZ, 100, weight, 0, 0])
    return f


@lru_cache(maxsize=None)
def _kerning(weight):
    """Pair kerning (font units) from the GPOS `kern` feature instanced at opsz 18 / weight."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    font = instancer.instantiateVariableFont(
        TTFont(str(FONT_PATH)), {"opsz": OPSZ, "wdth": 100, "wght": weight, "ROND": 0, "slnt": 0}
    )
    upm = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    gpos = font["GPOS"].table
    lookups = set()
    for rec in gpos.FeatureList.FeatureRecord:
        if rec.FeatureTag == "kern":
            lookups.update(rec.Feature.LookupListIndex)
    subtables = []
    for li in sorted(lookups):
        for st in gpos.LookupList.Lookup[li].SubTable:
            if st.LookupType == 9:
                st = st.ExtSubTable
            if st.LookupType == 2:
                subtables.append(st)

    def xadv(value):
        return getattr(value, "XAdvance", 0) or 0 if value is not None else 0

    def pair(g1, g2):
        for st in subtables:
            cov = st.Coverage.glyphs
            if g1 not in cov:
                continue
            if st.Format == 1:
                ps = st.PairSet[cov.index(g1)]
                for rec in ps.PairValueRecord:
                    if rec.SecondGlyph == g2:
                        return xadv(rec.Value1)
            else:
                c1 = st.ClassDef1.classDefs.get(g1, 0)
                c2 = st.ClassDef2.classDefs.get(g2, 0)
                rec = st.Class1Record[c1].Class2Record[c2]
                value = xadv(rec.Value1)
                if value:
                    return value
        return 0

    cache = {}

    def kern_em(a, b):
        key = (a, b)
        if key not in cache:
            ga, gb = cmap.get(ord(a)), cmap.get(ord(b))
            cache[key] = pair(ga, gb) / upm if ga and gb else 0.0
        return cache[key]

    return kern_em


def layout(text, size, weight, tracking):
    """Return [(char, x)] pen positions and total advance width, in px."""
    ref = _pil_font(1000, weight)
    kern = _kerning(weight)
    x = 0.0
    out = []
    for i, ch in enumerate(text):
        out.append((ch, x))
        x += ref.getlength(ch) / 1000 * size
        if i + 1 < len(text):
            x += kern(ch, text[i + 1]) * size + tracking * size
    return out, x


def text_width(text, size, weight, tracking):
    return layout(text, size, weight, tracking)[1]


def draw_text(img, text, x, baseline, size, weight, tracking, color):
    """Draw one line with its baseline at `baseline` (px), supersampled; returns bbox rect."""
    pens, width = layout(text, size, weight, tracking)
    pad = int(size * 0.4) + 2
    x0, y0 = math.floor(x) - pad, math.floor(baseline - size * 1.0) - pad
    w, h = math.ceil(width) + 2 * pad, math.ceil(size * 1.45) + 2 * pad
    mask = Image.new("L", (w * TEXT_SS, h * TEXT_SS), 0)
    d = ImageDraw.Draw(mask)
    font = _pil_font(int(round(size * TEXT_SS)), weight)
    for ch, px in pens:
        d.text(((x - x0 + px) * TEXT_SS, (baseline - y0) * TEXT_SS), ch, font=font, fill=255, anchor="ls")
    mask = mask.resize((w, h), Image.Resampling.BOX)
    if img.mode == "RGBA":
        layer = Image.new("RGBA", (w, h), color + (0,))
        layer.putalpha(mask)
        img.alpha_composite(layer, (x0, y0)) if x0 >= 0 and y0 >= 0 else _paste_clipped(img, layer, x0, y0)
    else:
        img.paste(color, (x0, y0), mask)
    return (x, baseline - size * 0.76, width, size * 0.98)


def _paste_clipped(img, layer, x0, y0):
    canvas = Image.new("RGBA", img.size, (0, 0, 0, 0))
    canvas.alpha_composite(layer, (max(x0, 0), max(y0, 0)), (max(-x0, 0), max(-y0, 0)))
    img.alpha_composite(canvas)


def wrap_text(text, size, weight, tracking, max_width):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and text_width(trial, size, weight, tracking) > max_width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    lines.append(cur)
    return lines


# --- identity artwork ------------------------------------------------------------------------
CARD_S_FILL = 674 / 1024  # bare S on cards: same height as the S inside every K1v2 icon
LOCKUP_S_FILL = 674 / 793  # bare S in lockups/logos: the previous visual size, now centred


def load_identity_image(ident, theme, px, s_fill=CARD_S_FILL):
    """Return (RGBA image of side px, corner-radius fraction, has_plate)."""
    src = ident["source"]
    if src == "umbrella":
        # Plate-less R1 S: the light variant is made for light surfaces, dark for dark ones.
        surface = "dark" if theme == "dark" else "light"
        s = Image.open(MARKETING / "source" / "umbrella" / f"S-R1-{surface}.png").convert("RGBA")
        s = s.crop(s.getchannel("A").getbbox())
        scale = px * s_fill / s.height
        s = s.resize((round(s.width * scale), round(s.height * scale)), Image.Resampling.LANCZOS)
        out = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        out.alpha_composite(s, ((px - s.width) // 2, (px - s.height) // 2))
        return out, 0.0, False
    mode = "Dark" if theme == "dark" else "Default"
    im = Image.open(MARKETING / "source" / "identities" / src / f"macOS-{mode}-512.png").convert("RGBA")
    return im.resize((px, px), Image.Resampling.LANCZOS), 0.23, True


def paste_identity(img, ident, theme, x, y, size, shadow=True, s_fill=CARD_S_FILL):
    art, _, plate = load_identity_image(ident, theme, size, s_fill)
    if plate and shadow and not THEMES[theme]["dark"]:
        a = art.getchannel("A").point(lambda v: int(v * 0.16))
        sh = Image.new("RGBA", art.size, rgb(THEMES[theme]["ink"]) + (0,))
        sh.putalpha(a)
        pad = int(size * 0.2)
        big = Image.new("RGBA", (size + 2 * pad, size + 2 * pad), (0, 0, 0, 0))
        big.alpha_composite(sh, (pad, pad))
        big = big.filter(ImageFilter.GaussianBlur(size * 0.035))
        _alpha_paste(img, big, x - pad, y - pad + int(size * 0.025))
    _alpha_paste(img, art, x, y)


def _alpha_paste(img, layer, x, y):
    if img.mode == "RGBA":
        base = Image.new("RGBA", img.size, (0, 0, 0, 0))
        base.paste(layer, (x, y))
        img.alpha_composite(base)
    else:
        rgba = img.convert("RGBA")
        base = Image.new("RGBA", img.size, (0, 0, 0, 0))
        base.paste(layer, (x, y))
        rgba.alpha_composite(base)
        img.paste(rgba.convert("RGB"))


# --- cards -------------------------------------------------------------------------------------
NAME_W, EYEBROW_W, ROLE_W = 700, 650, 500


def fit_name(lines, max_size, max_width):
    size = max_size
    while size > 20 and max(text_width(t, size, NAME_W, -0.025) for t in lines) > max_width:
        size -= 1
    return size


def card(ident, theme, fmt, params):
    width, height = fmt["size"]
    th = THEMES[theme]
    ink, ink2, ink3 = rgb(th["ink"]), rgb(th["ink2"]), rgb(th["ink3"])
    wide = width / height > 1.4
    protected = []
    texts = []  # (text, x, baseline, size, weight, tracking, color)
    eyebrow = ident.get("eyebrow", "Symaira")
    names = ident["name"]

    if wide:
        u = min(width / 1280, height / 640)
        m = round(80 * u)
        icon = round(0.52 * height)
        icon_x, icon_y = width - m - icon, (height - icon) // 2
        text_w = icon_x - m - round(48 * u)
        name_size = fit_name(names, 136 * u, text_w)
        eb_size, role_size = 40 * u, 38 * u
        role_lines = wrap_text(ident["role"], role_size, ROLE_W, -0.005, text_w)
        gap_role = 42 * u
        block = (eb_size * 1.29 if eyebrow else 0) + name_size * 0.74 + (len(names) - 1) * name_size * 1.04
        block += gap_role + role_size * 0.74 + (len(role_lines) - 1) * role_size * 1.32
        top = (height - block) / 2
        x = m
    else:
        m = round(0.075 * width)
        safe_top = round(0.14 * height) if height / width > 1.6 else m
        safe_bottom = round(0.14 * height) if height / width > 1.6 else m
        icon = round(0.5 * width)
        icon_x = width - m - icon
        icon_y = max(safe_top, round(height * (0.10 if height / width < 1.4 else 0.16)))
        text_w = width - 2 * m
        name_size = fit_name(names, 0.15 * width, text_w)
        eb_size, role_size = 0.04 * width, 0.04 * width
        role_lines = wrap_text(ident["role"], role_size, ROLE_W, -0.005, text_w)
        gap_role = 0.042 * width
        block = (eb_size * 1.29 if eyebrow else 0) + name_size * 0.74 + (len(names) - 1) * name_size * 1.04
        block += gap_role + role_size * 0.74 + (len(role_lines) - 1) * role_size * 1.32
        # block ends on the last baseline; keep descenders (g, p, y) out of the bottom safe zone
        top = height - safe_bottom - block - role_size * 0.24
        x = m

    y = top
    if eyebrow:
        y += eb_size * 0.74
        texts.append((eyebrow, x, y, eb_size, EYEBROW_W, -0.01, ink3))
        y += eb_size * 0.55
    for i, nm in enumerate(names):
        y += name_size * (0.74 if i == 0 else 1.04)
        texts.append((nm, x, y, name_size, NAME_W, -0.025, ink))
    y += gap_role
    for i, ln in enumerate(role_lines):
        y += role_size * (0.74 if i == 0 else 1.32)
        texts.append((ln, x, y, role_size, ROLE_W, -0.005, ink2))

    for text, tx, base, size, weight, tracking, _ in texts:
        w = text_width(text, size, weight, tracking)
        pad = 14 * (width / 1280)
        protected.append((tx - pad, base - size * 0.80 - pad, w + 2 * pad, size * 1.05 + 2 * pad, 12, False))
    if ident["source"] == "umbrella":
        # plate-less S: protect the glyph itself, not the whole (mostly empty) icon box
        gx0, gy0, gx1, gy1 = load_identity_image(ident, theme, icon)[0].getchannel("A").getbbox()
        pad = round(0.04 * icon)
        protected.append((icon_x + gx0 - pad, icon_y + gy0 - pad, gx1 - gx0 + 2 * pad, gy1 - gy0 + 2 * pad, 12, True))
    else:
        protected.append((icon_x, icon_y, icon, icon, icon * 0.23, True))

    text_rects = protected[:-1]
    x0 = min(r[0] for r in text_rects)
    y0 = min(r[1] for r in text_rects)
    x1 = max(r[0] + r[2] for r in text_rects)
    y1 = max(r[1] + r[3] for r in text_rects)
    halo = [(x0, y0, x1 - x0, y1 - y0), protected[-1][:4]]

    dpr = CARD_DPR * width / 1280
    alpha = topo_alpha(width, height, dpr, params, protected, th["dark"], halo)
    img = composite_topo(rgb(th["canvas"]), alpha, rgb(th["topo"]))
    paste_identity(img, ident, theme, icon_x, icon_y, icon)
    for text, tx, base, size, weight, tracking, color in texts:
        draw_text(img, text, tx, base, size, weight, tracking, color)
    return img


# --- transparent lockups / wordmarks -------------------------------------------------------------
def ink_for(surface):
    t = THEMES["dark" if surface == "on-dark" else "light"]
    return rgb(t["ink"]), rgb(t["ink3"])


def text_stack(img, ident, surface, x, top, name_size, eb_size, align_width=None):
    ink, ink3 = ink_for(surface)
    y = top
    eyebrow = ident.get("eyebrow", "Symaira")
    names = ident["name"]
    widths = []
    if eyebrow:
        y += eb_size * 0.74
        w = text_width(eyebrow, eb_size, EYEBROW_W, -0.01)
        ox = x + ((align_width - w) / 2 if align_width else 0)
        draw_text(img, eyebrow, ox, y, eb_size, EYEBROW_W, -0.01, ink3)
        widths.append(w)
        y += eb_size * 0.3
    for i, nm in enumerate(names):
        y += name_size * (0.74 if i == 0 else 1.04)
        w = text_width(nm, name_size, NAME_W, -0.025)
        ox = x + ((align_width - w) / 2 if align_width else 0)
        draw_text(img, nm, ox, y, name_size, NAME_W, -0.025, ink)
        widths.append(w)
    return y + name_size * 0.26, max(widths)


def stack_metrics(ident, name_size, eb_size):
    eyebrow = ident.get("eyebrow", "Symaira")
    names = ident["name"]
    w = max([text_width(n, name_size, NAME_W, -0.025) for n in names] + ([text_width(eyebrow, eb_size, EYEBROW_W, -0.01)] if eyebrow else [0]))
    h = (eb_size * 1.04 if eyebrow else 0) + name_size * 0.74 + (len(names) - 1) * name_size * 1.04 + name_size * 0.26
    return w, h


def wordmark(ident, surface):
    name_size, eb_size, pad = 120, 50, 28
    w, h = stack_metrics(ident, name_size, eb_size)
    img = Image.new("RGBA", (math.ceil(w) + 2 * pad, math.ceil(h) + 2 * pad), (0, 0, 0, 0))
    text_stack(img, ident, surface, pad, pad, name_size, eb_size)
    return img


def horizontal_lockup(ident, surface):
    icon, gap, pad = 256, 44, 28
    name_size, eb_size = 112, 46
    w, h = stack_metrics(ident, name_size, eb_size)
    height = max(icon, math.ceil(h)) + 2 * pad
    img = Image.new("RGBA", (pad + icon + gap + math.ceil(w) + pad, height), (0, 0, 0, 0))
    theme = "dark" if surface == "on-dark" else "light"
    paste_identity(img, ident, theme, pad, (height - icon) // 2, icon, shadow=False, s_fill=LOCKUP_S_FILL)
    text_stack(img, ident, surface, pad + icon + gap, (height - h) / 2, name_size, eb_size)
    return img


def product_logo(ident, surface):
    """1024 x 1024 transparent vertical lockup: icon, 'Symaira', product name."""
    side = 1024
    name_size = fit_name(ident["name"], 150, side - 160)
    eb_size = 56
    w, h = stack_metrics(ident, name_size, eb_size)
    icon = 480
    gap = 44
    total = icon + gap + h
    img = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    top = (side - total) / 2
    theme = "dark" if surface == "on-dark" else "light"
    paste_identity(img, ident, theme, (side - icon) // 2, round(top), icon, shadow=False, s_fill=LOCKUP_S_FILL)
    text_stack(img, ident, surface, 0, top + icon + gap, name_size, eb_size, align_width=side)
    return img


# --- DMG ---------------------------------------------------------------------------------------
DMG_SIZE = (660, 420)
DMG_ICON_CENTERS = ((180, 220), (480, 220))  # Finder positions set by scripts/create-symaira-dmg.sh
ARROW = {"x0": 268, "x1": 392, "y": 216, "head": 14, "stroke": 3.0}


def dmg_assets(params, scale):
    w, h = DMG_SIZE[0] * scale, DMG_SIZE[1] * scale
    protected = []
    for cx, cy in DMG_ICON_CENTERS:
        protected.append(((cx - 86) * scale, (cy - 84) * scale, 172 * scale, 188 * scale, 18 * scale, False))
    alpha = topo_alpha(w, h, 1.5 * scale, params, protected, False, [r[:4] for r in protected])
    flat = composite_topo(rgb(DMG_GRAY), alpha, rgb(THEMES["light"]["topo"])).convert("RGBA")
    terrain = Image.new("RGBA", (w, h), rgb(THEMES["light"]["topo"]) + (0,))
    terrain.putalpha(Image.fromarray(np.clip(np.rint(alpha * 255), 0, 255).astype(np.uint8), "L"))
    # champagne arrow, supersampled
    ss = 4
    arrow = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(arrow)
    a = ARROW
    s = scale * ss
    col = rgb(PRIMARY) + (230,)
    d.line([(a["x0"] * s, a["y"] * s), ((a["x1"] - a["head"] * 0.4) * s, a["y"] * s)], fill=col, width=round(a["stroke"] * s))
    d.line([((a["x1"] - a["head"]) * s, (a["y"] - a["head"]) * s), (a["x1"] * s, a["y"] * s), ((a["x1"] - a["head"]) * s, (a["y"] + a["head"]) * s)], fill=col, width=round(a["stroke"] * s), joint="curve")
    r = a["stroke"] * s / 2
    for (px, py) in ((a["x0"], a["y"]), (a["x1"] - a["head"], a["y"] - a["head"]), (a["x1"] - a["head"], a["y"] + a["head"]), (a["x1"], a["y"])):
        d.ellipse([px * s - r, py * s - r, px * s + r, py * s + r], fill=col)
    arrow = arrow.resize((w, h), Image.Resampling.LANCZOS)
    flat.alpha_composite(arrow)
    return flat.convert("RGB"), terrain


def dmg_svg(terrain_png):
    w, h = DMG_SIZE
    a = ARROW
    b64 = base64.b64encode(terrain_png).decode()
    head = a["head"]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
        f'  <title>Symaira installer background</title>\n'
        f'  <rect width="{w}" height="{h}" fill="{DMG_GRAY}"/>\n'
        f'  <image width="{w}" height="{h}" xlink:href="data:image/png;base64,{b64}"/>\n'
        f'  <g fill="none" stroke="{PRIMARY}" stroke-opacity=".9" stroke-width="{a["stroke"]}" stroke-linecap="round" stroke-linejoin="round">\n'
        f'    <path d="M{a["x0"]} {a["y"]}H{a["x1"] - head * 0.4:g}"/>\n'
        f'    <path d="M{a["x1"] - head} {a["y"] - head}L{a["x1"]} {a["y"]}L{a["x1"] - head} {a["y"] + head}"/>\n'
        f'  </g>\n</svg>\n'
    )


# --- driver ------------------------------------------------------------------------------------
def save_png(img, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)
    return {
        "path": None,
        "size": list(img.size),
        "mode": img.mode,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def load_params():
    return json.loads((DESIGN / "topo.json").read_text())


def design_inputs():
    files = [
        DESIGN / "DESIGN.md",
        DESIGN / "topo.json",
        DESIGN / "web" / "symaira-topo.js",
        FONT_PATH,
        MARKETING / "identities.json",
        MARKETING / "source" / "identities-provenance.json",
        MARKETING / "source" / "umbrella" / "S-R1-light.png",
        MARKETING / "source" / "umbrella" / "S-R1-dark.png",
        MARKETING / "source" / "umbrella" / "PROVENANCE.json",
    ]
    for d in sorted((MARKETING / "source" / "identities").iterdir()):
        files += sorted(d.glob("*.png"))
    return {str(p.relative_to(ROOT)): sha256_file(p) for p in files}


def build(out_root: Path, only: set[str] | None, dmg: bool, dmg_out: Path | None):
    spec = json.loads((MARKETING / "identities.json").read_text())
    params = load_params()
    topo_selfcheck(params)
    outputs = []

    def record(img, path, role, identity, **extra):
        info = save_png(img, path)
        info["path"] = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path.relative_to(out_root))
        info.update({"role": role, "identity": identity, **extra})
        outputs.append(info)

    for ident in spec["identities"]:
        if only and ident["id"] not in only:
            continue
        ident = {**spec["defaults"], **ident}
        base = out_root / ident["id"]
        for fmt_name in ident["formats"]:
            fmt = spec["formats"][fmt_name]
            for theme in ("dark", "light"):
                img = card(ident, theme, fmt, params)
                record(img, base / f"{fmt_name}-{theme}.png", fmt["role"], ident["id"], theme=theme, format=fmt_name)
        for surface in ("on-light", "on-dark"):
            record(wordmark(ident, surface), base / f"wordmark-{surface}.png", "transparent wordmark", ident["id"], surface=surface)
            record(horizontal_lockup(ident, surface), base / f"lockup-{surface}.png", "transparent horizontal product lockup", ident["id"], surface=surface)
        record(product_logo(ident, "on-light"), base / "product-logo.png", "assets/branding/product-logo.png (transparent 1024 vertical lockup, ink for light surfaces)", ident["id"], surface="on-light")
        record(product_logo(ident, "on-dark"), base / "product-logo-on-dark.png", "transparent 1024 vertical lockup, ink for dark surfaces", ident["id"], surface="on-dark")
        print(f"rendered {ident['id']}", flush=True)

    dmg_info = None
    if dmg:
        dmg_dir = dmg_out or (ROOT / "Brand" / "DMG")
        dmg_dir.mkdir(parents=True, exist_ok=True)
        flat, terrain = dmg_assets(params, 1)
        flat2, terrain2 = dmg_assets(params, 2)
        for name, im in (("symaira-dmg-background.png", flat), ("symaira-dmg-background@2x.png", flat2)):
            info = save_png(im, dmg_dir / name)
            info.update({"path": f"Brand/DMG/{name}" if dmg_out is None else str(dmg_dir / name), "role": "DMG background" + (" @2x" if "@2x" in name else ""), "identity": "dmg"})
            outputs.append(info)
        buf = io.BytesIO()
        terrain.save(buf, "PNG", optimize=True)
        (dmg_dir / "symaira-dmg-background.svg").write_text(dmg_svg(buf.getvalue()))
        outputs.append({"path": "Brand/DMG/symaira-dmg-background.svg" if dmg_out is None else str(dmg_dir / "symaira-dmg-background.svg"), "size": list(DMG_SIZE), "mode": "svg", "sha256": sha256_file(dmg_dir / "symaira-dmg-background.svg"), "bytes": (dmg_dir / "symaira-dmg-background.svg").stat().st_size, "role": "DMG background source (vector arrow + embedded terrain raster)", "identity": "dmg"})
        dmg_info = {"size": list(DMG_SIZE), "icon_centers": [list(c) for c in DMG_ICON_CENTERS], "gray": DMG_GRAY, "arrow": ARROW}
    return outputs, dmg_info


def write_manifest(outputs, dmg_info):
    spec = json.loads((MARKETING / "identities.json").read_text())
    vendor = {}
    for ident in spec["identities"]:
        base = f"Brand/Marketing/exports/{ident['id']}"
        vendor[ident["id"]] = {
            "docs/assets/social-preview.png": f"{base}/social-preview-dark.png",
            "assets/branding/product-logo.png": f"{base}/product-logo.png",
            "assets/branding/product-logo-on-dark.png": f"{base}/product-logo-on-dark.png",
            "assets/branding/og.png": f"{base}/og-dark.png",
        }
    manifest = {
        "generator": "scripts/generate-marketing-assets.py",
        "generator_version": GENERATOR_VERSION,
        "generator_sha256": sha256_file(Path(__file__)),
        "design_system": "Liquid Topography (design/liquid-topography/DESIGN.md)",
        "render": {"state": "idle", "flow_t": FLOW_T, "topo_zoom": TOPO_ZOOM, "card_dpr_at_1280": CARD_DPR, "font": "Google Sans Flex, opsz 18", "text_supersample": TEXT_SS},
        "colors": {"light": {k: v for k, v in THEMES["light"].items() if k != "dark"}, "dark": {k: v for k, v in THEMES["dark"].items() if k != "dark"}, "primary": PRIMARY, "dmg_gray": DMG_GRAY},
        "inputs": design_inputs(),
        "identities": {i["id"]: {k: v for k, v in i.items() if k != "id"} for i in spec["identities"]},
        "dmg": dmg_info,
        "outputs": sorted(outputs, key=lambda o: o["path"]),
        "usage": {
            "regenerate": "uv run scripts/generate-marketing-assets.py",
            "verify": "uv run scripts/verify-marketing-assets.py [--determinism]",
            "refresh_icons": "uv run scripts/vendor-marketing-icons.py --icons-root <dir with <key>/exports/macOS-{Default,Dark}.png + manifest.json>",
            "naming": "social-preview-{dark,light}.png 1280x640; og-{dark,light}.png 1200x630; lockup-on-{light,dark}.png and wordmark-on-{light,dark}.png transparent (suffix = surface the ink is made for); product-logo.png / product-logo-on-dark.png 1024x1024 transparent vertical lockup",
            "vendoring": vendor,
            "readme_picture": '<picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/social-preview-dark.png"><img alt="Symaira <Product>" src="docs/assets/social-preview-light.png"></picture>',
            "notes": [
                "GitHub social preview upload: use social-preview-dark.png (1280x640).",
                "Cards carry no version, metric or UI screenshot; roles come from Brand/Marketing/identities.json.",
                "scoop-bucket is provisional (plate-less K1v2 Symaira S, no approved Scoop icon).",
                "router reuses the Fritz signet for the documented public-kit title 'Symaira Router'; it never replaces Symaira Fritz.",
            ],
        },
    }
    (MARKETING / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", action="append", help="identity id (repeatable); skips manifest write")
    ap.add_argument("--out", type=Path, help="write cards here instead of Brand/Marketing/exports (skips manifest write)")
    ap.add_argument("--dmg", action="store_true", help="also render the DMG background (default: only when rendering everything)")
    ap.add_argument("--dmg-only", action="store_true", help="render only the DMG background (no manifest write)")
    args = ap.parse_args()
    full = not args.only and not args.out and not args.dmg_only
    if args.dmg_only:
        args.only = ["__none__"]
        args.dmg = True
    out_root = args.out or (MARKETING / "exports")
    dmg_out = (args.out / "_dmg") if args.out else None
    outputs, dmg_info = build(out_root, set(args.only) if args.only else None, full or args.dmg, dmg_out)
    if full:
        write_manifest(outputs, dmg_info)
        print(f"wrote {len(outputs)} outputs and Brand/Marketing/manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
