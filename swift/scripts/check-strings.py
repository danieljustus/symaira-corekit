#!/usr/bin/env python3
"""Check a product's Swift L("English key") calls against its String Catalog.

Pass the Swift source directory for one product target and the corresponding
.xcstrings file. The check covers ordinary, static lookup literals and plain
German string units; dynamic keys and operating-system resources are not scanned.
"""

import argparse
import json
import re
import sys
from pathlib import Path

LITERAL = r'"(?:[^"\\\n]|\\.)*"'
# Consume comments and other strings as well so examples in them are not lookups.
TOKENS = re.compile(rf'//[^\n]*|/\*[\s\S]*?\*/|\bL\s*\(\s*({LITERAL})\s*(?=[,)])|{LITERAL}')
FORMAT_MARKERS = re.compile(r'%%|%[@d]')


def placeholders(text):
    # Match the two conversions supported by the product lookup convention.
    return [marker for marker in FORMAT_MARKERS.findall(text) if marker != "%%"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args()
    if not args.source_root.is_dir():
        parser.error(f"not a source directory: {args.source_root}")

    try:
        used = set()
        for source in args.source_root.rglob("*.swift"):
            for match in TOKENS.finditer(source.read_text(encoding="utf-8")):
                if match[1] is not None:
                    try:
                        used.add(json.loads(match[1]))
                    except ValueError as error:
                        raise ValueError(f"{source}: expected a simple static L key: {match[1]}") from error
        if not used:
            raise ValueError(f"{args.source_root}: no literal L lookup keys found")
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))["strings"]
        if not isinstance(catalog, dict):
            raise ValueError("expected a 'strings' object")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"{args.catalog}: {error}", file=sys.stderr)
        return 1

    problems = []
    for key in sorted(used):
        german = catalog.get(key, {}).get("localizations", {}).get("de", {}).get("stringUnit", {}).get("value")
        if not isinstance(german, str) or not german.strip():
            problems.append(f"no German text: {key}")
        elif placeholders(key) != placeholders(german):
            problems.append(f"placeholders differ: {key}")
    if problems:
        for problem in problems:
            print(f"{args.catalog}: {problem}", file=sys.stderr)
        return 1

    print(f"{args.catalog}: all translated ({len(used)} keys)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
