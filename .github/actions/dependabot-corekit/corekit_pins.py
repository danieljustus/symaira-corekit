#!/usr/bin/env python3
"""Check, and with --fix repair, the symaira-corekit pins of a consumer checkout.

Dependabot bumps a CoreKit pin in some files but not in all that must agree:

- Swift: it rewrites Package.swift and the tracked Xcode project
  (project.pbxproj, Package.resolved) but never the XcodeGen spec project.yml,
  so the next `xcodegen generate` would silently revert the bump.
- Cargo: for a `tag = "vX.Y.Z"` pin under [workspace.dependencies] it rewrites
  only Cargo.lock, and only partly (symaira-desktop #1412 moved one of seven
  crates), so `cargo --locked` fails until Cargo.toml names the tag and the
  lock is re-resolved. A second workspace (fuzz/) inherits the pins through
  path dependencies and needs the same re-resolution.
- Nested Swift packages: it updates each Package.swift directory on its own. A
  root package that depends on a local package (`.package(path:)`) which also
  pins CoreKit cannot move alone, so the local package moves and the root
  manifest (and its Package.resolved) stays behind and stops resolving.

--fix copies the version Dependabot wrote into the stale file; for Swift
manifests that disagree it raises every one to the highest pinned version. Independently,
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


def version_key(version: str) -> tuple:
    return tuple(int(p) if p.isdigit() else -1 for p in re.split(r"[.+-]", version))


def tag_revision(version: str) -> str:
    """Commit SHA of the CoreKit release tag (peeled, so annotated tags work)."""
    out = subprocess.run(
        ["git", "ls-remote", f"https://github.com/danieljustus/{COREKIT}.git",
         f"refs/tags/v{version}", f"refs/tags/v{version}^{{}}"],
        check=True, capture_output=True, text=True,
    ).stdout
    refs = dict(reversed(line.split("\t")) for line in out.splitlines() if "\t" in line)
    sha = refs.get(f"refs/tags/v{version}^{{}}") or refs.get(f"refs/tags/v{version}")
    if not sha:
        raise SystemExit(f"::error::CoreKit tag v{version} not found")
    return sha


def check_swift_manifests(root: Path, fix: bool, errors: list[str], fixed: list[str]) -> int:
    """All tracked Package.swift files of one repository pin the same CoreKit."""
    manifests = {}
    for f in tracked(root, "**/Package.swift", "Package.swift"):
        have = swift_pin((root / f).read_text(errors="replace"))
        if have:
            manifests[f] = have
    versions = set(manifests.values())
    if len(versions) < 2:
        return len(manifests)
    target = max(versions, key=version_key)
    if not fix:
        errors.append(f"Package.swift CoreKit pins disagree: {manifests}; set exact: \"{target}\" everywhere")
        return len(manifests)
    revision = None
    for f, have in manifests.items():
        if have == target:
            continue
        text = (root / f).read_text()
        new = re.sub(COREKIT + r'((?:\.git)?"\s*,\s*exact:\s*")[^"]+(")',
                     lambda m: f"{COREKIT}{m.group(1)}{target}{m.group(2)}", text, count=1)
        (root / f).write_text(new)
        fixed.append(f"{f}: exact {have} -> {target}")
        resolved = str(Path(f).with_name("Package.resolved"))
        if not tracked(root, resolved):
            continue
        body = (root / resolved).read_text()
        if resolved_pin(body) in (None, target):
            continue
        revision = revision or tag_revision(target)
        # SwiftPM re-resolves on the stale originHash; the pin itself must name the tag.
        body = re.sub(
            r'("identity"\s*:\s*"' + COREKIT + r'".*?"revision"\s*:\s*")[0-9a-f]+(".*?"version"\s*:\s*")[^"]+(")',
            lambda m: f"{m.group(1)}{revision}{m.group(2)}{target}{m.group(3)}", body, count=1, flags=re.S)
        (root / resolved).write_text(body)
        fixed.append(f"{resolved}: {COREKIT} -> {target}")
    return len(manifests)


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


LOCK_TAG = re.compile(COREKIT + r"\?tag=(v[^#\"]+)")


def refresh_lock(manifest: Path) -> None:
    """Let Cargo re-resolve the lockfile minimally against the edited manifest."""
    subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--manifest-path", str(manifest)],
        check=True, stdout=subprocess.DEVNULL,
    )


def check_cargo(root: Path, fix: bool, errors: list[str], fixed: list[str]) -> int:
    """Every CoreKit Cargo pin and every tracked Cargo.lock names one release tag.

    Dependabot leaves two kinds of stale state: a `[workspace.dependencies]` tag
    it never rewrites, with a lockfile it moved only partly (one crate on the
    new tag, the rest on the old one), and a second workspace such as fuzz/
    whose lockfile inherits the pins through path dependencies. --fix sets every
    pin to the highest tag found and lets Cargo re-resolve each stale lockfile.
    """
    manifests: dict[str, list[str]] = {}
    for manifest in tracked(root, "**/Cargo.toml", "Cargo.toml"):
        text = (root / manifest).read_text(errors="replace")
        pin_lines = [l for l in text.splitlines() if COREKIT in l and "git" in l and not l.lstrip().startswith("#")]
        if not pin_lines:
            continue
        for l in pin_lines:
            if re.search(r"\b(rev|branch)\s*=", l) or not re.search(r"\btag\s*=", l):
                errors.append(f"{manifest}: CoreKit pin is not a release tag, Dependabot cannot bump it: {l.strip()}")
        manifests[manifest] = sorted(set(re.findall(r'\btag\s*=\s*"(v[^"]+)"', "\n".join(pin_lines))))
    locks = {
        lock: sorted(set(LOCK_TAG.findall((root / lock).read_text(errors="replace"))))
        for lock in tracked(root, "**/Cargo.lock", "Cargo.lock")
    }
    locks = {lock: tags for lock, tags in locks.items() if tags}
    tags = {t for v in [*manifests.values(), *locks.values()] for t in v}
    if not tags:
        return 0
    target = max(tags, key=lambda t: version_key(t.lstrip("v")))
    for manifest, want in manifests.items():
        if want in ([], [target]):
            continue
        if not fix:
            errors.append(f'{manifest} pins symaira-corekit tag {" ".join(want)}; set tag = "{target}"')
            continue
        text = (root / manifest).read_text()
        new = "\n".join(
            re.sub(r'(\btag\s*=\s*")v[^"]+(")', rf"\g<1>{target}\g<2>", l)
            if COREKIT in l and not l.lstrip().startswith("#") else l
            for l in text.split("\n")
        )
        (root / manifest).write_text(new)
        fixed.append(f"{manifest}: tag {' '.join(want)} -> {target}")
    for lock, have in locks.items():
        if have == [target]:
            continue
        manifest = Path(lock).with_name("Cargo.toml")
        if not fix:
            errors.append(f"{lock} resolves symaira-corekit {' '.join(have)}, not {target}; run cargo update for the CoreKit crates")
            continue
        refresh_lock(root / manifest)
        after = sorted(set(LOCK_TAG.findall((root / lock).read_text(errors="replace"))))
        if after == [target]:
            fixed.append(f"{lock}: {' '.join(have)} -> {target}")
        else:
            errors.append(f"{lock} still resolves symaira-corekit {' '.join(after)} after re-resolving; align it by hand")
    return len(manifests) + len(locks)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fix", action="store_true", help="rewrite stale project.yml / Cargo.toml / Package.swift pins")
    ap.add_argument("--root", type=Path, default=Path("."), help="consumer checkout (default: cwd)")
    args = ap.parse_args(argv)
    root = Path(
        subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=args.root, check=True,
                       capture_output=True, text=True).stdout.strip()
    )
    errors: list[str] = []
    fixed: list[str] = []
    # Manifests first: the project.yml check compares against the synced Package.swift.
    checked = check_swift_manifests(root, args.fix, errors, fixed)
    checked += check_specs(root, args.fix, errors, fixed) + check_cargo(root, args.fix, errors, fixed)
    for f in fixed:
        print(f"fixed: {f}")
    for e in errors:
        print(f"::error::{e}")
    if not errors:
        print(f"symaira-corekit pins consistent ({checked} pin file(s) checked)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
