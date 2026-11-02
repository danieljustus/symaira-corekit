"""Retired Go sources resolve from the immutable v0.18.3 anchor, tree first."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import retired_go


class RetiredGoTests(unittest.TestCase):
    def test_anchor_is_the_v0_18_3_tag_commit(self):
        tagged = subprocess.run(
            ["git", "rev-parse", f"{retired_go.ANCHOR_TAG}^{{commit}}"],
            cwd=retired_go.REPO, check=True, stdout=subprocess.PIPE, text=True,
        ).stdout.strip()
        self.assertEqual(tagged, retired_go.ANCHOR_COMMIT)

    def test_working_tree_has_no_retired_library_sources(self):
        tracked = subprocess.run(
            ["git", "ls-files", "--", "*.go", "go.mod", "go.sum"],
            cwd=retired_go.REPO, check=True, stdout=subprocess.PIPE, text=True,
        ).stdout.split()
        self.assertEqual([p for p in tracked if not p.startswith("scripts/rust-port/")], [])

    def test_absent_go_path_reads_anchor_and_present_path_wins(self):
        relative = "versionkit/versionkit.go"
        anchor = retired_go.anchor_blob(relative)
        self.assertIn(b"package versionkit", anchor)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(retired_go.read_bytes(root, relative), anchor)
            self.assertTrue(retired_go.exists(root, relative))
            (root / relative).parent.mkdir(parents=True)
            (root / relative).write_bytes(anchor + b"\n")
            self.assertEqual(retired_go.read_bytes(root, relative), anchor + b"\n")

    def test_traversal_absolute_and_symlink_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "root"
            root.mkdir()
            outside = base / "outside.go"
            outside.write_bytes(b"package outside\n")
            for bad in ("../outside.go", str(outside), "a//b.go", "./x.go", "a\\b.go", ""):
                with self.assertRaises(ValueError, msg=bad):
                    retired_go.read_bytes(root, bad)
                with self.assertRaises(ValueError, msg=bad):
                    retired_go.exists(root, bad)
            (root / "versionkit").mkdir()
            dangling = root / "versionkit/versionkit.go"
            dangling.symlink_to(base / "missing.go")
            with self.assertRaises(ValueError):
                retired_go.read_bytes(root, "versionkit/versionkit.go")
            with self.assertRaises(ValueError):
                retired_go.exists(root, "versionkit/versionkit.go")
            dangling.unlink()
            (root / "linked").symlink_to(base, target_is_directory=True)
            with self.assertRaises(ValueError):
                retired_go.read_bytes(root, "linked/outside.go")

    def test_unknown_or_non_go_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertFalse(retired_go.exists(root, "versionkit/missing.go"))
            with self.assertRaises(FileNotFoundError):
                retired_go.read_bytes(root, "versionkit/missing.go")
            with self.assertRaises(FileNotFoundError):
                retired_go.read_bytes(root, "README.txt")
            with self.assertRaises(ValueError):
                retired_go.anchor_blob("../outside.go")


if __name__ == "__main__":
    unittest.main()
