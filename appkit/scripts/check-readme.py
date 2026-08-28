#!/usr/bin/env python3
"""Validate README version pins and compile every Swift example block."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"


def latest_release_version(changelog: str) -> str:
    match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.MULTILINE)
    if not match:
        raise SystemExit("No released SemVer entry found in CHANGELOG.md")
    return match.group(1)


def readme_pin(readme: str) -> str:
    matches = re.findall(r'exact:\s*"(\d+\.\d+\.\d+)"', readme)
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one exact package pin, found {len(matches)}")
    return matches[0]


def swift_package_manifest() -> str:
    package_path = ROOT.as_posix().replace('\\', '\\\\').replace('"', '\\"')
    return f'''// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "READMEExamples",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(path: "{package_path}"),
    ],
    targets: [
        .executableTarget(
            name: "ToolKitExample",
            dependencies: [
                .product(name: "SymairaCLIRunner", package: "symaira-appkit"),
                .product(name: "SymairaToolKit", package: "symaira-appkit"),
            ]
        ),
        .executableTarget(
            name: "UpdateCheckExample",
            dependencies: [.product(name: "SymairaUpdateCheck", package: "symaira-appkit")]
        ),
        .executableTarget(
            name: "ThemeExample",
            dependencies: [.product(name: "SymairaTheme", package: "symaira-appkit")]
        ),
    ]
)
'''


def main() -> int:
    readme = README.read_text(encoding="utf-8")
    changelog = CHANGELOG.read_text(encoding="utf-8")

    expected = latest_release_version(changelog)
    actual = readme_pin(readme)
    if actual != expected:
        raise SystemExit(
            f"README exact pin {actual} does not match latest release {expected}"
        )

    all_blocks = re.findall(r"```swift\n(.*?)```", readme, re.DOTALL)
    blocks = [
        block
        for block in all_blocks
        if re.search(r"^\s*import\s+", block, re.MULTILINE)
    ]
    if not blocks:
        raise SystemExit("No Swift code blocks found in README.md")

    if shutil.which("swift") is None:
        raise SystemExit("swift executable is required to compile README examples")

    preambles = [
        "struct SearchResults: Decodable {}",
        "",
        "",
    ]
    if len(blocks) != len(preambles):
        raise SystemExit(
            f"README Swift block count changed: expected {len(preambles)}, found {len(blocks)}"
        )

    with tempfile.TemporaryDirectory(prefix="symaira-readme-check-") as temp_dir:
        package = Path(temp_dir)
        (package / "Package.swift").write_text(
            swift_package_manifest(), encoding="utf-8"
        )
        for target, preamble, block in zip(
            ("ToolKitExample", "UpdateCheckExample", "ThemeExample"),
            preambles,
            blocks,
        ):
            source_dir = package / "Sources" / target
            source_dir.mkdir(parents=True)
            (source_dir / "main.swift").write_text(
                f"{preamble}\n\n{block}", encoding="utf-8"
            )

        result = subprocess.run(
            ["swift", "build", "--package-path", str(package)],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit("README Swift example compilation failed")

    print(f"README checks passed: exact pin {actual}; compiled {len(blocks)} Swift blocks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
