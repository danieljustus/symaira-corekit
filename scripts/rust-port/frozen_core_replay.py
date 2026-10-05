#!/usr/bin/env python3
"""Verify reviewed foundation/LLM recordings and execute Rust without Go."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from frozen_core_anchors import FAMILIES
from bounded_oracle_process import run_checked

ROOT = Path(__file__).resolve().parents[2]


def verify_bytes(raw: bytes, expected: str, label: str) -> None:
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"reviewed frozen corpus byte mismatch: {label}")
    json.loads(raw)


def verify_family(family: str) -> dict:
    specification = FAMILIES[family]
    files = specification["files"]
    if not files:
        raise ValueError("empty frozen corpus inventory")
    for relative, expected in files.items():
        path = ROOT / relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise ValueError(f"frozen corpus must be a regular file: {relative}")
        verify_bytes(path.read_bytes(), expected, relative)
    for base, expected_count in specification["directories"].items():
        actual = {p.relative_to(ROOT).as_posix() for p in (ROOT / base).rglob("*.json")}
        recorded = {path for path in files if path.startswith(base + "/")}
        if actual != recorded or len(actual) != expected_count:
            raise ValueError(f"frozen corpus file inventory drift: {base}")

    # Exercise the same fixed-digest boundary as normal replay. A valid JSON
    # spelling change must fail before Cargo, even if JSON values stay equal.
    relative, expected = next(iter(files.items()))
    try:
        verify_bytes((ROOT / relative).read_bytes() + b"\n", expected, relative)
    except ValueError as error:
        if "byte mismatch" not in str(error):
            raise
    else:
        raise ValueError("frozen corpus mutation was accepted")
    return specification


def run_rust(family: str) -> None:
    specification = verify_family(family)
    command = ["cargo", "test", "--locked", "--offline", "--all-features"]
    for package in specification["packages"]:
        command.extend(["-p", package])
    import os
    completed = run_checked(command, cwd=ROOT, env=dict(os.environ), timeout=600,
                            artifact_dir=ROOT / "target" / "frozen-core-replay" / family, check=True)
    # Cargo success with no tests is insufficient for a contract replay.
    import re
    counts = re.findall(r"test result: ok\. (\d+) passed; 0 failed; (\d+) ignored;", completed.stdout.decode("utf-8"))
    if not counts or sum(int(passed) for passed, _ in counts) < specification["minimum_tests"]:
        raise ValueError(f"Rust replay did not execute the required {family} tests")
    if any(int(ignored) for _, ignored in counts):
        raise ValueError(f"Rust {family} replay unexpectedly skipped a test")
    verify_family(family)  # Re-read actual inputs after the real Rust execution.
    print(json.dumps({"status": "PASS", "family": family, "files": len(specification["files"]),
                      "contract_groups": specification["contract_groups"],
                      "rust_tests": sum(int(passed) for passed, _ in counts),
                      "fixture_mutation_rejected": True}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=sorted(FAMILIES), required=True)
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.verify_only:
            specification = verify_family(arguments.family)
            print(f"PASS frozen {arguments.family}: {len(specification['files'])} fixed-byte inputs; mutation rejected")
        else:
            run_rust(arguments.family)
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            # Full bounded output remains in the raw artifact; expose the
            # relevant tail in ordinary CI instead of hiding Cargo's reason.
            for stream in (error.stdout, error.stderr):
                if stream:
                    print(stream[-4096:].decode("utf-8", "replace"), file=sys.stderr)
        print(f"FAIL frozen core replay: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
