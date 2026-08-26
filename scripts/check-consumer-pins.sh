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

drifted=()

while IFS=$'\t' read -r repo pin; do
  content=$(gh api "repos/$repo/contents/$pin" --jq '.content' 2>/dev/null | base64 -d 2>/dev/null || echo "")
  if [ -z "$content" ]; then
    echo "WARN  $repo:$pin — could not read (missing read access, or the file moved)"
    continue
  fi

  version=$(echo "$content" | grep -oE 'github\.com/danieljustus/symaira-corekit v[0-9]+\.[0-9]+\.[0-9]+' | head -1 | awk '{print $2}')
  if [ -z "$version" ]; then
    echo "WARN  $repo:$pin — no symaira-corekit require line found"
    continue
  fi

  if [ "$version" = "$LATEST" ]; then
    echo "OK    $repo:$pin — $version"
  else
    echo "STALE $repo:$pin — $version (latest: $LATEST)"
    drifted+=("$repo:$pin@$version")
  fi
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
