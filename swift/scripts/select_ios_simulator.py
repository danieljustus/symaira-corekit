#!/usr/bin/env python3
"""Print the UDID of an existing iOS or tvOS Simulator device for CI tests.

The runner host is shared, so this script only selects a device that already
exists: the newest available runtime of the platform (`--platform iOS`, the
default, or `--platform tvOS`), an iPhone (Apple TV) before any other device
family, then by name. It never creates, boots or erases a device; creating one
is an owner decision on that host.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

RUNTIME_PREFIX = "com.apple.CoreSimulator.SimRuntime."
PREFERRED_FAMILY = {"iOS": "iPhone", "tvOS": "Apple TV"}


def runtime_version(identifier: str, platform: str = "iOS") -> tuple[int, ...] | None:
    prefix = f"{RUNTIME_PREFIX}{platform}-"
    if not identifier.startswith(prefix):
        return None
    parts = identifier[len(prefix) :].split("-")
    if not parts or not all(re.fullmatch(r"\d+", part) for part in parts):
        return None
    return tuple(int(part) for part in parts)


def select_device(listing: dict, platform: str = "iOS") -> str:
    family = PREFERRED_FAMILY[platform]
    candidates = []
    for runtime, devices in listing.get("devices", {}).items():
        version = runtime_version(runtime, platform)
        if version is None:
            continue
        for device in devices:
            if not device.get("isAvailable", False) or not device.get("udid"):
                continue
            name = device.get("name", "")
            candidates.append((version, name.startswith(family), name, device["udid"]))
    if not candidates:
        raise RuntimeError(
            f"No available {platform} Simulator device exists on this host; "
            "the maintainer has to create or designate one"
        )
    # Newest runtime first, the preferred family first, then the lowest name for a stable pick.
    candidates.sort(key=lambda item: (tuple(-part for part in item[0]), not item[1], item[2]))
    return candidates[0][3]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=sorted(PREFERRED_FAMILY), default="iOS")
    args = parser.parse_args()
    result = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "available", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"simctl failed: {result.stderr.strip()}", file=sys.stderr)
        return 1
    try:
        print(select_device(json.loads(result.stdout), args.platform))
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
