#!/usr/bin/env python3
"""Build the Symaira icon set from Brand/Icons/icons.svg.

Source format (one sprite, 24x24 grid, stroke style is implied):

    <symbol id="delete" data-label="Löschen">
      <g id="lid" data-o="5 7" data-hover="r:-6 y:-1.2" data-click="lift:3,-18">...</g>
      <path d="..."/>                      <!-- static part -->
    </symbol>

Part attributes: data-o = transform origin, data-hover = target pose
("s: sx: sy: r: x: y: o:"), data-click = comma-free list of motions separated
by spaces, each "name[:args][@delay]" (args comma-separated). Elements with
fill="currentColor" are filled instead of stroked.

Outputs:
  Brand/Icons/dist/svg/<id>.svg        static SVG for any platform
  Brand/Icons/dist/symaira-icons.css   hover/click motion for the web
  Brand/Icons/dist/icons.json          labels + motion spec for other clients
  Sources/SymairaTheme/SymairaIconData.swift   generated paths + motion
  docs/icon-preview.html               interactive preview
"""
import json, math, re, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "Brand/Icons/icons.svg"
DIST = ROOT / "Brand/Icons/dist"
SWIFT = ROOT / "Sources/SymairaTheme/SymairaIconData.swift"
PREVIEW = ROOT / "docs/icon-preview.html"
NS = "{http://www.w3.org/2000/svg}"

SPRING = (0.34, 1.56, 0.64, 1)
EASE = (0.45, 0, 0.2, 1)
OUT = (0.2, 0.8, 0.3, 1)
LINEAR = (0, 0, 1, 1)


def m(dur, ease, *frames):
    """Motion: duration, easing per segment, frames (t, pose-dict)."""
    return {"dur": dur, "ease": ease, "frames": [[t, p] for t, p in frames]}


# Motion library. Every motion starts and ends at the identity pose unless a
# frame at t=0 / t=1 says otherwise.
MOTIONS = {
    "pop": lambda k=1.15: m(.45, OUT, (.2, {"s": .82}), (.55, {"s": k})),
    "turn": lambda deg=360: m(.75, SPRING if abs(deg) < 360 else EASE, (1, {"r": deg})),
    "swing": lambda deg=16: m(.9, OUT, *[(t, {"r": deg * f}) for t, f in
                                       ((.1, 1), (.25, -.8), (.4, .55), (.55, -.35), (.7, .18))]),
    "lift": lambda dy=3, deg=0: m(.6, SPRING, (.4, {"y": -dy, "r": deg})),
    "nudge": lambda x=3, y=0: m(.42, SPRING, (.35, {"x": x, "y": y})),
    "drop": lambda dy=3: m(.65, EASE, (.35, {"y": -dy}), (.7, {"y": dy})),
    "squash": lambda: m(.65, OUT, (.65, {}), (.78, {"sx": 1.08, "sy": .86})),
    "blink": lambda: m(.45, EASE, (.45, {"sy": .08}), (.55, {"sy": .08})),
    "draw": lambda: m(.5, EASE, (0, {"d": 0})),
    "fade": lambda: m(.4, EASE, (0, {"o": 0})),
    "fly": lambda x=16, y=-16: m(.8, EASE, (.45, {"x": x, "y": y, "o": 0}),
                                 (.46, {"x": -x, "y": -y, "o": 0})),
    "pulse": lambda: m(.8, EASE, (.25, {"o": .3}), (.5, {}), (.75, {"o": .3})),
    "twinkle": lambda: m(.6, OUT, (.35, {"s": 0, "r": 45}), (1, {"r": 90})),
    "beat": lambda: m(.7, OUT, (.15, {"s": 1.22}), (.3, {"s": .96}), (.45, {"s": 1.14})),
    "peel": lambda x=-4, y=-4: m(.55, SPRING, (0, {"x": x, "y": y, "o": .2})),
    "shake": lambda px=2: m(.45, EASE, *[(t, {"x": px * f}) for t, f in
                                        ((.15, -1), (.35, 1), (.55, -.6), (.75, .3))]),
    "combo": lambda: m(1.1, EASE, (.3, {"r": 120}), (.6, {"r": -60}), (.85, {"r": 30})),
    "grow": lambda: m(.5, SPRING, (0, {"s": 0, "o": 0})),
    "scan": lambda: m(.9, EASE, (.2, {"x": -2}), (.4, {"y": -2}), (.6, {"x": 2}), (.8, {"y": 1})),
    "scribble": lambda: m(.6, EASE, (.2, {"x": -1, "y": 1}), (.4, {"x": 1, "y": -.5}),
                          (.6, {"x": -.5, "y": 1}), (.8, {"x": 1})),
    "twist": lambda deg=-35: m(.7, SPRING, (.4, {"r": deg})),
    "flex": lambda sy=.78: m(.55, SPRING, (.4, {"sy": sy})),
    "flip": lambda: m(.7, SPRING, (.4, {"sy": -1})),
    "rise": lambda: m(.55, SPRING, (0, {"sy": 0})),
    "spinx": lambda: m(.8, EASE, (.5, {"sx": .12})),
    "slide": lambda x=0, y=0: m(.55, SPRING, (0, {"x": x, "y": y, "o": 0})),
}
POSE_DEFAULT = {"s": 1, "sx": 1, "sy": 1, "r": 0, "x": 0, "y": 0, "o": 1, "d": 1}


