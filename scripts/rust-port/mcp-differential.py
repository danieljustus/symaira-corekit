#!/usr/bin/env python3
"""Replay frozen Go observations against the current Rust MCP binary."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

from frozen_process_oracle import check, serial_line_exchange

REPO = Path(__file__).resolve().parents[2]
ORACLE_COMMIT = "ff0e10ede1071f0a3137fd2774bd89d53f60cc9d"
CASES = REPO / "testdata" / "rust-port" / "mcp-cases.json"
HELPER = REPO / "scripts" / "rust-port" / "mcp-oracle" / "main.go"
RUST_PACKAGE = "symaira-core-mcp"
RUST_BIN = "symaira-mcp-fixture"


def frame(body: bytes) -> bytes:
    return b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body


def case_stdin(case: dict) -> bytes:
    mode = case["mode"]
    if "oversized_line_bytes" in case:
        return b"a" * case["oversized_line_bytes"] + b"\n"
    if "stdin_raw" in case:
        return case["stdin_raw"].encode()
    if "request_raw" in case:
        bodies = [case["request_raw"].encode()]
    else:
        requests = case.get("requests") or [case["request"]]
        bodies = [json.dumps(request, separators=(",", ":"), ensure_ascii=False).encode() for request in requests]
    separator = b"\n" if mode == "line" else b""
    return b"".join((body + separator if mode == "line" else frame(body)) for body in bodies)


def extract_oracle(destination: Path) -> None:
    archive = subprocess.run(["git", "archive", "--format=tar", ORACLE_COMMIT], cwd=REPO, check=True, stdout=subprocess.PIPE)
    with tarfile.open(fileobj=__import__("io").BytesIO(archive.stdout), mode="r:") as tar:
        tar.extractall(destination, filter="data")


def build_go_oracle(destination: Path) -> Path:
    oracle = destination / "oracle"
    oracle.mkdir()
    extract_oracle(oracle)
    helper = destination / "helper"
    helper.mkdir()
    (helper / "main.go").write_bytes(HELPER.read_bytes())
    (helper / "go.mod").write_text(
        "module symaira-mcp-oracle\n\ngo 1.26.6\n\n"
        "require github.com/danieljustus/symaira-corekit v0.17.0\n\n"
        f"replace github.com/danieljustus/symaira-corekit => {json.dumps(oracle.as_posix())}\n",
        encoding="utf-8",
    )
    if (oracle / "go.sum").exists():
        shutil.copy2(oracle / "go.sum", helper / "go.sum")
    binary = destination / ("go-mcp.exe" if os.name == "nt" else "go-mcp")
    env = os.environ.copy()
    env.update({"CGO_ENABLED": "0", "GOTOOLCHAIN": "go1.26.6"})
    subprocess.run(["go", "build", "-trimpath", "-o", str(binary), "."], cwd=helper, env=env, check=True)
    return binary


def run(binary: Path, stdin: bytes, case: dict) -> tuple[int, bytes, bytes]:
    env = {"PATH": os.environ.get("PATH", ""), "LANG": "C", "LC_ALL": "C", "TZ": "UTC", "NO_COLOR": "1"}
    env.update({key: os.environ[key] for key in ("TMPDIR", "TMP", "TEMP", "SystemRoot") if key in os.environ})
    env.update(case.get("env", {}))
    if case.get("exchange") == "request-response":
        if case["id"] != "MCP-011" or case["mode"] != "line":
            raise ValueError("request-response exchange is only defined for MCP-011 line mode")
        return serial_line_exchange(binary, stdin, env, timeout=10)
    completed = subprocess.run([str(binary)], input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=10, check=False)
    return completed.returncode, completed.stdout, completed.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true", help="execute Rust against the complete frozen Go corpus")
    modes.add_argument("--capture", type=Path, help="exclusive new native Go capture; requires GO_ORACLE=1")
    parser.add_argument("--fixture", type=Path, help="alternate capture, still checked against the trusted digest")
    args = parser.parse_args()
    document = json.loads(CASES.read_text(encoding="utf-8"))
    if document["oracle_commit"] != ORACLE_COMMIT:
        raise SystemExit("MCP corpus oracle provenance is not the fixed merged Go commit")
    cases = document["cases"]
    required = {f"MCP-{index:03d}" for index in range(1, 13)}
    covered = {match.group(1) for case in cases if (match := re.match(r"(MCP-\d{3})(?:-|$)", case["id"]))}
    if covered != required:
        missing = sorted(required - covered)
        extra = sorted(covered - required)
        raise SystemExit(f"MCP corpus coverage mismatch: missing={missing} extra={extra}")
    rust = REPO / "target" / "debug" / (RUST_BIN + (".exe" if os.name == "nt" else ""))
    args.rust_package, args.rust_bin = RUST_PACKAGE, RUST_BIN
    return check(Path(__file__), HELPER, CASES, ORACLE_COMMIT, cases,
                 [case_stdin(case) for case in cases], build_go_oracle, run, rust, args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(f"FAIL MCP capture: {error}") from error
