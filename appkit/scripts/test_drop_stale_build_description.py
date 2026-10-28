#!/usr/bin/env python3
"""Regression tests for dropping a stale Metal toolchain build description."""

from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from drop_stale_build_description import main  # noqa: E402

OLD = "com.apple.MobileAsset.MetalToolchain-v27.1.266.1.QhORso"
NEW = "com.apple.MobileAsset.MetalToolchain-v27.1.266.1.Aii2TR"


class DropStaleBuildDescriptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.build = root / ".build"
        self.description = self.build / "out" / "Intermediates.noindex" / "XCBuildData"
        self.objects = self.build / "out" / "Products"
        self.mounts = root / "mnt"
        for directory in (self.description / "a.xcbuilddata", self.objects, self.mounts):
            directory.mkdir(parents=True)
        (self.objects / "Kept.o").write_bytes(b"object")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_tool(self) -> str:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--build-dir", str(self.build), "--mount-root", str(self.mounts)]), 0)
        return output.getvalue()

    def describe(self, toolchain: str) -> None:
        payload = f"\x00/var/run/com.apple.security.cryptexd/mnt/{toolchain}/Metal.xctoolchain/usr/bin/metal\x01"
        (self.description / "a.xcbuilddata" / "task-store.msgpack").write_bytes(payload.encode())

    def test_removes_description_for_unmounted_toolchain(self) -> None:
        self.describe(OLD)
        (self.mounts / NEW).mkdir()
        self.assertIn(OLD, self.run_tool())
        self.assertFalse(self.description.exists())
        self.assertTrue((self.objects / "Kept.o").exists())

    def test_keeps_description_for_mounted_toolchain(self) -> None:
        self.describe(NEW)
        (self.mounts / NEW).mkdir()
        self.run_tool()
        self.assertTrue(self.description.exists())

    def test_keeps_description_without_metal_references(self) -> None:
        (self.description / "a.xcbuilddata" / "manifest.json").write_text("{}")
        self.run_tool()
        self.assertTrue(self.description.exists())

    def test_missing_build_directory_is_a_no_op(self) -> None:
        self.temp_dir.cleanup()
        self.assertIn("none exists", self.run_tool())


if __name__ == "__main__":
    unittest.main()