def parse_pose(text):
    out = {}
    for kv in (text or "").split():
        k, v = kv.split(":")
        assert k in POSE_DEFAULT, k
        out[k] = float(v)
    return out


def parse_click(text):
    tracks = []
    for item in (text or "").split():
        delay = 0.0
        if "@" in item:
            item, d = item.split("@")
            delay = float(d)
        name, _, args = item.partition(":")
        mo = MOTIONS[name](*[float(a) for a in args.split(",") if a])
        frames = mo["frames"]
        if not frames or frames[0][0] != 0:
            frames.insert(0, [0, {}])
        if frames[-1][0] != 1:
            frames.append([1, {}])
        tracks.append({**mo, "delay": delay, "name": name})
    return tracks


# ---------------------------------------------------------------- geometry
def arc_to_cubics(x1, y1, rx, ry, phi, fa, fs, x2, y2):
    if rx == 0 or ry == 0:
        return [(x1, y1, x2, y2, x2, y2)]
    phi = math.radians(phi)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    rx, ry = abs(rx), abs(ry)
    lam = x1p**2 / rx**2 + y1p**2 / ry**2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx**2 * ry**2 - rx**2 * y1p**2 - ry**2 * x1p**2
    den = rx**2 * y1p**2 + ry**2 * x1p**2
    co = math.sqrt(max(0, num / den)) * (-1 if fa == fs else 1)
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    n = max(1, math.ceil(abs(dt) / (math.pi / 2)))
    step = dt / n
    k = 4 / 3 * math.tan(step / 4)
    out = []
    for i in range(n):
        a1, a2 = t1 + i * step, t1 + (i + 1) * step
        p = lambda a: (cx + rx * math.cos(a) * cp - ry * math.sin(a) * sp,
                       cy + rx * math.cos(a) * sp + ry * math.sin(a) * cp)
        d = lambda a: (-rx * math.sin(a) * cp - ry * math.cos(a) * sp,
                       -rx * math.sin(a) * sp + ry * math.cos(a) * cp)
        (ax, ay), (bx, by) = p(a1), p(a2)
        (dax, day), (dbx, dby) = d(a1), d(a2)
        out.append((ax + k * dax, ay + k * day, bx - k * dbx, by - k * dby, bx, by))
    return out


