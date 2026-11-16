#!/usr/bin/env bash
# Runs the exact Rust/Go consumer verifier against every record in
# docs/consumers.json, then lists every CoreKit pin of the sibling checkouts.
# Read-only: no consumer checkout is modified.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKOUT="$(git -C "$SCRIPT_DIR/.." rev-parse --show-toplevel)"
COMMON_DIR="$(git -C "$CHECKOUT" rev-parse --path-format=absolute --git-common-dir)"
CANONICAL_CHECKOUT="$(dirname "$COMMON_DIR")"
WORKSPACE_ROOT="$(dirname "$CANONICAL_CHECKOUT")"

verify_status=0
python3 "$CHECKOUT/port/consumer/verify.py" \
  --released-consumers \
  --workspace-root "$WORKSPACE_ROOT" \
  --corekit-root "$CHECKOUT" || verify_status=$?

# Every CoreKit pin (Cargo rev/tag, SwiftPM, XcodeGen, Xcode, Go) of each
# sibling checkout, resolved against the local CoreKit release tags.
python3 "$CHECKOUT/port/consumer/drift.py" \
  --workspace-root "$WORKSPACE_ROOT" \
  --corekit-root "$CHECKOUT"

[ "$verify_status" -eq 0 ] || exit "$verify_status"
