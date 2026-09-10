#!/usr/bin/env bash
# Lists Go pins from the canonical Symaira workspace and runs the exact
# Rust/Go consumer verifier against every record in docs/consumers.json.
# Read-only: no consumer checkout is modified.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKOUT="$(git -C "$SCRIPT_DIR/.." rev-parse --show-toplevel)"
COMMON_DIR="$(git -C "$CHECKOUT" rev-parse --path-format=absolute --git-common-dir)"
CANONICAL_CHECKOUT="$(dirname "$COMMON_DIR")"
WORKSPACE_ROOT="$(dirname "$CANONICAL_CHECKOUT")"
MODULE="github.com/danieljustus/symaira-corekit"

verify_status=0
python3 "$CHECKOUT/port/consumer/verify.py" \
  --released-consumers \
  --workspace-root "$WORKSPACE_ROOT" \
  --corekit-root "$CHECKOUT" || verify_status=$?

CUR_TAG="$(git -C "$CHECKOUT" describe --tags --abbrev=0 2>/dev/null || echo "unknown")"
printf 'corekit HEAD: %s\n\n' "$CUR_TAG"

rows=()
found_any=0
for dir in "$WORKSPACE_ROOT"/symaira-*; do
	[ -d "$dir" ] || continue
	repo="$(basename "$dir")"
	[ "$repo" = "symaira-corekit" ] && continue
	gomod="$dir/go.mod"
	if [ ! -f "$gomod" ]; then
		rows+=("~0"$'\t'"$repo"$'\t'"no go.mod")
		continue
	fi
	pinned="$(grep -oE "${MODULE} v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?" "$gomod" | awk '{print $2}' || true)"
	if [ -z "$pinned" ]; then
		rows+=("~1"$'\t'"$repo"$'\t'"not a consumer")
		continue
	fi
	found_any=1
	rows+=("$pinned"$'\t'"$repo"$'\t'"$pinned")
done

if [ "$found_any" -eq 0 ]; then
	echo "no sibling consumer repos found next to $WORKSPACE_ROOT" >&2
	exit 1
fi

printf '%-28s %s\n' "REPO" "PINNED VERSION"
printf '%s\n' "${rows[@]}" | sort -t$'\t' -k1,1V | while IFS=$'\t' read -r _ repo version; do
	printf '%-28s %s\n' "$repo" "$version"
done

[ "$verify_status" -eq 0 ] || exit "$verify_status"
