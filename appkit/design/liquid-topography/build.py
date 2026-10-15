#!/usr/bin/env python3
"""Erzeugt dist/ aus DESIGN.md + topo.json und prüft WCAG-Kontraste beider Modi.

Ausgaben:
  dist/tokens.css          CSS-Variablen, hell + dunkel (prefers-color-scheme und [data-theme])
  dist/tokens.json         flache Token-Liste für andere Tools
  dist/SymairaTokens.swift SwiftUI-Farben (adaptiv hell/dunkel), Radien, Abstände, Topo-Parameter
Exit 1, wenn ein Pflicht-Kontrast unter 4.5:1 fällt.
"""
import json, pathlib, re, sys
import yaml

ROOT = pathlib.Path(__file__).resolve().parent
DIST = ROOT / "dist"


def load():
    text = (ROOT / "DESIGN.md").read_text()
    front = re.match(r"^---\n(.*?)\n---\n", text, re.S).group(1)
    return yaml.safe_load(front), json.loads((ROOT / "topo.json").read_text())


def roles(colors):
    """Paare Rolle -> (hell, dunkel)."""
    out = {}
    for k, v in colors.items():
        if k.endswith("-dark"):
            continue
        out[k] = (v.upper(), colors.get(k + "-dark", v).upper())
    return out


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# Pflichtpaare: (Text, Hintergrund, Minimum). 3.0 = nicht-textuelle UI (WCAG 1.4.11)
CHECKS = [
    ("ink", "canvas", 4.5), ("ink-2", "canvas", 4.5), ("ink-3", "canvas", 4.5),
    ("ink", "surface", 4.5), ("ink-2", "surface", 4.5), ("ink-3", "surface", 4.5),
    ("ink-2", "sidebar", 4.5), ("ink-3", "sidebar", 4.5), ("ink", "selection", 4.5),
    ("ink-2", "raised", 4.5), ("on-primary", "primary", 4.5), ("ink", "primary-soft", 4.5),
    ("critical", "critical-soft", 4.5), ("critical", "surface", 4.5), ("positive", "surface", 4.5),
    ("on-critical", "critical", 4.5), ("on-selected", "selected", 4.5), ("warning", "surface", 4.5), ("warning", "canvas", 4.5),
    ("positive", "canvas", 4.5), ("critical", "canvas", 4.5), ("ink-3", "raised", 4.5),
    # nicht-textuelle Zustände (WCAG 1.4.11): Auswahl gegen Schiene und Karte, Fokus gegen Hintergrund
    ("selected", "raised", 3.0), ("selected", "surface", 3.0), ("focus", "canvas", 3.0), ("focus", "surface", 3.0),
]


def check(r):
    fails, rows = [], []
    for fg, bg, mn in CHECKS:
        for mode, i in (("hell", 0), ("dunkel", 1)):
            v = ratio(r[fg][i], r[bg][i])
            rows.append(f"{fg:>10} / {bg:<13} {mode:<6} {v:5.2f} (min {mn})")
            if v < mn:
                fails.append(rows[-1])
    return rows, fails


def kebab_to_camel(s):
    p = s.split("-")
    return p[0] + "".join(x.capitalize() for x in p[1:])


def css(d, r, topo):
    def block(i):
        return "\n".join(f"  --sym-{k}: {v[i]};" for k, v in r.items())
    lines = ["/* generiert von build.py aus DESIGN.md – nicht von Hand bearbeiten */",
             ":root {", block(0)]
    lines += [f"  --sym-radius-{k}: {v};" for k, v in d["rounded"].items()]
    lines += [f"  --sym-space-{k}: {v};" for k, v in d["spacing"].items()]
    lines += ['  --sym-font: "Google Sans Flex", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;',
              '  --sym-font-mono: ui-monospace, "SF Mono", Menlo, monospace;',
              "  --sym-icon-stroke: 2;",
              "  --sym-shadow-float: 0 1px 2px rgba(0,0,0,.05), 0 10px 28px rgba(0,0,0,.10);",
              "  color-scheme: light;", "}",
              "/* Feste optische Größe: automatisch wird kleine Schrift 5–8 % breiter. Jede font-Kurzschreibweise setzt",
              "   beides zurück und schlägt über Spezifität jede normale Regel. Daher bewusst !important (DESIGN.md › Typography). */",
              "body, body * { font-optical-sizing: none !important; font-variation-settings: 'opsz' 18 !important; }"]
    for k, t in d["typography"].items():
        lines.append(f".sym-type-{k} {{ font: {t['fontWeight']} {t['fontSize']}/{t['lineHeight']} "
                     f"{'var(--sym-font-mono)' if k == 'mono' else 'var(--sym-font)'};"
                     + (f" letter-spacing: {t['letterSpacing']};" if "letterSpacing" in t else "") + " }")
    dark = block(1) + "\n  color-scheme: dark;"
    lines += ["@media (prefers-color-scheme: dark) {", ":root:not([data-theme=\"light\"]) {", dark, "}", "}",
              ":root[data-theme=\"dark\"] {", dark, "}"]
    return "\n".join(lines) + "\n"


