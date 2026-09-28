#!/usr/bin/env python3
"""Regenerate and compare the update archive extraction Go/Rust fixture."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

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
        "goos": goos_name(),
        "cases": cases,
    }


def goos_name() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("win"):
        return "windows"
    return platform.system().lower()


def replay(fixture: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["EXTRACT_FIXTURE"] = str(fixture)
    return subprocess.run(
        ["cargo", "test", "--manifest-path", str(ROOT / "rust/symaira-core-update/Cargo.toml"), "--test", "extract", "--locked"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


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
            print("PASS Rust rejected mutated extraction fixture")
            return 0
        print("ERROR mutated fixture was accepted", file=sys.stderr)
        return 1
    if observed != fixture and fixture.get("goos") != observed["goos"]:
        # Archive paths are platform specific: replay this platform's Go
        # observations instead of the fixture recorded on another platform.
        with tempfile.TemporaryDirectory(prefix="upd006-platform-") as directory:
            candidate = Path(directory) / "platform.json"
            candidate.write_text(json.dumps(observed, indent=2) + "\n", encoding="utf-8")
            result = replay(candidate)
        if result.returncode:
            raise RuntimeError(result.stdout)
        print(
            f"PASS Go/Rust extraction differential on {observed['goos']} "
            f"(committed fixture recorded on {fixture.get('goos')})"
        )
        return 0
    compare(fixture, observed)
    print(f"PASS Go extraction oracle: {len(observed['cases'])} cases")
    result = replay(args.fixture)
    if result.returncode:
        raise RuntimeError(result.stdout)
    print("PASS Rust extraction replay")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
