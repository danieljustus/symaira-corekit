#!/bin/zsh
# Baut die iOS-Demo für den Simulator (arm64) ohne Xcode-Projekt.
set -euo pipefail
KIT="${0:A:h:h:h}"   # design/liquid-topography
SRC="$KIT/../../Sources/SymairaTheme"
OUT="${1:-$KIT/apple/Demo/build}"
APP="$OUT/LiquidTopographyiOS.app"
SDK="$(xcrun --sdk iphonesimulator --show-sdk-path)"
rm -rf "$APP"; mkdir -p "$APP"
xcrun -sdk iphonesimulator metal -target air64-apple-ios26.0-simulator -c "$SRC/Resources/SymairaTopo.metal" -o "$OUT/topo-ios.air"
xcrun -sdk iphonesimulator metallib "$OUT/topo-ios.air" -o "$APP/default.metallib"
xcrun -sdk iphonesimulator swiftc -O -parse-as-library -swift-version 6 -target arm64-apple-ios26.0-simulator -sdk "$SDK" \
  "$SRC/SymairaTokens.swift" "$SRC/SymairaTopoView.swift" "$KIT/apple/Demo/iOSDemoApp.swift" \
  -o "$APP/LiquidTopographyiOS"
cat > "$APP/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>LiquidTopographyiOS</string>
<key>CFBundleIdentifier</key><string>com.symaira.design.topodemo.ios</string>
<key>CFBundleName</key><string>Topography</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>MinimumOSVersion</key><string>26.0</string>
<key>UIDeviceFamily</key><array><integer>1</integer></array>
<key>UILaunchScreen</key><dict/>
<key>UIApplicationSceneManifest</key><dict><key>UIApplicationSupportsMultipleScenes</key><false/></dict>
</dict></plist>
PLIST
codesign -s - --force "$APP" >/dev/null
echo "$APP"
