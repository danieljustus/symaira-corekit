#!/bin/zsh
# Baut die native Demo als .app ohne Xcode-Projekt: swiftc + metallib.
set -euo pipefail
KIT="${0:A:h:h:h}"   # design/liquid-topography
OUT="${1:-$KIT/apple/Demo/build}"
APP="$OUT/Liquid Topography Demo.app"
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
xcrun -sdk macosx metal -c "$KIT/../../Sources/SymairaTheme/Resources/SymairaTopo.metal" -o "$OUT/topo.air"
xcrun -sdk macosx metallib "$OUT/topo.air" -o "$APP/Contents/Resources/default.metallib"
xcrun -sdk macosx swiftc -O -parse-as-library -swift-version 6 -target arm64-apple-macos26 \
  "$KIT/../../Sources/SymairaTheme/SymairaTokens.swift" "$KIT/../../Sources/SymairaTheme/SymairaTopoView.swift" "$KIT/apple/Demo/DemoApp.swift" \
  -o "$APP/Contents/MacOS/LiquidTopographyDemo"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>LiquidTopographyDemo</string>
<key>CFBundleIdentifier</key><string>com.symaira.design.topodemo</string>
<key>CFBundleName</key><string>Liquid Topography Demo</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSMinimumSystemVersion</key><string>26.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
codesign -s - --force "$APP" >/dev/null
echo "$APP"
