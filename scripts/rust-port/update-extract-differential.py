#!/usr/bin/env python3
"""Regenerate and compare the update archive extraction Go/Rust fixture."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "testdata/rust-port/fixtures/update/extract.json"
ORACLE = ROOT / "scripts/rust-port/update-extract-oracle/main.go"
GO_SOURCE = ROOT / "updatecheck/extract/extract.go"


def live_observation():
    output = subprocess.check_output(
        ["go", "run", "./scripts/rust-port/update-extract-oracle"], cwd=ROOT
    )
    cases = json.loads(output)
    if len(cases) != 12:
        raise ValueError(f"extract oracle ran {len(cases)} cases, expected 12")
    return {
        "go_source_sha256": hashlib.sha256(GO_SOURCE.read_bytes()).hexdigest(),
        "oracle_sha256": hashlib.sha256(ORACLE.read_bytes()).hexdigest(),
        "cases": cases,
    }


def compare(expected, observed):
    if expected != observed:
        raise ValueError("Go archive extraction observations disagree with fixture")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--negative-control", action="store_true")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args()
    observed = live_observation()
    if args.write:
        args.fixture.parent.mkdir(parents=True, exist_ok=True)
        args.fixture.write_text(json.dumps(observed, indent=2) + "\n", encoding="utf-8")
        print(f"WROTE Go extraction fixture: {len(observed['cases'])} cases")
        return 0
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    if args.negative_control:
        mutated = json.loads(json.dumps(fixture))
        mutated["cases"][0]["files"][0]["content"] = "mutated"
        try:
            compare(mutated, observed)
        except ValueError:
            print("REJECTED mutated fixture as required")
            return 1
        print("ERROR mutated fixture was accepted", file=sys.stderr)
        return 0
    compare(fixture, observed)
    print(f"PASS Go extraction oracle: {len(observed['cases'])} cases")
    subprocess.run(
        ["cargo", "test", "--manifest-path", str(ROOT / "rust/symaira-core-update/Cargo.toml"), "--test", "extract", "--locked"],
        cwd=ROOT,
        check=True,
    )
    print("PASS Rust extraction replay")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
