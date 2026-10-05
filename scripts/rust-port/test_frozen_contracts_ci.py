"""Actual shared-bin PATH isolation must preserve tools while removing Go."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from frozen_contracts_ci import path_without_go


class AggregatePathTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "Unix shared system-bin regression")
    def test_shared_bin_preserves_actual_shell_execution_but_hides_go(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            original = root / "shared-bin"
            original.mkdir()
            (original / "go").symlink_to(shutil.which("sh"))
            (original / "gofmt").symlink_to(shutil.which("sh"))
            (original / "sh").symlink_to(shutil.which("sh"))
            view = root / "view"
            view.mkdir()
            filtered = path_without_go(str(original), view)
            self.assertIsNone(shutil.which("go", path=filtered))
            self.assertIsNone(shutil.which("gofmt", path=filtered))
            result = subprocess.run(["sh", "-c", "printf preserved"], env=dict(os.environ, PATH=filtered), capture_output=True, check=True)
            self.assertEqual(result.stdout, b"preserved")


if __name__ == "__main__":
    unittest.main()
