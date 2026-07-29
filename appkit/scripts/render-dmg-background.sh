#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="${SCRIPT_DIR}/../Brand/DMG/symaira-dmg-background.svg"
OUTPUT="${1:-${SCRIPT_DIR}/../Brand/DMG/symaira-dmg-background.png}"
FONT="/System/Library/Fonts/SFNS.ttf"

if ! command -v magick >/dev/null 2>&1; then
  echo "error: ImageMagick 'magick' is required" >&2
  exit 2
fi
if [ ! -f "$FONT" ]; then
  FONT="/System/Library/Fonts/Helvetica.ttc"
fi

mkdir -p "$(dirname "$OUTPUT")"
magick \
  -background none "$SOURCE" \
  -resize 660x420 \
  -font "$FONT" \
  -gravity north \
  -fill '#F8EFD9' -pointsize 24 -annotate +0+40 'Install for macOS' \
  -fill '#B8B2A6' -pointsize 13 -annotate +0+76 'Drag the app into Applications' \
  -gravity northwest \
  -fill '#D1CABD' -pointsize 13 -annotate +165+330 'APP' \
  -fill '#D1CABD' -pointsize 13 -annotate +430+330 'APPLICATIONS' \
  -gravity south \
  -fill '#766F64' -pointsize 10 -annotate +0+19 'S Y M A I R A   ·   L O C A L - F I R S T   T O O L S' \
  -strip \
  "$OUTPUT"
