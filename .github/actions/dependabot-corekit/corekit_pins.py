#!/usr/bin/env python3
"""Check, and with --fix repair, the symaira-corekit pins of a consumer checkout.

Dependabot bumps a CoreKit pin in some files but not in all that must agree:

- Swift: it rewrites Package.swift and the tracked Xcode project
  (project.pbxproj, Package.resolved) but never the XcodeGen spec project.yml,
  so the next `xcodegen generate` would silently revert the bump.
- Cargo: for a `tag = "vX.Y.Z"` pin under [workspace.dependencies] it rewrites
  only Cargo.lock, so `cargo --locked` fails until Cargo.toml names the tag.

--fix copies the version Dependabot wrote into the stale file. Independently,
every CoreKit Cargo pin must be a release tag: Dependabot never moves a `rev`
or `branch` pin (ADR 0002, amendment 2026-11-16).

Stdlib only; runs on any GitHub-hosted runner and on the maintainer's Mac.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

COREKIT = "symaira-corekit"


def tracked(root: Path, *globs: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--", *(f":(glob){g}" for g in globs)],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def spec_pin(text: str) -> tuple[int, str] | None:
    """Line index and version of the exactVersion in the CoreKit package block."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if COREKIT in line and "url:" in line:
            for j in range(i + 1, min(i + 7, len(lines))):
                m = re.search(r"exactVersion:\s*[\"']?([0-9][^\"'\s]*)", lines[j])
                if m:
                    return j, m.group(1)
    return None


def swift_pin(text: str) -> str | None:
    m = re.search(COREKIT + r'(?:\.git)?"\s*,\s*exact:\s*"([^"]+)"', text)
    return m.group(1) if m else None


def pbxproj_pin(text: str) -> str | None:
    m = re.search(r"repositoryURL = \"[^\"]*" + COREKIT + r"[^\"]*\";.*?version = ([^;\s]+);", text, re.S)
    return m.group(1).strip('"') if m else None


def resolved_pin(text: str) -> str | None:
    m = re.search(r'"identity"\s*:\s*"' + COREKIT + r'".*?"version"\s*:\s*"([^"]+)"', text, re.S)
    return m.group(1) if m else None


def check_specs(root: Path, fix: bool, errors: list[str], fixed: list[str]) -> int:
    checked = 0
    for spec in tracked(root, "**/project.yml", "project.yml"):
        text = (root / spec).read_text(errors="replace")
        pin = spec_pin(text)
        if pin is None:
            continue
        line_no, want = pin
        prefix = "" if Path(spec).parent == Path(".") else f"{Path(spec).parent}/"
        siblings: dict[str, str] = {}
        for f in tracked(
            root,
            f"{prefix}Package.swift",
            f"{prefix}*.xcodeproj/project.pbxproj",
            f"{prefix}*.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved",
        ):
            body = (root / f).read_text(errors="replace")
            if f.endswith("Package.resolved"):
                have = resolved_pin(body)
            elif f.endswith(".pbxproj"):
                have = pbxproj_pin(body)
            else:
                have = swift_pin(body)
            if have:
                siblings[f] = have
        checked += len(siblings)
        versions = set(siblings.values())
        if not versions or versions == {want}:
            continue
        if len(versions) > 1:
            errors.append(f"{spec}: CoreKit pins disagree: {siblings}; align them by hand")
            continue
        (have,) = versions
        if fix:
            lines = text.splitlines(keepends=True)
            lines[line_no] = lines[line_no].replace(want, have, 1)
            (root / spec).write_text("".join(lines))
            fixed.append(f"{spec}: exactVersion {want} -> {have}")
        else:
            errors.append(
                f"{spec} pins symaira-corekit {want} but {', '.join(siblings)} pin {have}; "
                f"set exactVersion: {have} in {spec}"
            )
    return checked


def check_cargo(root: Path, fix: bool, errors: list[str], fixed: list[str]) -> int:
    checked = 0
    for manifest in tracked(root, "**/Cargo.toml", "Cargo.toml"):
        text = (root / manifest).read_text(errors="replace")
        pin_lines = [l for l in text.splitlines() if COREKIT in l and "git" in l and not l.lstrip().startswith("#")]
        if not pin_lines:
            continue
        for l in pin_lines:
            if re.search(r"\b(rev|branch)\s*=", l) or not re.search(r"\btag\s*=", l):
                errors.append(f"{manifest}: CoreKit pin is not a release tag, Dependabot cannot bump it: {l.strip()}")
        lock = str(Path(manifest).with_name("Cargo.lock"))
        if not tracked(root, lock):
            continue
        want = sorted(set(re.findall(r'\btag\s*=\s*"(v[^"]+)"', "\n".join(pin_lines))))
        have = sorted(set(re.findall(COREKIT + r"\?tag=(v[^#\"]+)", (root / lock).read_text(errors="replace"))))
        if not want or not have:
            continue
        checked += 1
        if want == have:
            continue
        if fix and len(have) == 1:
            new = "\n".join(
                re.sub(r'(\btag\s*=\s*")v[^"]+(")', rf"\g<1>{have[0]}\g<2>", l)
                if COREKIT in l and not l.lstrip().startswith("#") else l
                for l in text.split("\n")
            )
            (root / manifest).write_text(new)
            fixed.append(f"{manifest}: tag {' '.join(want)} -> {have[0]}")
        else:
            errors.append(
                f"{manifest} pins symaira-corekit tag {' '.join(want)} but {lock} resolves {' '.join(have)}; "
                f'set tag = "{have[-1]}" in {manifest}'
            )
    return checked


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fix", action="store_true", help="rewrite stale project.yml / Cargo.toml pins")
    ap.add_argument("--root", type=Path, default=Path("."), help="consumer checkout (default: cwd)")
    args = ap.parse_args(argv)
    root = Path(
        subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=args.root, check=True,
                       capture_output=True, text=True).stdout.strip()
    )
    errors: list[str] = []
    fixed: list[str] = []
    checked = check_specs(root, args.fix, errors, fixed) + check_cargo(root, args.fix, errors, fixed)
    for f in fixed:
        print(f"fixed: {f}")
    for e in errors:
        print(f"::error::{e}")
    if not errors:
        print(f"symaira-corekit pins consistent ({checked} pin file(s) checked)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