def path_ops(d):
    """SVG path data -> flat list: 0 x y (move), 1 x y (line), 2 6xy (cubic), 3 (close)."""
    toks = re.findall(r"[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?", d)
    ops, i, cmd = [], 0, None
    x = y = sx = sy = 0.0
    lc = None  # last control point for S/T
    lq = None

    def num():
        nonlocal i
        v = float(toks[i]); i += 1
        return v

    while i < len(toks):
        if re.match(r"[A-Za-z]", toks[i]):
            cmd = toks[i]; i += 1
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = (x, y) if rel else (0, 0)
        if c == "M":
            x, y = num() + ox, num() + oy
            sx, sy = x, y
            ops += [0, x, y]
            cmd = "l" if rel else "L"
            lc = lq = None
        elif c == "L":
            x, y = num() + ox, num() + oy
            ops += [1, x, y]; lc = lq = None
        elif c == "H":
            x = num() + (x if rel else 0)
            ops += [1, x, y]; lc = lq = None
        elif c == "V":
            y = num() + (y if rel else 0)
            ops += [1, x, y]; lc = lq = None
        elif c in "CS":
            if c == "C":
                c1 = (num() + ox, num() + oy)
            else:
                c1 = (2 * x - lc[0], 2 * y - lc[1]) if lc else (x, y)
            c2 = (num() + ox, num() + oy)
            x, y = num() + ox, num() + oy
            ops += [2, *c1, *c2, x, y]; lc = c2; lq = None
        elif c in "QT":
            if c == "Q":
                q = (num() + ox, num() + oy)
            else:
                q = (2 * x - lq[0], 2 * y - lq[1]) if lq else (x, y)
            nx, ny = num() + ox, num() + oy
            ops += [2, x + 2 / 3 * (q[0] - x), y + 2 / 3 * (q[1] - y),
                    nx + 2 / 3 * (q[0] - nx), ny + 2 / 3 * (q[1] - ny), nx, ny]
            x, y = nx, ny; lq = q; lc = None
        elif c == "A":
            rx, ry, phi, fa, fs = num(), num(), num(), num(), num()
            nx, ny = num() + ox, num() + oy
            for cub in arc_to_cubics(x, y, rx, ry, phi, int(fa), int(fs), nx, ny):
                ops += [2, *cub]
            x, y = nx, ny; lc = lq = None
        elif c == "Z":
            ops += [3]; x, y = sx, sy; lc = lq = None
        else:
            raise ValueError(cmd)
    return ops


def element_d(el):
    tag = el.tag.replace(NS, "")
    a = lambda k, dflt=0: float(el.get(k, dflt))
    if tag == "path":
        return el.get("d")
    if tag == "line":
        return f"M{a('x1')} {a('y1')}L{a('x2')} {a('y2')}"
    if tag in ("polyline", "polygon"):
        pts = re.findall(r"-?[\d.]+", el.get("points"))
        d = "M" + " L".join(f"{pts[i]} {pts[i+1]}" for i in range(0, len(pts), 2))
        return d + ("Z" if tag == "polygon" else "")
    if tag in ("circle", "ellipse"):
        cx, cy = a("cx"), a("cy")
        rx = a("r") if tag == "circle" else a("rx")
        ry = a("r") if tag == "circle" else a("ry")
        return (f"M{cx - rx} {cy}A{rx} {ry} 0 1 0 {cx + rx} {cy}"
                f"A{rx} {ry} 0 1 0 {cx - rx} {cy}Z")
    if tag == "rect":
        x, y, w, h = a("x"), a("y"), a("width"), a("height")
        r = min(a("rx", el.get("ry", 0)), w / 2, h / 2)
        if not r:
            return f"M{x} {y}H{x+w}V{y+h}H{x}Z"
        return (f"M{x+r} {y}H{x+w-r}A{r} {r} 0 0 1 {x+w} {y+r}V{y+h-r}"
                f"A{r} {r} 0 0 1 {x+w-r} {y+h}H{x+r}A{r} {r} 0 0 1 {x} {y+h-r}"
                f"V{y+r}A{r} {r} 0 0 1 {x+r} {y}Z")
    raise ValueError(tag)


