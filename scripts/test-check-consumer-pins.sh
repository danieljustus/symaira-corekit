#!/usr/bin/env bash
# Executable regression fixture for consumer pin version classification.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
# Keep classification vectors independent of the live consumer inventory.
# These are synthetic test records, not claims of current consumer adoption.
mkdir -p "$TMP/bin" "$TMP/fixture/scripts" "$TMP/fixture/docs"
cp "$ROOT/scripts/check-consumer-pins.sh" "$ROOT/scripts/parse-go-pin.py" "$TMP/fixture/scripts/"
python3 - "$TMP/fixture/docs/consumers.json" <<'FIXTURE'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps({"consumers": [
    {"repo": "example/" + name, "pins": ["go.mod"]}
    for name in ("current", "stale", "pseudo-newer", "ahead", "invalid")
]}), encoding="utf-8")
FIXTURE

cat >"$TMP/bin/gh" <<'FAKE_GH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"release view"* ]]; then
  printf '%s\n' 'v0.17.0'
  exit 0
fi
case "$*" in
  *example/current*) version='v0.17.0' ;;
  *example/stale*) version='v0.16.9-0.20260908091500-0123456789ab' ;;
  *example/pseudo-newer*) version='v0.17.1-0.20260908091500-0123456789ab' ;;
  *example/ahead*) version='v0.17.1' ;;
  *example/invalid*) version='v0.17.0-20260908091500-0123456789ab' ;;
  *) printf 'unexpected fake gh request: %s\n' "$*" >&2; exit 1 ;;
esac
printf 'module example.invalid/consumer\n\nrequire github.com/danieljustus/symaira-corekit %s\n' "$version" | base64 | tr -d '\n'
printf '\n'
FAKE_GH
chmod +x "$TMP/bin/gh"

set +e
output=$(PATH="$TMP/bin:$PATH" "$TMP/fixture/scripts/check-consumer-pins.sh" 2>&1)
status=$?
set -e

if [[ "$status" -ne 1 ]]; then
  printf 'expected stale-pin exit 1, got %s\n%s\n' "$status" "$output" >&2
  exit 1
fi
grep -F 'OK    example/current:go.mod — v0.17.0 (tagged-release)' <<<"$output" >/dev/null
grep -F 'STALE example/stale:go.mod — v0.16.9-0.20260908091500-0123456789ab (pseudoversion-older than latest)' <<<"$output" >/dev/null
grep -F 'OK    example/pseudo-newer:go.mod — v0.17.1-0.20260908091500-0123456789ab (pseudoversion-newer)' <<<"$output" >/dev/null
grep -F 'AHEAD example/ahead:go.mod — v0.17.1 (tagged-release-newer)' <<<"$output" >/dev/null
grep -F 'WARN  example/invalid:go.mod — unsupported CoreKit version v0.17.0-20260908091500-0123456789ab' <<<"$output" >/dev/null

parser="$ROOT/scripts/parse-go-pin.py"
[[ "$(printf '%s\n' '// require github.com/danieljustus/symaira-corekit v9.9.9' | python3 "$parser")" = missing ]]
[[ "$(printf '%s\n' 'require github.com/danieljustus/symaira-corekit' | python3 "$parser")" = invalid ]]
[[ "$(printf '%s\n' 'require github.com/danieljustus/symaira-corekit v0.17.0' 'require github.com/danieljustus/symaira-corekit v0.17.0' | python3 "$parser")" = duplicate ]]
[[ "$(printf '%s\n' 'require github.com/danieljustus/symaira-corekit v0.17.0' 'require github.com/danieljustus/symaira-corekit v0.18.0' | python3 "$parser")" = inconsistent ]]
printf '%s\n' 'consumer pin classification regression: ok'
