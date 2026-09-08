#!/usr/bin/env bash
# Reports which consumers of symaira-corekit (docs/consumers.json) are pinned
# behind the latest corekit release.
#
# Requires `gh` authenticated with read access to every listed consumer repo:
#   - Locally: your own `gh auth login` session, if you can read all of them.
#   - In CI: secrets.CONSUMER_READ_TOKEN (a fine-grained PAT with Contents:read
#     on every consumer repo) — see .github/workflows/consumer-pin-drift.yml
#     and AGENTS.md "Consumer Bump Ownership" for setup.
#
# Usage: scripts/check-consumer-pins.sh [--create-issue]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="$SCRIPT_DIR/../docs/consumers.json"
CREATE_ISSUE=false
[ "${1:-}" = "--create-issue" ] && CREATE_ISSUE=true

LATEST=$(gh release view --repo danieljustus/symaira-corekit --json tagName -q .tagName)
echo "Latest symaira-corekit release: $LATEST"
echo

# Go pseudo-versions are ordered by the base release version. A pseudo-version
# for the same base version is before that tagged release; one for a later base
# version is newer than the latest tagged release. Never compare these as raw
# strings: v0.17.1-0.<timestamp>-<hash> is newer than v0.17.0.
classify_pin() {
  python3 - "$1" "$LATEST" <<'PY'
import re
import sys

pin, latest = sys.argv[1:]
tag = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
pseudo = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-(?:0\.)?[0-9]{14}-[0-9a-f]{12}$")

latest_match = tag.fullmatch(latest)
pin_tag = tag.fullmatch(pin)
pin_pseudo = pseudo.fullmatch(pin)
if not latest_match or (not pin_tag and not pin_pseudo):
    print("invalid")
    raise SystemExit(0)
latest_version = tuple(int(part) for part in latest_match.groups())
if pin == latest:
    print("tagged-release")
    raise SystemExit(0)
if pin_pseudo:
    pin_version = tuple(int(part) for part in pin_pseudo.groups())
    print("pseudoversion-newer" if pin_version > latest_version else "pseudoversion-older")
else:
    pin_version = tuple(int(part) for part in pin_tag.groups())
    print("tagged-release-newer" if pin_version > latest_version else "older")
PY
}

drifted=()

while IFS=$'\t' read -r repo pin; do
  content=$(gh api "repos/$repo/contents/$pin" --jq '.content' 2>/dev/null | base64 -d 2>/dev/null || echo "")
  if [ -z "$content" ]; then
    echo "WARN  $repo:$pin — could not read (missing read access, or the file moved)"
    continue
  fi

  version=$(printf '%s\n' "$content" | grep -oE 'github\.com/danieljustus/symaira-corekit v[^[:space:]]+' | awk 'NR == 1 { print $2 }' || true)
  if [ -z "$version" ]; then
    echo "WARN  $repo:$pin — no symaira-corekit require line found"
    continue
  fi

  classification=$(classify_pin "$version")
  case "$classification" in
    tagged-release)
      echo "OK    $repo:$pin — $version (tagged-release)"
      ;;
    older|pseudoversion-older)
      echo "STALE $repo:$pin — $version ($classification than latest)"
      drifted+=("$repo:$pin@$version")
      ;;
    tagged-release-newer)
      echo "AHEAD $repo:$pin — $version ($classification)"
      ;;
    pseudoversion-newer)
      echo "OK    $repo:$pin — $version ($classification)"
      ;;
    *)
      echo "WARN  $repo:$pin — unsupported CoreKit version $version"
      ;;
  esac
done < <(jq -r '.consumers[] | .repo as $r | .pins[] | "\($r)\t\(.)"' "$MANIFEST")

if [ "$CREATE_ISSUE" = true ] && [ "${#drifted[@]}" -gt 0 ]; then
  body="Consumers pinned behind $LATEST as of $(date -u +%Y-%m-%d):"$'\n\n'
  for d in "${drifted[@]}"; do
    body="${body}- $d"$'\n'
  done
  body="${body}"$'\n'"Raised by the \`consumer-pin-drift\` workflow. See AGENTS.md \"Consumer Bump Ownership\" for who bumps and when."

  existing=$(gh issue list --repo danieljustus/symaira-corekit --search "Consumer pin drift in:title" --state open --json number -q '.[0].number' 2>/dev/null || true)
  if [ -n "$existing" ]; then
    gh issue comment "$existing" --repo danieljustus/symaira-corekit --body "$body"
    echo "Updated existing tracking issue #$existing"
  else
    gh issue create --repo danieljustus/symaira-corekit \
      --title "Consumer pin drift: $LATEST" \
      --body "$body" \
      --label "group: shared-libs" --label "cross-repo"
    echo "Opened a new tracking issue"
  fi
fi

if [ "${#drifted[@]}" -gt 0 ]; then
  exit 1
fi
