# Symaira Brand Assets

This directory is the shared source for visual assets used by Symaira native
apps and disk images.

## Marketing assets (current: Liquid Topography)

`Marketing/` is the current source and export set for README/GitHub social cards, OpenGraph
cards, transparent product lockups/wordmarks and the DMG background. It is rendered by one
deterministic generator from the current design system
([`design/liquid-topography/DESIGN.md`](../design/liquid-topography/DESIGN.md)): gray canvas
`#EEEDEA` / `#1C1C1B`, champagne `#E0D2BA` as the only accent, Google Sans Flex (original
bundled file, opsz 18) and the idle frame of the topography shader (`topo.json`, fixed frame).
Nothing is invented: no swirls, grids, extra colours, fake UI, metrics or version numbers.

```bash
uv run scripts/generate-marketing-assets.py      # renders Marketing/exports/** and Brand/DMG/**
uv run scripts/verify-marketing-assets.py        # hashes, sizes, alpha, DMG geometry, path safety
uv run scripts/verify-marketing-assets.py --determinism   # re-render AppKit, compare bytes
```

* `Marketing/identities.json` – public identities, factual one-line roles, formats.
* `Marketing/source/` – vendored inputs (512 px approved K1v2 icon renders + provenance, the
  plate-less Symaira S in light and dark for the provisional Scoop bucket). The generator reads
  nothing outside the repository; refresh icons with
  `scripts/vendor-marketing-icons.py --icons-root <dir>`.
* `Marketing/exports/<id>/` – `social-preview-{dark,light}.png` (1280×640),
  `og-{dark,light}.png` (1200×630), transparent `lockup-on-{light,dark}.png` and
  `wordmark-on-{light,dark}.png` (suffix = surface the ink is made for), and
  `product-logo.png` / `product-logo-on-dark.png` (1024×1024 transparent vertical lockup for
  `assets/branding/product-logo.png`). `fritz` and `router` additionally carry square,
  portrait, story and 16:9 release cards.
* `Marketing/manifest.json` – provenance (input hashes), roles, dimensions, output hashes and a
  `usage.vendoring` map (`target path in a product repo` → `file here`) for automated copying.

Icon rule: the approved K1v2 Icon Composer packages (2026-10-23) are **frozen** – never redraw,
recolour or re-interpret them. K1v2 is the two-part Symaira S in graphite relief with contour
lines and one champagne index line, plus the product glyph in champagne Liquid Glass in front.
Each package has three groups (glyph, contour lines, S); `actool` rejects more than four.
The Tinted appearance keeps the relief readable through fixed luminance steps. Marketing art
uses the approved renders of those packages on the neutral canvas and never rasterises glass
into transparent lockups beyond what the render contains.

Roles are labels, not claims: Brain agent context/control, Desktop document workspace, Vault
credential service, Cockpit Mac system control, EraseMe data-broker removal, Fritz FRITZ!Box
tools, AppKit Swift UI foundations, CoreKit shared backend foundations. Libraries,
distribution identities (Homebrew tap, Scoop bucket) and the website are not shown as native
apps. `router` is a separate family for the documented public-kit title *Symaira Router*; it
reuses the Fritz signet and never replaces *Symaira Fritz*. Brain's optional Browse/Operate/
Scope modules have no approved mark and therefore no card here (modules are not apps).
`scoop-bucket` is provisional: no approved Scoop icon exists, so it shows the plate-less S only.

## Product logos (legacy)

> **Superseded for new work** by `Marketing/` above. The files below predate Liquid Topography
> (Roboto Flex lockups, champagne-only ink) and stay untouched until each repository migrates.

`ProductLogos/` is the previous export set for the Symaira product family.
Every logo uses the unchanged Symaira S, a champagne/sand foreground, the
Roboto Flex word line, and a transparent canvas. The transparent canvas is
intentional: native apps add the platform-provided Liquid Glass background at
render time instead of baking a glass simulation into the artwork.

Each standalone product repository vendors its matching export as
`assets/branding/product-logo.png`. The vendored copy is the build and release
input, so no product depends on a neighbouring `symaira-appkit` checkout.
Use the canonical files for large product identity surfaces, About screens,
installer artwork, store artwork, and future app-icon catalogs. Do not shrink
the complete lockup into small toolbar or status icons; those surfaces keep
using purpose-built symbols.

## Approved Icon Composer families

`AppIcon/SymairaAppKit/` is the canonical, complete approved family for this
library's brand identity. It vendors the unchanged Icon Composer package,
approved source inputs, the six macOS/iOS appearance exports, and
`exports/AppIcon.icns`. `icon-manifest.json` records the release manifest
checksums; `scripts/verify-approved-icon.py` is the CI guard for drift.

The approved K1v2 Icon Composer package is the source of truth; it replaced the
A3 artwork on 2026-10-23. Do not redraw, recolor, or regenerate the artwork with
the historical shell renderer. The older shell files in `Brand/AppIcon/` and the
A3 inputs under `source/` remain available for historical assets, but they are
not inputs for new icon families.

To refresh the canonical family from the approved release directory, run:

```bash
python3 scripts/vendor-approved-icon.py \
  --release-root /path/to/symaira-icons-release
python3 scripts/verify-approved-icon.py
```

Keep all layered Icon Composer inputs and rendered outputs together. Consumers
that need a product icon should vendor the matching family into their own
repository rather than depending on a neighbouring AppKit checkout.

For a neutral-background refresh of historical A3 packages (two groups,
`S.png` + `signet.png`; it rejects K1v2), use `scripts/render-a3-icon.py --source
/path/to/AppIcon.icon --output /path/to/separate-review-directory`. It reads
`canvas` and `canvas-dark` from the current design contract, preserves both
foreground groups and their image bytes, renders all six macOS/iOS Default,
Dark and TintedDark variants, and creates checked ICNS/PNG fallbacks. Review
and vendor the results with their manifest; this does not install an app or
publish a release. The separate system Clear appearance is **not** verified
by these CLI renders and must not be inferred from Default.

## App names

User-facing names use `Symaira <Product>` with a space:

- `Symaira Brain`, `Symaira Desktop`, `Symaira Vault`, `Symaira Cockpit`, `Symaira EraseMe`.
- `symdesk` and `SymDesk*` remain technical identifiers; the display name is **Symaira Desktop**.

Internal target, scheme, executable, and bundle identifiers may retain their
stable technical names. Set `CFBundleDisplayName` and `CFBundleName` for the
user-facing standard rather than renaming executables.

## Disk images

`DMG/symaira-dmg-background.svg` is the canonical installer background (660 × 420; PNG
render plus `@2x`), generated by `scripts/generate-marketing-assets.py`: plain neutral gray
terrain from the topography shader, a subtle champagne arrow, no baked app icons or text.
The gray (`#767572`) is chosen so both Finder label colours – black in Light, white in Dark
mode – keep ≥ 4.4:1 contrast. `scripts/create-symaira-dmg.sh` creates the Finder layout with
the app on the left (≈ 180, 220) and `/Applications` on the right (≈ 480, 220); the layout
geometry is unchanged.

Release repositories vendor the script and background at a known revision.
That avoids a release-time dependency on a sibling checkout while keeping the
visual source and packaging behavior identical.
