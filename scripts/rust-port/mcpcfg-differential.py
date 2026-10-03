#!/usr/bin/env python3
"""Replay frozen Go observations against the current Rust MCP-config binary."""
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

from frozen_process_oracle import check, stream_exchange

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
        f"replace github.com/danieljustus/symaira-corekit => {json.dumps(oracle.as_posix())}\n",
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
    env.update({key: os.environ[key] for key in ("TMPDIR", "TMP", "TEMP", "SystemRoot") if key in os.environ})
    return stream_exchange(binary, stdin, env, timeout=30)


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true", help="execute Rust against the complete frozen Go corpus")
    modes.add_argument("--capture", type=Path, help="exclusive new native Go capture; requires GO_ORACLE=1")
    parser.add_argument("--fixture", type=Path, help="alternate capture, still checked against the trusted digest")
    args = parser.parse_args()
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
    args.rust_package, args.rust_bin = RUST_PACKAGE, RUST_BIN
    return check(Path(__file__), HELPER, CASES, ORACLE_COMMIT, cases,
                 [json.dumps(case, separators=(",", ":"), ensure_ascii=False).encode() for case in cases],
                 build_go_oracle, run, rust, args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(f"FAIL MCP-config capture: {error}") from error