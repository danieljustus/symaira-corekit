#!/usr/bin/env python3
"""Drop a SwiftPM build description that points at an unmounted Metal toolchain.

The Metal toolchain is a cryptex mounted under a path whose suffix changes on
every reboot. A persistent `.build` on a self-hosted runner keeps absolute
paths to the old mount in `XCBuildData`, and the next build then fails with
"unable to spawn process .../MetalToolchain-<old>/.../metal". Removing only the
build description keeps the compiled objects; SwiftPM regenerates it in seconds.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

MOUNT_ROOT = Path("/var/run/com.apple.security.cryptexd/mnt")
TOOLCHAIN_REF = re.compile(rb"com\.apple\.MobileAsset\.MetalToolchain-[A-Za-z0-9._-]+")


def referenced_toolchains(build_description: Path) -> set[str]:
    refs: set[str] = set()
    for path in build_description.rglob("*"):
        if path.is_file():
            refs.update(match.decode() for match in TOOLCHAIN_REF.findall(path.read_bytes()))
    return refs


def stale_toolchains(build_dir: Path, mount_root: Path) -> set[str]:
    build_description = build_dir / "out" / "Intermediates.noindex" / "XCBuildData"
    if not build_description.is_dir():
        return set()
    mounted = {entry.name for entry in mount_root.iterdir()} if mount_root.is_dir() else set()
    return referenced_toolchains(build_description) - mounted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=Path(".build"))
    parser.add_argument("--mount-root", type=Path, default=MOUNT_ROOT)
    args = parser.parse_args(argv)

    stale = stale_toolchains(args.build_dir, args.mount_root)
    if not stale:
        print("Build description matches the mounted Metal toolchain (or none exists).")
        return 0
    build_description = args.build_dir / "out" / "Intermediates.noindex" / "XCBuildData"
    shutil.rmtree(build_description)
    print(f"Removed {build_description}: it references unmounted {', '.join(sorted(stale))}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
