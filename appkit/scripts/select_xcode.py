#!/usr/bin/env python3
"""Select the newest installed full Xcode meeting the CI minimum."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable

# Xcode 26 supplies the Swift 6.2 toolchain covered by the CI build.
MIN_XCODE = (26, 0)


def xcode_version(developer_dir: Path, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> tuple[int, ...]:
    result = runner(
        ["xcodebuild", "-version"],
        env={**os.environ, "DEVELOPER_DIR": str(developer_dir)},
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"^Xcode\s+(\d+(?:\.\d+)*)$", result.stdout, re.MULTILINE)
    if result.returncode != 0 or match is None:
        raise ValueError(f"unable to determine Xcode version for {developer_dir}")
    return tuple(int(part) for part in match.group(1).split("."))


def select_xcode(
    candidates: Iterable[Path],
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    minimum: tuple[int, ...] = MIN_XCODE,
) -> Path:
    supported: list[tuple[tuple[int, ...], Path]] = []
    for app in candidates:
        developer_dir = app / "Contents" / "Developer"
        if not developer_dir.is_dir():
            continue
        try:
            version = xcode_version(developer_dir, runner)
        except ValueError:
            continue
        if version >= minimum:
            supported.append((version, developer_dir))
    if not supported:
        minimum_text = ".".join(str(part) for part in minimum)
        raise RuntimeError(
            f"No installed full Xcode >= {minimum_text} supports the requested build"
        )
    return max(supported, key=lambda item: (item[0], str(item[1])))[1]


def installed_candidates() -> list[Path]:
    explicit = os.environ.get("DEVELOPER_DIR")
    if explicit:
        explicit_dir = Path(explicit)
        expected = explicit_dir.name == "Developer" and explicit_dir.parent.name == "Contents"
        if not explicit_dir.is_dir() or not expected:
            raise RuntimeError(
                f"DEVELOPER_DIR must name an installed Xcode Developer directory: {explicit}"
            )
        return [explicit_dir.parent.parent]

    beta = Path("/Applications/Xcode-beta.app")
    apps = sorted(Path("/Applications").glob("Xcode*.app"), key=lambda path: path.name)
    return ([beta] if beta.exists() else []) + [app for app in apps if app != beta]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--minimum",
        default="26.0",
        help="minimum Xcode version (default: 26.0 for Swift 6.2 coverage)",
    )
    args = parser.parse_args()
    minimum = tuple(int(part) for part in args.minimum.split("."))
    try:
        print(select_xcode(installed_candidates(), minimum=minimum))
    except (RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
