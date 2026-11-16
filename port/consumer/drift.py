#!/usr/bin/env python3
"""List every CoreKit pin in the sibling Symaira checkouts.

Read-only and informational: it scans the tracked Cargo, SwiftPM, XcodeGen,
Xcode and Go manifests of each ``symaira-*`` checkout next to CoreKit,
resolves each pin against the local CoreKit tags and reports how many
releases it trails. It never fetches, edits or judges release evidence; that
stays with ``verify.py``. Exit status is 0 unless the inputs are unreadable.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys

COREKIT = "symaira-corekit"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
MANIFEST_NAMES = {"Cargo.toml", "Package.swift", "project.yml", "project.pbxproj", "Package.resolved", "go.mod"}

CARGO_GIT_RE = re.compile(r'git\s*=\s*"[^"]*symaira-corekit[^"]*"')
CARGO_REF_RE = re.compile(r'\b(rev|tag|branch)\s*=\s*"([^"]+)"')
SWIFT_RE = re.compile(r'symaira-corekit(?:\.git)?"\s*,\s*(exact|from|revision|branch)\s*:\s*"([^"]+)"')
XCODEGEN_RE = re.compile(r'^\s*(exactVersion|from|minVersion|revision|branch)\s*:\s*"?([^"\s#]+)')
PBX_REF_RE = re.compile(r'\b(version|minimumVersion|revision|branch)\s*=\s*"?([^";]+)"?;')
RESOLVED_RE = re.compile(r'"(version|revision)"\s*:\s*"([^"]+)"')
GO_RE = re.compile(r"github\.com/danieljustus/symaira-corekit\s+(v\S+)")


@dataclass(frozen=True)
class Pin:
    path: str
    kind: str
    ref: str  # version "X.Y.Z", 40-hex revision, or a branch name


def _version(text: str) -> tuple[int, int, int] | None:
    match = VERSION_RE.fullmatch(text)
    return tuple(int(part) for part in match.groups()) if match else None  # type: ignore[return-value]


def _following(lines: list[str], start: int, pattern: re.Pattern[str], window: int) -> tuple[str, str] | None:
    for line in lines[start + 1:start + 1 + window]:
        match = pattern.search(line)
        if match:
            return match.group(1), match.group(2)
    return None


def parse_pins(path: str, text: str) -> list[Pin]:
    """Return the CoreKit pins declared in one manifest (text-based, no tooling)."""
    name = Path(path).name
    lines = text.splitlines()
    pins: list[Pin] = []
    for index, line in enumerate(lines):
        if name == "Cargo.toml" and CARGO_GIT_RE.search(line):
            # ponytail: inline tables only; a multi-line [dependencies.x] git
            # table would need a TOML parser.
            ref = CARGO_REF_RE.search(line)
            pins.append(Pin(path, f"cargo {ref.group(1)}" if ref else "cargo", ref.group(2) if ref else "default-branch"))
        elif name == "Package.swift":
            match = SWIFT_RE.search(line)
            if match:
                pins.append(Pin(path, f"swiftpm {match.group(1)}", match.group(2)))
        elif name == "project.yml" and COREKIT in line and "url:" in line:
            found = _following(lines, index, XCODEGEN_RE, 6)
            if found:
                pins.append(Pin(path, f"xcodegen {found[0]}", found[1]))
        elif name == "project.pbxproj" and "repositoryURL" in line and COREKIT in line:
            found = _following(lines, index, PBX_REF_RE, 5)
            if found:
                pins.append(Pin(path, f"xcode {found[0]}", found[1]))
        elif name == "Package.resolved" and f'"identity" : "{COREKIT}"' in line.replace('":"', '" : "'):
            state = [m for m in (RESOLVED_RE.search(item) for item in lines[index + 1:index + 9]) if m]
            versions = [m.group(2) for m in state if m.group(1) == "version"]
            revisions = [m.group(2) for m in state if m.group(1) == "revision"]
            if versions or revisions:
                pins.append(Pin(path, "resolved", versions[0] if versions else revisions[0]))
        elif name == "go.mod":
            match = GO_RE.search(line)
            if match:
                pins.append(Pin(path, "go", match.group(1)))
    return [Pin(pin.path, pin.kind, pin.ref.removeprefix("v") if _version(pin.ref) else pin.ref) for pin in pins]


def _git(args: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    return result.returncode, result.stdout.strip()


class Releases:
    """CoreKit release tags (vX.Y.Z) with their commits, read from a local checkout."""

    def __init__(self, corekit_root: Path) -> None:
        self.root = corekit_root
        code, out = _git(["for-each-ref", "--format=%(refname:short) %(objectname) %(*objectname)", "refs/tags/v*"], corekit_root)
        if code:
            raise RuntimeError(f"cannot list CoreKit tags in {corekit_root}")
        self.tags: dict[str, str] = {}
        for row in out.splitlines():
            tag, obj, peeled = (row.split() + [""])[:3]
            if _version(tag):
                self.tags[tag] = peeled or obj
        self.ordered = sorted(self.tags, key=lambda tag: _version(tag) or (0, 0, 0))
        self.latest = self.ordered[-1] if self.ordered else None

    def resolve(self, ref: str) -> tuple[str, int | None]:
        """Return (identity, newer-release count); count is None when unknown."""
        version = _version(ref)
        if version:
            return f"v{ref}", sum((_version(tag) or (0, 0, 0)) > version for tag in self.ordered)
        if not SHA_RE.fullmatch(ref):
            return f"branch {ref}", None
        # Peel first: Cargo also accepts an annotated tag object's SHA as `rev`.
        code, commit = _git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], self.root)
        if code:
            return f"{ref[:7]} (unknown to local CoreKit)", None
        exact = [tag for tag in self.ordered if self.tags[tag] == commit]
        code, out = _git(["tag", "--contains", commit, "--list", "v*"], self.root)
        containing = {tag for tag in out.splitlines() if tag in self.tags} if code == 0 else set()
        newer = [tag for tag in self.ordered if tag in containing and self.tags[tag] != commit]
        if exact:
            return f"{exact[-1]} ({ref[:7]})", len(newer)
        if newer:
            return f"{ref[:7]} (before {newer[0]})", len(newer)
        return f"{ref[:7]} (after {self.latest})", 0


def scan_repository(repo: Path) -> list[Pin]:
    code, out = _git(["ls-files", "-z"], repo)
    if code:
        return []
    pins: list[Pin] = []
    for relative in out.split("\0"):
        if Path(relative).name not in MANIFEST_NAMES:
            continue
        try:
            text = (repo / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if COREKIT in text:
            pins.extend(parse_pins(relative, text))
    return pins


def report(workspace_root: Path, corekit_root: Path) -> str:
    releases = Releases(corekit_root)
    rows: list[tuple[str, str, str, str, str]] = []
    warnings: list[str] = []
    for repo in sorted(workspace_root.glob("symaira-*")):
        if repo.resolve() == corekit_root.resolve() or not (repo / ".git").exists():
            continue
        identities: set[str] = set()
        for pin in scan_repository(repo):
            identity, newer = releases.resolve(pin.ref)
            identities.add(identity.split(" (")[0] if identity.startswith("v") else identity)
            status = "unknown" if newer is None else ("current" if newer == 0 else f"{newer} release(s) behind")
            if pin.kind.startswith("cargo") and pin.kind != "cargo tag":
                status += "; Dependabot cannot bump"
            rows.append((repo.name, pin.path, pin.kind, identity, status))
        if len(identities) > 1:
            warnings.append(f"{repo.name} mixes {len(identities)} CoreKit pins: {', '.join(sorted(identities))}")
    header = ("REPO", "FILE", "KIND", "PIN", "STATUS")
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(len(header))]
    lines = [f"CoreKit latest release: {releases.latest}", ""]
    lines += ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip() for row in [header, *rows]]
    if not rows:
        lines.append(f"no CoreKit pins found in symaira-* checkouts below {workspace_root}")
    if warnings:
        lines += ["", *(f"warning: {warning}" for warning in warnings)]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--corekit-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        sys.stdout.write(report(args.workspace_root.resolve(), args.corekit_root.resolve()))
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
