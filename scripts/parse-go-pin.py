#!/usr/bin/env python3
"""Parse exactly one CoreKit require from a Go module/workspace file."""
from __future__ import annotations

import re
import sys

MODULE = "github.com/danieljustus/symaira-corekit"
VERSION = re.compile(
    r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


def parse(text: str) -> str:
    versions: list[str] = []
    invalid = False
    in_block = False
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line:
            continue
        if in_block and line == ")":
            in_block = False
            continue
        if not in_block and line == "require (":
            in_block = True
            continue
        if not in_block and line.startswith("require "):
            declaration = line[len("require "):].strip()
        elif in_block:
            declaration = line
        else:
            continue
        fields = declaration.split()
        if not fields or fields[0] != MODULE:
            continue
        if len(fields) != 2 or not VERSION.fullmatch(fields[1]):
            invalid = True
        else:
            versions.append(fields[1])
    if in_block:
        invalid = True
    if invalid:
        return "invalid"
    if not versions:
        return "missing"
    if len(versions) > 1:
        return "inconsistent" if len(set(versions)) > 1 else "duplicate"
    return versions[0]


if __name__ == "__main__":
    print(parse(sys.stdin.read()))
