"""Fail-closed merge gate over every pull-request job in the CI workflow.

The `merge-gate` job needs every PR-relevant CI job and runs with `always()`.
It passes only when the scope selector succeeded, every unconditional job
succeeded, and every full-scope job succeeded (full scope) or was skipped
(docs-only scope). A failed, cancelled, missing or unexpectedly skipped job
fails the gate, so one required context covers the whole native matrix.
"""
import json
import os
import sys

# Jobs that run on every pull request regardless of the selected scope.
ALWAYS = frozenset({"changes", "test", "lint", "govulncheck", "apidiff"})


def evaluate(needs, full):
    """Return a list of human-readable violations; empty means pass."""
    if full not in ("true", "false"):
        return [f"scope selector returned {full!r}, expected 'true' or 'false'"]
    problems = []
    missing = sorted(ALWAYS - needs.keys())
    if missing:
        problems.append(f"gate does not depend on required jobs: {', '.join(missing)}")
    for job, info in sorted(needs.items()):
        result = info.get("result") if isinstance(info, dict) else None
        expected = "success" if job in ALWAYS or full == "true" else "skipped"
        if result != expected:
            problems.append(f"{job}: result {result!r}, expected {expected!r}")
    return problems


def main():
    try:
        needs = json.loads(os.environ["NEEDS_JSON"])
    except (KeyError, json.JSONDecodeError) as error:
        print(f"merge gate: unreadable job results: {error}", file=sys.stderr)
        return 1
    if not isinstance(needs, dict) or not needs:
        print("merge gate: no job results", file=sys.stderr)
        return 1
    full = os.environ.get("CI_FULL_SCOPE", "")
    problems = evaluate(needs, full)
    for problem in problems:
        print(f"merge gate: {problem}", file=sys.stderr)
    if problems:
        return 1
    print(f"merge gate: {len(needs)} jobs satisfied (full scope: {full})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
