#!/usr/bin/env python3
"""Run the MCP-configuration corpus against the pinned Go implementation and the Rust port."""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

REPO = Path(__file__).resolve().parents[2]
ORACLE_COMMIT = "f3d3eb79b9b1f31b4f973d2ed518a8292cedf588"
CASES = REPO / "testdata" / "rust-port" / "mcpcfg-cases.json"
HELPER = REPO / "scripts" / "rust-port" / "mcpcfg-oracle" / "main.go"
RUST_PACKAGE = "symaira-core-mcpcfg"
RUST_BIN = "symaira-mcpcfg-fixture"
REQUIRED = {f"MCFG-{index:03d}" for index in range(1, 6)}


def extract_oracle(destination: Path) -> None:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", ORACLE_COMMIT],
        cwd=REPO,
        check=True,
        stdout=subprocess.PIPE,
    )
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
        tar.extractall(destination, filter="data")


def build_go_oracle(destination: Path) -> Path:
    oracle = destination / "oracle"
    oracle.mkdir()
    extract_oracle(oracle)
    helper = destination / "helper"
    helper.mkdir()
    (helper / "main.go").write_bytes(HELPER.read_bytes())
    (helper / "go.mod").write_text(
        "module symaira-mcpcfg-oracle\n\ngo 1.26.6\n\n"
        "require github.com/danieljustus/symaira-corekit v0.17.0\n\n"
        f"replace github.com/danieljustus/symaira-corekit => {oracle.as_posix()}\n",
        encoding="utf-8",
    )
    if (oracle / "go.sum").exists():
        shutil.copy2(oracle / "go.sum", helper / "go.sum")
    binary = destination / ("go-mcpcfg.exe" if os.name == "nt" else "go-mcpcfg")
    env = os.environ.copy()
    env.update({"CGO_ENABLED": "0", "GOTOOLCHAIN": "go1.26.6"})
    # The helper imports the oracle's own dependencies (yaml.v3), so the module
    # graph has to be completed before building.
    subprocess.run(["go", "mod", "tidy"], cwd=helper, env=env, check=True)
    subprocess.run(
        ["go", "build", "-trimpath", "-o", str(binary), "."],
        cwd=helper,
        env=env,
        check=True,
    )
    return binary


def run(binary: Path, stdin: bytes, case: dict) -> tuple[int, bytes, bytes]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "NO_COLOR": "1",
    }
    env.update(case.get("env", {}))
    completed = subprocess.run(
        [str(binary)],
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=30,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="run the complete pinned-oracle corpus")
    args = parser.parse_args()
    if not args.check:
        parser.error("use --check")
    document = json.loads(CASES.read_text(encoding="utf-8"))
    if document["oracle_commit"] != ORACLE_COMMIT:
        raise SystemExit("MCP-config corpus oracle provenance is not the fixed Go commit")
    cases = document["cases"]
    covered = {match.group(1) for case in cases if (match := re.match(r"(MCFG-\d{3})(?:-|$)", case["id"]))}
    if covered != REQUIRED:
        missing = sorted(REQUIRED - covered)
        extra = sorted(covered - REQUIRED)
        raise SystemExit(f"MCP-config corpus coverage mismatch: missing={missing} extra={extra}")
    rust = REPO / "target" / "debug" / (RUST_BIN + (".exe" if os.name == "nt" else ""))
    subprocess.run(
        ["cargo", "build", "-p", RUST_PACKAGE, "--bin", RUST_BIN, "--locked"],
        cwd=REPO,
        check=True,
    )
    with tempfile.TemporaryDirectory(prefix="corekit-mcpcfg-oracle-") as raw:
        go = build_go_oracle(Path(raw))
        for case in cases:
            payload = json.dumps(case, separators=(",", ":"), ensure_ascii=False).encode()
            left = run(go, payload, case)
            right = run(rust, payload, case)
            if left[0] != right[0] or left[1] != right[1]:
                print(f"FAIL {case['id']}: exit/stdout differs", file=sys.stderr)
                print(f"Go exit={left[0]} stdout={left[1]!r}", file=sys.stderr)
                print(f"Rust exit={right[0]} stdout={right[1]!r}", file=sys.stderr)
                return 1
            if case.get("stderr") != "ignore" and left[2] != right[2]:
                print(f"FAIL {case['id']}: stderr differs", file=sys.stderr)
                print(f"Go stderr={left[2]!r}", file=sys.stderr)
                print(f"Rust stderr={right[2]!r}", file=sys.stderr)
                return 1
            if b"\x00" in right[1]:
                print(f"FAIL {case['id']}: stdout contains NUL", file=sys.stderr)
                return 1
            print(f"PASS {case['id']}")
    print(f"PASS MCP-config differential ({len(cases)} cases, oracle {ORACLE_COMMIT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())