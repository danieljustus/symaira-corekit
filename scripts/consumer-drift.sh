#!/usr/bin/env bash
# Lists the corekit version pinned by every sibling Symaira repo checked out
# next to this one, sorted oldest-pinned-first, so drift is visible at a
# glance. Read-only: does not modify any consumer repo.
set -euo pipefail

MODULE="github.com/danieljustus/symaira-corekit"
WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CUR_TAG="$(git -C "$(dirname "${BASH_SOURCE[0]}")/.." describe --tags --abbrev=0 2>/dev/null || echo "unknown")"

printf 'corekit HEAD: %s\n\n' "$CUR_TAG"

rows=()
found_any=0
for dir in "$WORKSPACE_ROOT"/symaira-*; do
	[ -d "$dir" ] || continue
	repo="$(basename "$dir")"
	[ "$repo" = "symaira-corekit" ] && continue
	gomod="$dir/go.mod"
	if [ ! -f "$gomod" ]; then
		rows+=("~0	$repo	no go.mod")
		continue
	fi
	pinned="$(grep -oE "${MODULE} v[0-9]+\.[0-9]+\.[0-9]+" "$gomod" | awk '{print $2}' || true)"
	if [ -z "$pinned" ]; then
		rows+=("~1	$repo	not a consumer")
		continue
	fi
	found_any=1
	rows+=("$pinned	$repo	$pinned")
done

if [ "$found_any" -eq 0 ]; then
	echo "no sibling consumer repos found next to $WORKSPACE_ROOT" >&2
	exit 1
fi

printf '%-28s %s\n' "REPO" "PINNED VERSION"
printf '%s\n' "${rows[@]}" | sort -t'	' -k1,1V | while IFS=$'\t' read -r _ repo version; do
	printf '%-28s %s\n' "$repo" "$version"
done
