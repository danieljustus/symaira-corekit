"""Checks for the read-only CoreKit pin inventory (drift.py)."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import drift  # noqa: E402

URL = "https://github.com/danieljustus/symaira-corekit"


def git(cwd: Path, *args: str) -> str:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


class ParsePinsTest(unittest.TestCase):
    def test_every_manifest_kind(self) -> None:
        cases = {
            "Cargo.toml": (f'a = {{ git = "{URL}", rev = "{"a" * 40}", version = "=0.0.0" }}\n'
                           f'b = {{ version = "=0.0.0", git = "{URL}", tag = "v0.23.0" }}\n', [("cargo rev", "a" * 40), ("cargo tag", "0.23.0")]),
            "Package.swift": (f'.package(url: "{URL}.git", exact: "0.22.4"),\n', [("swiftpm exact", "0.22.4")]),
            "project.yml": (f"packages:\n  symaira-corekit:\n    url: {URL}.git\n    # pinned\n    exactVersion: 0.20.0\n", [("xcodegen exactVersion", "0.20.0")]),
            "project.pbxproj": (f'repositoryURL = "{URL}.git";\nrequirement = {{\nkind = exactVersion;\nversion = 0.20.0;\n}};\n', [("xcode version", "0.20.0")]),
            "Package.resolved": ('{"pins":[{\n"identity" : "symaira-corekit",\n"state" : {\n"revision" : "' + "b" * 40 + '",\n"version" : "0.22.4"\n}}]}\n', [("resolved", "0.22.4")]),
            "go.mod": ("require github.com/danieljustus/symaira-corekit v0.17.0\n", [("go", "0.17.0")]),
        }
        for name, (text, expected) in cases.items():
            with self.subTest(name=name):
                self.assertEqual([(pin.kind, pin.ref) for pin in drift.parse_pins(f"dir/{name}", text)], expected)

    def test_unrelated_git_dependency_is_ignored(self) -> None:
        self.assertEqual(drift.parse_pins("Cargo.toml", 'x = { git = "https://github.com/other/repo", rev = "abc" }\n'), [])


class ResolveTest(unittest.TestCase):
    def test_versions_revisions_and_annotated_tag_objects(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            git(root, "init", "-q")
            commits = []
            for tag in ("v0.1.0", "v0.2.0", "v0.10.0"):
                git(root, "commit", "-q", "--allow-empty", "-m", tag)
                commits.append(git(root, "rev-parse", "HEAD"))
                git(root, "tag", "-a", tag, "-m", tag)
            git(root, "commit", "-q", "--allow-empty", "-m", "unreleased")
            unreleased = git(root, "rev-parse", "HEAD")
            tag_object = git(root, "rev-parse", "v0.2.0")
            releases = drift.Releases(root)
            self.assertEqual(releases.latest, "v0.10.0")  # numeric, not lexical order
            self.assertEqual(releases.resolve("0.1.0"), ("v0.1.0", 2))
            self.assertEqual(releases.resolve(commits[1])[1], 1)
            self.assertTrue(releases.resolve(tag_object)[0].startswith("v0.2.0"))
            self.assertEqual(releases.resolve(unreleased)[1], 0)
            self.assertIsNone(releases.resolve("f" * 40)[1])


if __name__ == "__main__":
    unittest.main()