# ---------------------------------------------------------------- read
def load():
    tree = ET.parse(SRC)
    icons = []
    for sym in tree.getroot().iter(NS + "symbol"):
        parts, static = [], []
        for child in sym:
            if child.tag == NS + "g":
                parts.append({
                    "id": child.get("id"),
                    "origin": [float(v) for v in child.get("data-o", "12 12").split()],
                    "hover": parse_pose(child.get("data-hover")),
                    "click": parse_click(child.get("data-click")),
                    "els": list(child),
                })
            else:
                static.append(child)
        if static:
            parts.insert(0, {"id": "base", "origin": [12, 12], "hover": {}, "click": [], "els": static})
        icons.append({"id": sym.get("id"), "label": sym.get("data-label", sym.get("id")),
                      "group": sym.get("data-group", ""), "parts": parts})
    order = ["Products", "Navigation", "Actions", "Media", "Status", "Security",
             "Documents", "Communication", "System"]
    icons.sort(key=lambda i: order.index(i["group"]))
    ids = [i["id"] for i in icons]
    assert len(ids) == len(set(ids)), "duplicate icon ids"
    return icons


def is_fill(el):
    return el.get("fill") == "currentColor"


def el_markup(el, draw):
    tag = el.tag.replace(NS, "")
    attrs = {k: v for k, v in el.attrib.items()}
    if draw and not is_fill(el):
        attrs["pathLength"] = "1"
    s = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    return f"<{tag} {s}/>"


def has_draw(p):
    return any(t["name"] == "draw" for t in p["click"])


def svg_markup(icon, size=24):
    body = []
    for p in icon["parts"]:
        inner = "".join(el_markup(e, has_draw(p)) for e in p["els"])
        body.append(f'<g class="p-{p["id"]}">{inner}</g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}" '
            f'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round" class="si-{icon["id"]}">{"".join(body)}</svg>')


# ---------------------------------------------------------------- css
def css_transform(p):
    s = p.get("s", 1)
    t = []
    if p.get("x") or p.get("y"):
        t.append(f"translate({p.get('x', 0):g}px,{p.get('y', 0):g}px)")
    if p.get("r"):
        t.append(f"rotate({p['r']:g}deg)")
    sx, sy = s * p.get("sx", 1), s * p.get("sy", 1)
    if sx != 1 or sy != 1:
        t.append(f"scale({sx:g},{sy:g})")
    return " ".join(t) or "none"


def css_decl(p):
    out = [f"transform:{css_transform(p)}"]
    if "o" in p:
        out.append(f"opacity:{p['o']:g}")
    if "d" in p:
        out.append(f"stroke-dashoffset:{1 - p['d']:g}")
    return ";".join(out)


def build_css(icons):
    css = [
        "/* Generated by scripts/build-icons.py. Wrap an icon in .si, add .si-play to animate. */",
        ".si svg *{transform-box:view-box;transition:transform .3s cubic-bezier(.34,1.56,.64,1),opacity .3s}",
        ".si svg [pathLength]{stroke-dasharray:1;stroke-dashoffset:0}",
        "@media (prefers-reduced-motion:reduce){.si svg *{animation:none!important;transition:none!important}}",
    ]
    for ic in icons:
        for p in ic["parts"]:
            sel = f".si-{ic['id']} .p-{p['id']}"
            ox, oy = p["origin"]
            if p["hover"] or p["click"]:
                css.append(f"{sel}{{transform-origin:{ox:g}px {oy:g}px}}")
            if p["hover"]:
                css.append(f".si:hover {sel}{{{css_decl(p['hover'])}}}")
            anims = []
            for n, tr in enumerate(p["click"]):
                name = f"si-{ic['id']}-{p['id']}-{n}"
                ease = "cubic-bezier({:g},{:g},{:g},{:g})".format(*tr["ease"])
                frames = "".join(f"{t * 100:g}%{{{css_decl(pose)}}}" for t, pose in tr["frames"])
                css.append(f"@keyframes {name}{{{frames}}}")
                anims.append(f"{name} {tr['dur']:g}s {ease} {tr['delay']:g}s backwards")
            if anims:
                sel_draw = f"{sel} [pathLength]" if has_draw(p) else sel
                # draw animates the elements, everything else the group
                grp = [a for a, t in zip(anims, p["click"]) if t["name"] != "draw"]
                drw = [a for a, t in zip(anims, p["click"]) if t["name"] == "draw"]
                if grp:
                    css.append(f".si.si-play {sel}{{animation:{','.join(grp)}}}")
                if drw:
                    css.append(f".si.si-play {sel_draw}{{animation:{','.join(drw)}}}")
    return "\n".join(css) + "\n"


