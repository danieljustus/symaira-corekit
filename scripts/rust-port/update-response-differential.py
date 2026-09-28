#!/usr/bin/env python3
"""Check recorded Go Checker.Check response outcomes against the committed fixture."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "testdata/rust-port/fixtures/update/responses.json"
ORACLE = ROOT / "scripts/rust-port/update-response-oracle/main.go"
SOURCE = ROOT / "updatecheck/updatecheck.go"


def replay(fixture: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["RESPONSE_FIXTURE"] = str(fixture)
    return subprocess.run(
        ["cargo", "test", "--manifest-path", str(ROOT / "rust/symaira-core-update/Cargo.toml"), "--test", "response", "--locked"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="replace the fixture with fresh Go observations")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--negative-control", action="store_true", help="prove a mutated fixture is rejected")
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
    committed = json.loads(args.fixture.read_text(encoding="utf-8"))
    if args.negative_control:
        mutated = json.loads(json.dumps(committed))
        mutated["cases"][0]["result"] = json.loads('{"code": "mutated-response"}')
        with tempfile.TemporaryDirectory(prefix="upd002-negative-") as directory:
            candidate = Path(directory) / "mutated.json"
            candidate.write_text(json.dumps(mutated, indent=2) + "\n", encoding="utf-8")
            result = replay(candidate)
        if result.returncode == 0:
            raise ValueError("mutated response fixture unexpectedly passed")
        print("PASS Rust rejected mutated response fixture")
        return
    if observed != committed:
        raise ValueError("Go response oracle disagrees with committed fixture")
    result = replay(args.fixture)
    if result.returncode:
        raise RuntimeError(result.stdout)
    print(f"PASS Go Checker.Check response oracle: {len(cases)} cases and Rust replay")


if __name__ == "__main__":
    main()
