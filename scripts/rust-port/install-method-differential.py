#!/usr/bin/env python3
"""Generate UPD-008 observations from Go and replay them in Rust."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "testdata/rust-port/fixtures/update/install-methods.json"


def oracle():
    with tempfile.TemporaryDirectory(prefix="upd008-go-cache-") as cache:
        env = os.environ.copy()
        env.setdefault("GOCACHE", cache)
        output = subprocess.check_output(
            ["go", "run", "./scripts/rust-port/install-method-oracle"],
            cwd=ROOT,
            env=env,
        )
    result = json.loads(output)
    if len(result.get("cases", [])) != 15:
        raise ValueError("install-method oracle did not execute all 15 cases")
    return result


def replay(fixture):
    env = os.environ.copy()
    env["INSTALL_METHOD_FIXTURE"] = str(fixture)
    return subprocess.run(
        ["cargo", "test", "-p", "symaira-core-update", "--test", "install_method", "--locked"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--negative-control", action="store_true")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args()
    observed = oracle()

    if args.write:
        args.fixture.parent.mkdir(parents=True, exist_ok=True)
        args.fixture.write_text(json.dumps(observed, indent=2) + "\n", encoding="utf-8")
        print(f"PASS Go install-method oracle: {len(observed['cases'])} cases written")
        return

    committed = json.loads(args.fixture.read_text(encoding="utf-8"))
    if observed != committed:
        raise ValueError("install-method Go oracle disagrees with committed fixture")
    if args.negative_control:
        mutated = json.loads(json.dumps(committed))
        mutated["cases"][0]["method"] = "mutated-fixture"
        with tempfile.TemporaryDirectory(prefix="upd008-negative-") as directory:
            candidate = Path(directory) / "mutated.json"
            candidate.write_text(json.dumps(mutated), encoding="utf-8")
            result = replay(candidate)
        if result.returncode == 0:
            raise ValueError("mutated-fixture negative control unexpectedly passed")
        print("PASS Rust rejected mutated install-method fixture")
        return

    result = replay(args.fixture)
    if result.returncode:
        raise RuntimeError(result.stdout)
    print(f"PASS Go/Rust install-method differential: {len(observed['cases'])} cases")


if __name__ == "__main__":
    main()
