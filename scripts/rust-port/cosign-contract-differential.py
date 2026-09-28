#!/usr/bin/env python3
"""Generate and replay Go cosign verification contract observations."""

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
FIXTURE = ROOT / "testdata/rust-port/fixtures/update/cosign.json"
ORACLE = ROOT / "scripts/rust-port/cosign-contract-oracle/main.go"
GO_SOURCE = ROOT / "updatecheck/cosign/cosign.go"


def goos_name():
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("win"):
        return "windows"
    return platform.system().lower()


def observe():
    output = subprocess.check_output(
        ["go", "run", "./scripts/rust-port/cosign-contract-oracle"], cwd=ROOT
    )
    result = json.loads(output)
    if len(result["cases"]) != 13:
        raise ValueError(f"cosign oracle ran {len(result['cases'])} cases, expected 13")
    result["go_source_sha256"] = hashlib.sha256(GO_SOURCE.read_bytes()).hexdigest()
    result["oracle_sha256"] = hashlib.sha256(ORACLE.read_bytes()).hexdigest()
    if result["goos"] != goos_name():
        raise ValueError(f"oracle goos {result['goos']} differs from host {goos_name()}")
    return result


def rust_replay(fixture):
    env = dict(os.environ, COSIGN_CONTRACT_FIXTURE=str(fixture))
    return subprocess.run(
        ["cargo", "test", "-p", "symaira-core-update", "--test", "cosign_contract", "--locked"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args()
    current = observe()
    if args.write:
        args.fixture.parent.mkdir(parents=True, exist_ok=True)
        args.fixture.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"PASS wrote {len(current['cases'])} Go cosign observations")
        return 0

    committed = json.loads(args.fixture.read_text(encoding="utf-8"))
    if committed["goos"] == current["goos"]:
        if current != committed:
            raise ValueError("Go cosign oracle disagrees with committed fixture")
        replay_path = args.fixture
    else:
        with tempfile.TemporaryDirectory(prefix="upd009-platform-") as directory:
            replay_path = Path(directory) / "platform.json"
            replay_path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
            replay = rust_replay(replay_path)
        if replay.returncode:
            raise RuntimeError(replay.stdout)
        print(f"PASS Rust cosign replay on {current['goos']} (fixture recorded on {committed['goos']})")
        replay_path = None
    if replay_path is not None:
        replay = rust_replay(replay_path)
        if replay.returncode:
            raise RuntimeError(replay.stdout)
        print(f"PASS Go/Rust cosign observations: {len(current['cases'])} cases")

    mutated = json.loads(json.dumps(current))
    mutated["cases"][0]["result"]["body"] += "-mutated"
    with tempfile.TemporaryDirectory(prefix="cosign-contract-negative-") as directory:
        path = Path(directory) / "mutated.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        negative = rust_replay(path)
    if negative.returncode == 0:
        raise RuntimeError("mutated cosign fixture was incorrectly accepted")
    print("PASS mutated-fixture negative control rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
