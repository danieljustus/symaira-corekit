#!/usr/bin/env python3
"""Record Go update-cache behavior and replay it in the Rust crate."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "testdata/rust-port/fixtures/update/cache.json"
ORACLE = ROOT / "scripts/rust-port/update-cache-oracle/main.go"
SOURCE = ROOT / "updatecheck/updatecheck.go"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observe_go():
    output = subprocess.run(
        ["go", "run", "./scripts/rust-port/update-cache-oracle"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout
    observed = json.loads(output)
    if len(observed["cases"]) != 7:
        raise ValueError("cache oracle did not execute all 7 observations")
    return {
        "go_source_sha256": digest(SOURCE),
        "oracle_sha256": digest(ORACLE),
        **observed,
    }


def compare(observed, fixture_path):
    return observed == json.loads(fixture_path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="regenerate fixture from public Go API")
    mode.add_argument("--negative-control", action="store_true", help="prove a mutated fixture is rejected")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args()
    observed = observe_go()
    if args.write:
        args.fixture.parent.mkdir(parents=True, exist_ok=True)
        args.fixture.write_text(json.dumps(observed, indent=2) + "\n", encoding="utf-8")
        print(f"PASS wrote {len(observed['cases'])} Go cache observations")
        return
    if args.negative_control:
        mutated = copy.deepcopy(observed)
        mutated["cases"][0]["requests"] += 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutated.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            if compare(observed, path):
                raise SystemExit("FAIL mutated fixture was accepted")
        print("PASS mutated fixture rejected")
        return
    if not compare(observed, args.fixture):
        raise SystemExit("FAIL Go cache oracle disagrees with committed fixture")
    subprocess.run(
        ["cargo", "test", "-p", "symaira-core-update", "--test", "cache", "--locked"],
        cwd=ROOT, check=True,
    )
    print(f"PASS Go/Rust update-cache differential: {len(observed['cases'])} observations")


if __name__ == "__main__":
    main()
