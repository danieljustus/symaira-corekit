#!/usr/bin/env python3
"""Regression tests for CI Xcode selection."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess

sys.path.insert(0, str(Path(__file__).parent))
from select_xcode import MIN_XCODE, installed_candidates, select_xcode  # noqa: E402


class SelectXcodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.old = root / "Xcode-26.0.app"
        self.new = root / "Xcode-26.6.app"
        for app in (self.old, self.new):
            (app / "Contents" / "Developer").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def runner(*args, **kwargs) -> CompletedProcess[str]:
        developer_dir = kwargs["env"]["DEVELOPER_DIR"]
        version = "26.0" if "26.0" in developer_dir else "26.6"
        return CompletedProcess(args[0], 0, f"Xcode {version}\nBuild version test\n", "")

    def test_selects_highest_supported_version(self) -> None:
        self.assertEqual(select_xcode([self.old, self.new], self.runner), self.new / "Contents" / "Developer")

    def test_rejects_when_no_supported_toolchain_is_installed(self) -> None:
        def unsupported(*args, **kwargs):
            return CompletedProcess(args[0], 0, "Xcode 15.4\n", "")

        with self.assertRaises(RuntimeError):
            select_xcode([self.old], unsupported)

    def test_swift_62_requirement_can_require_xcode_26(self) -> None:
        def xcode_25(*args, **kwargs):
            return CompletedProcess(args[0], 0, "Xcode 25.4\n", "")

        with self.assertRaises(RuntimeError):
            select_xcode([self.old], xcode_25, minimum=(26, 0))

    def test_minimum_matches_swift_62_coverage_requirement(self) -> None:
        self.assertEqual(MIN_XCODE, (26, 0))

    def test_invalid_explicit_developer_dir_fails_closed(self) -> None:
        invalid = str(Path(self.temp_dir.name) / "missing" / "Contents" / "Developer")
        old = os.environ.get("DEVELOPER_DIR")
        os.environ["DEVELOPER_DIR"] = invalid
        self.addCleanup(self._restore_developer_dir, old)

        with self.assertRaises(RuntimeError):
            installed_candidates()

    def _restore_developer_dir(self, value: str | None) -> None:
        if value is None:
            os.environ.pop("DEVELOPER_DIR", None)
        else:
            os.environ["DEVELOPER_DIR"] = value


if __name__ == "__main__":
    unittest.main()
