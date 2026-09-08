#!/usr/bin/env python3
"""Run the CoreKit Miri gate with explicit isolation modes.

Miri's default isolation is useful for pure code, but it rejects the real
filesystem/process operations exercised by the contract and foundation tests.
Those tests therefore run in a separate, explicitly non-isolated invocation.
The two package sets are intentionally exhaustive and disjoint.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]

# Keep default isolation for code whose tests do not need ambient I/O.
PURE_PACKAGES = (
    "symaira-core-exit",
    "symaira-core-version",
    "symaira-core-env",
    "symaira-core-log",
    "symaira-core-mcp",
)

# These tests intentionally exercise filesystem/process/environment boundaries.
NON_ISOLATED_PACKAGES = (
    "symaira-core-config",
    "symaira-core-fs",
    "symaira-core-secretref",
    "symaira-contract-fixtures",
    "symaira-core-foundation",
)

NEGATIVE_PACKAGE = "symaira-contract-fixtures"
NEGATIVE_TEST = "con_001_exit_fixture_is_valid_and_byte_stable"
MIRI_EXPENSIVE_TEST = "frame_parser_fuzz_smoke_10000"


def cargo_packages() -> set[str]:
    result = subprocess.run(
        ["cargo", "metadata", "--no-deps", "--format-version", "1"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    metadata = json.loads(result.stdout)
    return {package["name"] for package in metadata["packages"]}


def validate_package_partition() -> None:
    pure = set(PURE_PACKAGES)
    non_isolated = set(NON_ISOLATED_PACKAGES)
    overlap = pure & non_isolated
    if overlap:
        raise RuntimeError(f"Miri package sets overlap: {sorted(overlap)}")

    expected = cargo_packages()
    actual = pure | non_isolated
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise RuntimeError(
            "Miri package partition is not exhaustive: "
            f"missing={missing}, extra={extra}"
        )

    if NEGATIVE_PACKAGE not in non_isolated:
        raise RuntimeError("negative isolation probe must be non-isolated")


def miri_command(packages: Sequence[str], *, test: str | None = None) -> list[str]:
    command = ["cargo", "+nightly", "miri", "test"]
    for package in packages:
        command.extend(("-p", package))
    if test is not None:
        command.extend(("--test", "con_001"))
    command.extend(("--all-features", "--locked"))
    if test is not None:
        command.extend(("--", "--exact", test))
    else:
        # This deterministic 10k smoke is covered by the dedicated fuzz gate;
        # interpreting it under Miri adds an unbounded, redundant runtime cost.
        command.extend(("--", "--skip", MIRI_EXPENSIVE_TEST))
    return command


def run_gate_command(
    label: str, command: Sequence[str], *, miriflags: str | None, timeout: int = 600
) -> None:
    environment = os.environ.copy()
    if miriflags is None:
        environment.pop("MIRIFLAGS", None)
    else:
        environment["MIRIFLAGS"] = miriflags
    print(f"=== {label} ===", flush=True)
    print("$", " ".join(command), flush=True)
    try:
        subprocess.run(command, cwd=ROOT, env=environment, check=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{label} timed out after {timeout}s") from error


def negative_isolation_probe() -> None:
    """Prove an I/O fixture cannot be reported green under default isolation."""
    command = miri_command((NEGATIVE_PACKAGE,), test=NEGATIVE_TEST)
    environment = os.environ.copy()
    environment.pop("MIRIFLAGS", None)
    print("=== negative default-isolation probe ===", flush=True)
    print("$", " ".join(command), flush=True)
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            text=True,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("negative default-isolation probe timed out") from error

    if result.returncode == 0:
        raise RuntimeError(
            "negative default-isolation probe unexpectedly passed; "
            "the I/O package classification is no longer proven"
        )
    output = result.stdout.lower()
    if "open" not in output or "isolation" not in output:
        raise RuntimeError(
            "negative default-isolation probe failed for an unexpected reason; "
            "expected Miri's isolated open diagnostic"
        )
    print("PASS: default isolation rejects the I/O fixture", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="validate the package partition")
    parser.add_argument(
        "--negative-test",
        action="store_true",
        help="prove default isolation rejects the known I/O fixture",
    )
    parser.add_argument("--run", action="store_true", help="run both explicit Miri modes")
    args = parser.parse_args()

    if sum((args.self_test, args.negative_test, args.run)) != 1:
        parser.error("choose exactly one of --self-test, --negative-test or --run")

    try:
        validate_package_partition()
        if args.self_test:
            print("PASS: Miri package partition is exhaustive and disjoint")
        elif args.negative_test:
            negative_isolation_probe()
        else:
            run_gate_command(
                "pure/core Miri (default isolation)",
                miri_command(PURE_PACKAGES),
                miriflags=None,
            )
            run_gate_command(
                "I/O boundary Miri (isolation disabled explicitly)",
                miri_command(NON_ISOLATED_PACKAGES),
                miriflags="-Zmiri-disable-isolation",
            )
    except (OSError, subprocess.CalledProcessError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Miri gate failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
