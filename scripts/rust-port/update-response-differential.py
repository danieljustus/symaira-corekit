#!/usr/bin/env python3
"""Check recorded Go Checker.Check response outcomes against the committed fixture."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "testdata/rust-port/fixtures/update/responses.json"
ORACLE = ROOT / "scripts/rust-port/update-response-oracle/main.go"
SOURCE = ROOT / "updatecheck/updatecheck.go"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="replace the fixture with fresh Go observations")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args()

    output = subprocess.run(
        ["go", "run", "./scripts/rust-port/update-response-oracle"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    cases = json.loads(output)
    if len(cases) != 9:
        raise ValueError(f"response oracle executed {len(cases)} cases, expected 9")
    observed = {
        "go_source_sha256": digest(SOURCE),
        "oracle_sha256": digest(ORACLE),
        "cases": cases,
    }
    if args.write:
        args.fixture.parent.mkdir(parents=True, exist_ok=True)
        args.fixture.write_text(json.dumps(observed, indent=2) + "\n", encoding="utf-8")
    elif observed != json.loads(args.fixture.read_text(encoding="utf-8")):
        raise ValueError("Go response oracle disagrees with committed fixture")
    print(f"PASS Go Checker.Check response oracle: {len(cases)} cases")


if __name__ == "__main__":
    main()
