"""Regression check for corekit_pins.py: the two files Dependabot leaves stale."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import corekit_pins  # noqa: E402

URL = "https://github.com/danieljustus/symaira-corekit"
SPEC = f"packages:\n  symaira-corekit:\n    url: {URL}.git\n    exactVersion: 0.26.0\n"
PBX = (
    f'repositoryURL = "{URL}.git";\n\t\t\trequirement = {{\n'
    "\t\t\t\tkind = exactVersion;\n\t\t\t\tversion = 0.27.0;\n"
)
CARGO = f'[workspace.dependencies]\nsymaira-core-llm = {{ git = "{URL}", tag = "v0.26.0", version = "=0.0.0" }}\n'
LOCK = f'source = "git+{URL}?tag=v0.27.0#{"a" * 40}"\n'


class CorekitPinsTest(unittest.TestCase):
    def run_tool(self, root, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = corekit_pins.main(["--root", str(root), *args])
        return code, out.getvalue()

    def make_repo(self, files):
        root = Path(tempfile.mkdtemp()).resolve()  # macOS: /var -> /private/var
        for name, body in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(body)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        return root

    def test_fix_copies_dependabot_version_into_stale_files(self):
        root = self.make_repo({
            "project.yml": SPEC,
            "App.xcodeproj/project.pbxproj": PBX,
            "Cargo.toml": CARGO,
            "Cargo.lock": LOCK,
        })
        code, out = self.run_tool(root)
        self.assertEqual(code, 1, out)
        code, out = self.run_tool(root, "--fix")
        self.assertEqual(code, 0, out)
        self.assertIn("exactVersion: 0.27.0", (root / "project.yml").read_text())
        self.assertIn('tag = "v0.27.0"', (root / "Cargo.toml").read_text())
        self.assertEqual(self.run_tool(root)[0], 0)

    def test_fix_raises_a_root_manifest_behind_its_local_package(self):
        # cockpit: Package.swift depends on .package(path: "tuning"); Dependabot
        # can bump only tuning/, so the root manifest and Package.resolved lag.
        manifest = '.package(url: "{0}.git", exact: "{1}"),\n.package(path: "tuning"),\n'
        resolved = (
            '{\n  "pins" : [\n    {\n      "identity" : "symaira-corekit",\n'
            f'      "location" : "{URL}.git",\n      "state" : {{\n'
            f'        "revision" : "{"a" * 40}",\n        "version" : "0.27.0"\n'
            "      }\n    }\n  ],\n  \"version\" : 3\n}\n"
        )
        root = self.make_repo({
            "Package.swift": manifest.format(URL, "0.27.0"),
            "Package.resolved": resolved,
            "tuning/Package.swift": manifest.format(URL, "0.27.1"),
        })
        self.assertEqual(self.run_tool(root)[0], 1)
        original = corekit_pins.tag_revision
        corekit_pins.tag_revision = lambda version: "c" * 40
        try:
            code, out = self.run_tool(root, "--fix")
        finally:
            corekit_pins.tag_revision = original
        self.assertEqual(code, 0, out)
        self.assertIn('exact: "0.27.1"', (root / "Package.swift").read_text())
        body = (root / "Package.resolved").read_text()
        self.assertIn('"version" : "0.27.1"', body)
        self.assertIn(f'"revision" : "{"c" * 40}"', body)
        self.assertIn('"version" : 3', body)  # file format version untouched
        self.assertEqual(self.run_tool(root)[0], 0)

    def test_fix_completes_a_partly_moved_lock_and_the_fuzz_lock(self):
        # desktop #1412: Dependabot moved one of the workspace crates in
        # Cargo.lock and left Cargo.toml and fuzz/Cargo.lock on the old tag.
        def lock(*tags):
            return "".join(f'source = "git+{URL}?tag={t}#{"a" * 40}"\n' for t in tags)
        root = self.make_repo({
            "Cargo.toml": CARGO.replace("v0.26.0", "v0.27.0"),
            "Cargo.lock": lock("v0.27.1", "v0.27.0"),
            "fuzz/Cargo.toml": '[dependencies]\ncore = { path = "../crates/core" }\n',
            "fuzz/Cargo.lock": lock("v0.27.0"),
        })
        self.assertEqual(self.run_tool(root)[0], 1)
        refreshed = []
        def fake_refresh(manifest):  # what `cargo metadata` does to the lock
            refreshed.append(manifest.relative_to(root).as_posix())
            lockfile = manifest.with_name("Cargo.lock")
            lockfile.write_text(lockfile.read_text().replace("v0.27.0", "v0.27.1"))
        original = corekit_pins.refresh_lock
        corekit_pins.refresh_lock = fake_refresh
        try:
            code, out = self.run_tool(root, "--fix")
        finally:
            corekit_pins.refresh_lock = original
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(refreshed), ["Cargo.toml", "fuzz/Cargo.toml"])
        self.assertIn('tag = "v0.27.1"', (root / "Cargo.toml").read_text())
        self.assertEqual(self.run_tool(root)[0], 0)

    def test_rev_pin_is_an_error_even_with_fix(self):
        root = self.make_repo({"Cargo.toml": CARGO.replace('tag = "v0.26.0"', f'rev = "{"b" * 40}"')})
        code, out = self.run_tool(root, "--fix")
        self.assertEqual(code, 1)
        self.assertIn("not a release tag", out)


if __name__ == "__main__":
    unittest.main()
