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
        root = Path(tempfile.mkdtemp())
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

    def test_rev_pin_is_an_error_even_with_fix(self):
        root = self.make_repo({"Cargo.toml": CARGO.replace('tag = "v0.26.0"', f'rev = "{"b" * 40}"')})
        code, out = self.run_tool(root, "--fix")
        self.assertEqual(code, 1)
        self.assertIn("not a release tag", out)


if __name__ == "__main__":
    unittest.main()
