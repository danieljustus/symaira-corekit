#!/usr/bin/env python3
"""Check the committed stable-version observations against the live Go API."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "testdata/rust-port/fixtures/update/stable-versions.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args()
    output = subprocess.check_output(
        ["go", "run", "./scripts/rust-port/update-oracle"],
        cwd=ROOT,
    )
    cases = json.loads(output)
    if len(cases) != 30:
        raise ValueError("stable-version oracle did not execute all 30 cases")
    observed = {
        "go_source_sha256": hashlib.sha256((ROOT / "updatecheck/updatecheck.go").read_bytes()).hexdigest(),
        "oracle_sha256": hashlib.sha256((ROOT / "scripts/rust-port/update-oracle/main.go").read_bytes()).hexdigest(),
        "cases": cases,
    }
    if args.write:
        args.fixture.parent.mkdir(parents=True, exist_ok=True)
        args.fixture.write_text(json.dumps(observed, indent=2) + "\n", encoding="utf-8")
    elif observed != json.loads(args.fixture.read_text(encoding="utf-8")):
        raise ValueError("stable-version Go oracle disagrees with committed fixture")
    print(f"PASS Go stable-version oracle: {len(cases)} cases")


if __name__ == "__main__":
    main()