# ---------------------------------------------------------------- swift
def swift_pose(p):
    if not p:
        return ".identity"
    return "IconPose(" + ", ".join(f"{k}: {p[k]:g}" for k in POSE_DEFAULT if k in p) + ")"


def r(v):
    return f"{round(v, 3):g}"


def swift_case(name):
    return f"`{name}`" if name in {"repeat", "default", "import", "return", "case", "in"} else name


def build_swift(icons):
    camel = lambda s: re.sub(r"-(\w)", lambda mm: mm.group(1).upper(), s)
    lines = [
        "// swift-format-ignore-file", "// Generated by scripts/build-icons.py from Brand/Icons/icons.svg. Do not edit.",
        "import CoreGraphics", "",
        "/// The shared Symaira icon vocabulary: one case per meaning, drawn in-house",
        "/// on a 24 pt grid. See `Brand/Icons/README.md`.",
        "public enum SymairaIcon: String, CaseIterable, Sendable {",
    ]
    group = None
    for ic in icons:
        if ic["group"] != group:
            group = ic["group"]
            lines.append(f"    // MARK: {group}")
        lines.append(f"    case {swift_case(camel(ic['id']))} = \"{ic['id']}\"")
    lines += ["}", "", "extension SymairaIcon {",
              "    /// English source label; localize at the call site.",
              "    public var label: String {", "        switch self {"]
    for ic in icons:
        lines.append(f"        case .{swift_case(camel(ic['id']))}: \"{ic['label']}\"")
    lines += ["        }", "    }", "",
              "    var spec: [IconPart] {", "        switch self {"]
    for ic in icons:
        lines.append(f"        case .{swift_case(camel(ic['id']))}: [")
        for p in ic["parts"]:
            strokes = [path_ops(element_d(e)) for e in p["els"] if not is_fill(e)]
            fills = [path_ops(element_d(e)) for e in p["els"] if is_fill(e)]
            fmt = lambda arr: "[" + ", ".join("[" + ", ".join(r(v) for v in ops) + "]" for ops in arr) + "]"
            tracks = []
            for t in p["click"]:
                fr = ", ".join(f"({r(ti)}, {swift_pose(po)})" for ti, po in t["frames"])
                tracks.append(f"IconTrack(duration: {t['dur']:g}, delay: {t['delay']:g}, "
                              f"ease: ({', '.join(f'{e:g}' for e in t['ease'])}), "
                              f"draws: {'true' if t['name'] == 'draw' else 'false'}, frames: [{fr}])")
            lines.append(
                f"            IconPart(origin: CGPoint(x: {p['origin'][0]:g}, y: {p['origin'][1]:g}), "
                f"strokes: {fmt(strokes)}, fills: {fmt(fills)}, hover: {swift_pose(p['hover'])}, "
                f"click: [{', '.join(tracks)}]),")
        lines.append("        ]")
    lines += ["        }", "    }", "}", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- preview
def build_preview(icons, css):
    groups = {}
    for ic in icons:
        groups.setdefault(ic["group"], []).append(ic)
    body = []
    for g, items in groups.items():
        tiles = "".join(
            f'<button class="si tile" title="{ic["id"]}">{svg_markup(ic, 32)}<span>{ic["label"]}</span></button>'
            for ic in items)
        body.append(f"<h2>{g} <small>{len(items)}</small></h2><div class=grid>{tiles}</div>")
    animated = sum(1 for ic in icons if any(p["click"] for p in ic["parts"]))
    return f"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Symaira Icons</title>
<style>
:root{{--bg:#F4EEE5;--fg:#2A2219;--mut:#7A6A55;--gold:#9A7444;--card:#FFFDF9;--line:#2A22190F;--glow:#9A744422}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#110E0B;--fg:#F8E6CD;--mut:#9E8D76;--gold:#E5C397;--card:#1B1712;--line:#F8E6CD12;--glow:#E5C39718}}}}
:root[data-theme=dark]{{--bg:#110E0B;--fg:#F8E6CD;--mut:#9E8D76;--gold:#E5C397;--card:#1B1712;--line:#F8E6CD12;--glow:#E5C39718}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,system-ui,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:40px 16px 80px}} h1{{margin:0 0 6px;font-size:26px;font-weight:600}}
p{{color:var(--mut);margin:0 0 20px}} h2{{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);margin:32px 0 10px}} h2 small{{opacity:.6}}
.bar{{display:flex;gap:8px;flex-wrap:wrap}} .bar button{{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:999px;padding:7px 16px;font:inherit;cursor:pointer}}
.bar button[aria-pressed=true]{{border-color:var(--gold);color:var(--gold)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:10px}}
.tile{{all:unset;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:12px;padding:22px 6px 14px;border-radius:18px;background:var(--card);border:1px solid var(--line);transition:box-shadow .3s,border-color .3s}}
.tile:hover{{border-color:color-mix(in srgb,var(--gold) 35%,transparent);box-shadow:0 8px 28px var(--glow)}}
.tile:focus-visible{{outline:2px solid var(--gold);outline-offset:2px}}
.tile span{{font-size:12px;color:var(--mut);text-align:center}} .tile svg{{color:var(--gold);overflow:visible}}
body.light-ink .tile svg{{color:var(--fg)}}
body.small .tile svg{{width:20px;height:20px}}
{css}
</style><main>
<h1>Symaira Icons</h1>
<p>{len(icons)} icons, {animated} with part-level motion. Hover previews, click plays. Generated from Brand/Icons/icons.svg.</p>
<div class=bar><button id=all>Play all</button><button id=ink aria-pressed=false>Text colour</button><button id=sm aria-pressed=false>20 px</button></div>
{''.join(body)}</main>
<script>
const play=t=>{{t.classList.remove("si-play");void t.offsetWidth;t.classList.add("si-play")}};
document.querySelectorAll(".tile").forEach(t=>t.addEventListener("click",()=>play(t)));
all.onclick=()=>document.querySelectorAll(".tile").forEach((t,i)=>setTimeout(()=>play(t),i*40));
const tog=(b,c)=>b.onclick=()=>b.ariaPressed=document.body.classList.toggle(c);
tog(ink,"light-ink");tog(sm,"small");
</script></html>
"""


def main():
    icons = load()
    css = build_css(icons)
    (DIST / "svg").mkdir(parents=True, exist_ok=True)
    for old in (DIST / "svg").glob("*.svg"):
        old.unlink()
    for ic in icons:
        (DIST / "svg" / f"{ic['id']}.svg").write_text(svg_markup(ic) + "\n")
    (DIST / "symaira-icons.css").write_text(css)
    spec = {ic["id"]: {"label": ic["label"], "group": ic["group"], "parts": [
        {"id": p["id"], "origin": p["origin"], "hover": p["hover"],
         "click": [{k: t[k] for k in ("name", "dur", "delay", "ease", "frames")} for t in p["click"]]}
        for p in ic["parts"]]} for ic in icons}
    (DIST / "icons.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n")
    SWIFT.write_text(build_swift(icons))
    PREVIEW.write_text(build_preview(icons, css))
    print(f"{len(icons)} icons")


if __name__ == "__main__":
    main()
