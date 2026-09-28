#!/usr/bin/env python3
"""Generate and replay Go self-update filesystem observations against Rust."""

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
FIXTURE = ROOT / "testdata/rust-port/fixtures/update/apply.json"
ORACLE = ROOT / "scripts/rust-port/update-apply-oracle/main.go"
RUST_MANIFEST = ROOT / "rust/symaira-core-update/Cargo.toml"


def goos_name():
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("win"):
        return "windows"
    return platform.system().lower()


def observed():
    output = subprocess.check_output(
        ["go", "run", "./scripts/rust-port/update-apply-oracle"], cwd=ROOT
    )
    cases = json.loads(output)
    if len(cases) < 7:
        raise ValueError(f"apply oracle ran {len(cases)} cases, expected at least 7")
    go_source = b"\0".join(
        path.read_bytes()
        for path in (
            ROOT / "updatecheck/updateapply/updateapply.go",
            ROOT / "updatecheck/extract/extract.go",
        )
    )
    return {
        "go_source_sha256": hashlib.sha256(go_source).hexdigest(),
        "oracle_sha256": hashlib.sha256(ORACLE.read_bytes()).hexdigest(),
        "goos": goos_name(),
        "cases": cases,
    }


def replay(fixture):
    env = dict(os.environ, UPDATE_APPLY_FIXTURE=str(fixture))
    return subprocess.run(
        [
            "cargo",
            "test",
            "--manifest-path",
            str(RUST_MANIFEST),
            "--test",
            "apply",
            "--locked",
        ],
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
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args()
    current = observed()
    if args.write:
        args.fixture.parent.mkdir(parents=True, exist_ok=True)
        args.fixture.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"WROTE Go update apply fixture: {len(current['cases'])} cases")
        return 0

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    if fixture.get("goos") == current["goos"]:
        if fixture != current:
            raise ValueError("Go update apply oracle disagrees with committed fixture")
        print(f"PASS fresh Go oracle matches {len(current['cases'])} fixture cases")
        replay_path = args.fixture
    else:
        with tempfile.TemporaryDirectory(prefix="update-apply-platform-") as temp:
            replay_path = Path(temp) / "platform.json"
            replay_path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
            result = replay(replay_path)
        if result.returncode:
            raise RuntimeError(result.stdout)
        print(
            f"PASS Go/Rust update apply on {current['goos']} "
            f"(committed fixture recorded on {fixture.get('goos')})"
        )
        replay_path = None

    if replay_path is not None:
        result = replay(replay_path)
        if result.returncode:
            raise RuntimeError(result.stdout)
        print("PASS Rust apply replay")

    mutated = json.loads(json.dumps(current))
    case = next(row for row in mutated["cases"] if row["input"]["id"] == "install")
    case["observation"]["target_content"] = "mutated fixture"
    with tempfile.TemporaryDirectory(prefix="update-apply-negative-") as temp:
        path = Path(temp) / "mutated.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        negative = replay(path)
    if negative.returncode == 0:
        raise RuntimeError("mutated fixture was incorrectly accepted")
    blocked = next(row for row in mutated["cases"] if row["input"]["id"] == "blocked-parent")
    blocked["observation"]["stage_during_download"] = True
    with tempfile.TemporaryDirectory(prefix="update-apply-blocked-negative-") as temp:
        path = Path(temp) / "mutated.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        negative = replay(path)
    if negative.returncode == 0:
        raise RuntimeError("blocked-parent mutation was incorrectly accepted")
    print("PASS mutated-fixture negative control rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
