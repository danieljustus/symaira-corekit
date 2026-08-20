# Symaira Brand Assets

This directory is the shared source for visual assets used by Symaira native
apps and disk images.

## Product logos

`ProductLogos/` is the canonical export set for the Symaira product family.
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

## App icons

Symaira app icons use one shared shell:

- warm-black instrument-panel canvas
- champagne-gold Symaira rim and orbital strokes
- a restrained technical grid
- one clear, tool-specific line glyph
- one semantic accent from the Symaira palette

The tool glyph remains in the owning tool repository. This keeps
`symaira-appkit` free of tool-specific product assets while still making the
shell, sizing, safe zones, and exports reproducible.

Render an icon with:

```bash
python3 scripts/render-app-icon.py \
  --glyph /path/to/app-icon-glyph.svg \
  --output /path/to/Assets.xcassets/AppIcon.appiconset \
  --master /path/to/assets/branding/app-icon.svg \
  --platforms macos,ios \
  --accent '#71D9F0'
```

Rendering requires macOS Quick Look (`qlmanage`) and ImageMagick (`magick`);
both are build-time tools only and are not linked into an app.

The glyph SVG must use a `0 0 512 512` view box. Use `currentColor` for its
primary stroke or fill and `#F7E0A8` for deliberate gold details.

Xcode projects consume the generated asset catalog directly. Manually
assembled bundles should vendor an `actool`-compiled `AppIcon.icns` next to the
sources and copy it during packaging; release builds must not depend on
`iconutil` converting PNGs at runtime.

## App names

User-facing names use `Symaira <Product>` with a space:

- `Symaira Hub`, `Symaira Terminal`, `Symaira Vault`, …
- `SymDesk` remains the deliberate product-name exception.

Internal target, scheme, executable, and bundle identifiers may retain their
stable technical names. Set `CFBundleDisplayName` and `CFBundleName` for the
user-facing standard rather than renaming executables.

## Disk images

`DMG/symaira-dmg-background.svg` is the canonical installer background.
`scripts/create-symaira-dmg.sh` creates the Finder layout with the app on the
left and `/Applications` on the right.

Release repositories vendor the script and background at a known revision.
That avoids a release-time dependency on a sibling checkout while keeping the
visual source and packaging behavior identical.