def swift(d, r, topo):
    def rgb(h):
        return ", ".join(f"{int(h[i:i + 2], 16) / 255:.4f}" for i in (1, 3, 5))
    out = ["// generiert von build.py aus DESIGN.md – nicht von Hand bearbeiten",
           "import SwiftUI", "", "#if canImport(AppKit)", "import AppKit", "#elseif canImport(UIKit)", "import UIKit", "#endif", "",
           "public enum SymairaTokens {",
           "    static func adaptive(_ l: (Double, Double, Double), _ d: (Double, Double, Double)) -> Color {",
           "        #if canImport(AppKit)",
           "        return Color(",
           "            nsColor: NSColor(name: nil) { a in",
           "                let c = a.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? d : l",
           "                return NSColor(srgbRed: c.0, green: c.1, blue: c.2, alpha: 1)",
           "            })",
           "        #else",
           "        return Color(",
           "            uiColor: UIColor { t in",
           "                let c = t.userInterfaceStyle == .dark ? d : l",
           "                return UIColor(red: c.0, green: c.1, blue: c.2, alpha: 1)",
           "            })",
           "        #endif", "    }", ""]
    for k, (l, dk) in r.items():
        out.append(f"    public static let {kebab_to_camel(k)} = adaptive(({rgb(l)}), ({rgb(dk)}))")
    out += ["", "    public enum Radius {"]
    out += [f"        public static let {k}: CGFloat = {float(v[:-2])}" for k, v in d["rounded"].items()]
    out += ["    }", "    public enum Space {"]
    out += [f"        public static let {k}: CGFloat = {float(v[:-2])}" for k, v in d["spacing"].items()]
    out += ["    }", "    public static let iconWeight: Font.Weight = .semibold", "",
            "    /// Parameter der Hochebene, 1:1 aus topo.json", "    public enum Topo {"]
    for k in ("levels", "scale", "lineAlpha", "indexAlpha", "bandAlpha", "maxAlpha", "basinOpen", "lightModeFactor", "transitionSeconds"):
        out.append(f"        public static let {k}: Double = {float(topo[k])}")
    out.append(f"        public static let fps: Double = {float(topo['fps']['apple'])}")
    out.append(f"        public static let maxProtectedRects = {topo['maxProtectedRects']}")
    out.append(f"        public static let pointerRadius: Double = {float(topo['pointer']['radius'])}")
    out.append(f"        public static let pointerStrength: Double = {float(topo['pointer']['strength'])}")
    for k in ("pressDepth", "pressSeconds", "dragRippleEvery", "clickRipple"):
        out.append(f"        public static let {k}: Double = {float(topo['pointer'][k])}")
    for k in ("moveThreshold", "rippleThrottleSeconds", "edgeRipple"):
        out.append(f"        public static let layout{k[0].upper()+k[1:]}: Double = {float(topo['layout'][k])}")
    out += ["    }", "}", ""]
    return "\n".join(out)


def main():
    d, topo = load()
    r = roles(d["colors"])
    rows, fails = check(r)
    DIST.mkdir(exist_ok=True)
    (DIST / "tokens.css").write_text(css(d, r, topo))
    (DIST / "SymairaTokens.swift").write_text(swift(d, r, topo))
    # AppKit-Modul: generierte Tokens direkt ins SymairaTheme-Target
    (ROOT.parent.parent / "Sources/SymairaTheme/SymairaTokens.swift").write_text(swift(d, r, topo))
    (DIST / "tokens.json").write_text(json.dumps({
        "colors": {k: {"light": v[0], "dark": v[1]} for k, v in r.items()},
        "rounded": d["rounded"], "spacing": d["spacing"], "typography": d["typography"], "topo": topo},
        indent=2, ensure_ascii=False) + "\n")
    (DIST / "contrast-report.txt").write_text("\n".join(rows) + "\n")
    print(f"{len(r)} Farbrollen, {len(rows)} Kontrastprüfungen, {len(fails)} Verstöße")
    for f in fails:
        print("FAIL", f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
