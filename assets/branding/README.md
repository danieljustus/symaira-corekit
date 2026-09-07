# Symaira CoreKit brand assets

CoreKit is a shared Go library, not a GUI application. This directory vendors
CoreKit's approved brand-only Icon Composer family so documentation, release
artwork, and ecosystem references have a stable local asset without making any
consumer depend on an AppKit checkout.

`SymairaCoreKit/AppIcon.icon/` contains the unchanged layered Icon Composer
package. The matching six appearance exports and `exports/AppIcon.icns` remain
next to it. `icon-manifest.json` records the approved release checksums.

The high-contrast approved A3 artwork is authoritative. Do not redraw or
recolor these files. Run the repository guard after changing branding assets:

```bash
python3 scripts/verify-brand-assets.py
```

The existing `product-logo.png` is a separate transparent wordmark export and
is retained for compatibility; it is not replaced by the app-icon artwork.
