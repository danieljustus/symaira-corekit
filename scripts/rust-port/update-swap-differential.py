#!/usr/bin/env python3
"""Compare the unexported Go atomic swap to the Rust filesystem operation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "testdata/rust-port/fixtures/update/swap.json"
ORACLE = ROOT / "updatecheck/updateapply/atomic_swap_oracle_test.go"
GO_SOURCE = ROOT / "updatecheck/updateapply/updateapply.go"
RUST_MANIFEST = ROOT / "rust/symaira-core-update/Cargo.toml"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture(output):
    env = dict(os.environ, COREKIT_SWAP_ORACLE_OUT=str(output))
    env.setdefault("GOTOOLCHAIN", "go1.26.6")
    env["CGO_ENABLED"] = "0"
    subprocess.run(
        ["go", "test", "-count=1", "-run", "^TestAtomicSwapOracle$", "./updatecheck/updateapply"],
        cwd=ROOT, env=env, check=True, capture_output=True, text=True,
    )
    cases = json.loads(output.read_text(encoding="utf-8"))
    ids = [case["input"]["id"] for case in cases]
    expected = {"missing-source", "validation-rollback", "validation-first-install", "preexisting-backup"}
    if len(ids) != len(expected) or set(ids) != expected:
        raise ValueError(f"Go swap oracle case mismatch: {ids}")
    return {
        "goos": "darwin" if sys.platform == "darwin" else "windows" if sys.platform == "win32" else "linux",
        "go_source_sha256": digest(GO_SOURCE),
        "oracle_sha256": digest(ORACLE),
        "runner_sha256": digest(Path(__file__)),
        "cases": cases,
    }


def replay(fixture):
    env = dict(os.environ, UPDATE_SWAP_FIXTURE=str(fixture))
    result = subprocess.run(
        ["cargo", "test", "--manifest-path", str(RUST_MANIFEST), "-p", "symaira-core-update", "--test", "swap", "--locked"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="update-swap-", dir=os.environ.get("TMPDIR")) as temp:
        path = Path(temp) / "go.json"
        current = capture(path)
        if args.write:
            FIXTURE.parent.mkdir(parents=True, exist_ok=True)
            FIXTURE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"WROTE Go atomic-swap fixture: {len(current['cases'])} cases")
            return 0
        committed = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for field in ("go_source_sha256", "oracle_sha256", "runner_sha256"):
            if committed[field] != current[field]:
                raise ValueError(f"swap fixture source drift: {field}")
        if committed["goos"] == current["goos"] and committed != current:
            raise ValueError("Go atomic-swap oracle disagrees with committed fixture")
        replay_path = Path(temp) / "replay.json"
        replay_path.write_text(json.dumps(current), encoding="utf-8")
        positive = replay(replay_path)
        if positive.returncode or "test result: ok. 1 passed;" not in positive.stdout:
            raise RuntimeError(f"Rust swap replay failed or ran zero tests:\n{positive.stdout}\n{positive.stderr}")
        mutated = json.loads(json.dumps(current))
        missing = next(case for case in mutated["cases"] if case["input"]["id"] == "missing-source")
        missing["observation"]["target_content"] = "corrupted fixture"
        replay_path.write_text(json.dumps(mutated), encoding="utf-8")
        negative = replay(replay_path)
        if negative.returncode == 0:
            raise RuntimeError("Rust swap replay accepted mutated Go observation")
    print(f"PASS Go/Rust atomic swap: {len(current['cases'])} cases, {current['goos']}; mutation rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
