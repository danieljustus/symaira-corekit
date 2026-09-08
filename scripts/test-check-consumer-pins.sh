#!/usr/bin/env bash
# Executable regression fixture for consumer pin version classification.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"

cat >"$TMP/bin/gh" <<'FAKE_GH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"release view"* ]]; then
  printf '%s\n' 'v0.17.0'
  exit 0
fi
case "$*" in
  *symaira-brain*) version='v0.17.0' ;;
  *symaira-browse*) version='v0.16.9-0.20260908091500-0123456789ab' ;;
  *symaira-desktop*) version='v0.17.1-0.20260908091500-0123456789ab' ;;
  *symaira-eraseme*) version='v0.17.1' ;;
  *symaira-vault*) version='v0.17.0-20260908091500-0123456789ab' ;;
  *) printf 'unexpected fake gh request: %s\n' "$*" >&2; exit 1 ;;
esac
printf 'module example.invalid/consumer\n\nrequire github.com/danieljustus/symaira-corekit %s\n' "$version" | base64 | tr -d '\n'
printf '\n'
FAKE_GH
chmod +x "$TMP/bin/gh"

set +e
output=$(PATH="$TMP/bin:$PATH" "$ROOT/scripts/check-consumer-pins.sh" 2>&1)
status=$?
set -e

[[ "$status" -eq 1 ]]
grep -F 'OK    danieljustus/symaira-brain:go.mod — v0.17.0 (tagged-release)' <<<"$output" >/dev/null
grep -F 'STALE danieljustus/symaira-browse:go.mod — v0.16.9-0.20260908091500-0123456789ab (pseudoversion-older than latest)' <<<"$output" >/dev/null
grep -F 'OK    danieljustus/symaira-desktop:go.mod — v0.17.1-0.20260908091500-0123456789ab (pseudoversion-newer)' <<<"$output" >/dev/null
grep -F 'AHEAD danieljustus/symaira-eraseme:go.mod — v0.17.1 (tagged-release-newer)' <<<"$output" >/dev/null
grep -F 'WARN  danieljustus/symaira-vault:go.mod — unsupported CoreKit version v0.17.0-20260908091500-0123456789ab' <<<"$output" >/dev/null
printf '%s\n' 'consumer pin classification regression: ok'
