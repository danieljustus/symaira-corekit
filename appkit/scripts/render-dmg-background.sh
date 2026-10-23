#!/bin/bash
# Renders Brand/DMG/symaira-dmg-background.{svg,png,@2x.png} with the Liquid Topography generator.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run "${SCRIPT_DIR}/generate-marketing-assets.py" --dmg-only
