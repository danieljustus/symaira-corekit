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
    env = dict(os.environ, GOTOOLCHAIN="go1.26.6", CGO_ENABLED="0")
    output = subprocess.check_output(
        ["go", "run", "./scripts/rust-port/update-apply-oracle"], cwd=ROOT, env=env
    )
    cases = json.loads(output)
    if len(cases) != 17:
        raise ValueError(f"apply oracle ran {len(cases)} cases, expected 17")
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

def production_replay(fixture):
    env = dict(os.environ, UPDATE_APPLY_FIXTURE=str(fixture))
    return subprocess.run(
        ["cargo", "test", "--manifest-path", str(RUST_MANIFEST),
         "--test", "applier", "--locked"],
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
            production = production_replay(replay_path)
        if result.returncode or "test result: ok. 1 passed;" not in result.stdout:
            raise RuntimeError(result.stdout)
        if production.returncode or "test result: ok. 1 passed;" not in production.stdout:
            raise RuntimeError(production.stdout)
        print(
            f"PASS Go/Rust update apply on {current['goos']} "
            f"(committed fixture recorded on {fixture.get('goos')})"
        )
        replay_path = None

    if replay_path is not None:
        result = replay(replay_path)
        if result.returncode or "test result: ok. 1 passed;" not in result.stdout:
            raise RuntimeError(result.stdout)
        production = production_replay(replay_path)
        if production.returncode or "test result: ok. 1 passed;" not in production.stdout:
            raise RuntimeError(production.stdout)
        print("PASS Rust apply replay")
    print("PASS native production Applier Go filesystem cases")

    mutated = json.loads(json.dumps(current))
    case = next(row for row in mutated["cases"] if row["input"]["id"] == "install")
    case["observation"]["target_content"] = "mutated fixture"
    with tempfile.TemporaryDirectory(prefix="update-apply-negative-") as temp:
        path = Path(temp) / "mutated.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        negative = replay(path)
        production_negative = production_replay(path)
    if negative.returncode == 0 or "install observation" not in negative.stdout:
        raise RuntimeError("install mutation was not rejected at its intended assertion")
    if production_negative.returncode == 0 or "install target content" not in production_negative.stdout:
        raise RuntimeError("production Applier accepted mutated Go install observation")
    blocked_mutated = json.loads(json.dumps(current))
    blocked = next(row for row in blocked_mutated["cases"] if row["input"]["id"] == "blocked-parent")
    blocked["observation"]["stage_during_download"] = True
    with tempfile.TemporaryDirectory(prefix="update-apply-blocked-negative-") as temp:
        path = Path(temp) / "mutated.json"
        path.write_text(json.dumps(blocked_mutated), encoding="utf-8")
        negative = replay(path)
    if negative.returncode == 0 or "blocked-parent observation" not in negative.stdout:
        raise RuntimeError("blocked-parent mutation was not rejected at its intended assertion")
    nested_mutated = json.loads(json.dumps(current))
    nested = next(row for row in nested_mutated["cases"] if row["input"]["id"] == "nested-install")
    nested["observation"]["files"][0]["path"] = "wrong-nested/mytool"
    with tempfile.TemporaryDirectory(prefix="update-apply-nested-negative-") as temp:
        path = Path(temp) / "mutated.json"
        path.write_text(json.dumps(nested_mutated), encoding="utf-8")
        negative = replay(path)
    if negative.returncode == 0 or "nested-install observation" not in negative.stdout:
        raise RuntimeError("nested-install mutation was not rejected at its intended assertion")
    zip_mutated = json.loads(json.dumps(current))
    zip_case = next(row for row in zip_mutated["cases"] if row["input"]["id"] == "zip-extract-blocked")
    zip_case["observation"]["target_content"] = "wrong ZIP installation"
    with tempfile.TemporaryDirectory(prefix="update-apply-zip-negative-") as temp:
        path = Path(temp) / "mutated.json"
        path.write_text(json.dumps(zip_mutated), encoding="utf-8")
        negative = replay(path)
    if negative.returncode == 0 or "zip-extract-blocked observation" not in negative.stdout:
        raise RuntimeError("ZIP mutation was not rejected at its intended assertion")
    asset_mutated = json.loads(json.dumps(current))
    shaped = next(row for row in asset_mutated["cases"] if row["input"]["id"] == "checksums-shaped-asset")
    shaped["observation"]["error_code"] = "wrong asset acceptance"
    with tempfile.TemporaryDirectory(prefix="update-apply-asset-negative-") as temp:
        path = Path(temp) / "mutated.json"
        path.write_text(json.dumps(asset_mutated), encoding="utf-8")
        negative = replay(path)
    if negative.returncode == 0 or "checksums-shaped-asset observation" not in negative.stdout:
        raise RuntimeError("checksums-shaped asset mutation was not rejected at its intended assertion")
    checksums_mutated = json.loads(json.dumps(current))
    malformed = next(row for row in checksums_mutated["cases"] if row["input"]["id"] == "malformed-checksums")
    malformed["observation"]["stage_during_download"] = True
    with tempfile.TemporaryDirectory(prefix="update-apply-checksums-negative-") as temp:
        path = Path(temp) / "mutated.json"
        path.write_text(json.dumps(checksums_mutated), encoding="utf-8")
        negative = replay(path)
    if negative.returncode == 0 or "malformed-checksums observation" not in negative.stdout:
        raise RuntimeError("malformed checksums mutation was not rejected at its intended assertion")
    print("PASS install, blocked-parent, nested, ZIP, asset and checksums mutations rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
