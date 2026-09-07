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

## Approved Icon Composer families

`AppIcon/SymairaAppKit/` is the canonical, complete approved family for this
library's brand identity. It vendors the unchanged Icon Composer package,
approved source inputs, the six macOS/iOS appearance exports, and
`exports/AppIcon.icns`. `icon-manifest.json` records the release manifest
checksums; `scripts/verify-approved-icon.py` is the CI guard for drift.

The approved high-contrast A3 artwork is the source of truth. Do not redraw,
recolor, or regenerate the artwork with the historical shell renderer. The
older shell files in `Brand/AppIcon/` remain available for historical assets,
but they are not inputs for new icon families.

To refresh the canonical family from the approved release directory, run:

```bash
python3 scripts/vendor-approved-icon.py \
  --release-root /path/to/symaira-icons-release
python3 scripts/verify-approved-icon.py
```

Keep all layered Icon Composer inputs and rendered outputs together. Consumers
that need a product icon should vendor the matching family into their own
repository rather than depending on a neighbouring AppKit checkout.

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
