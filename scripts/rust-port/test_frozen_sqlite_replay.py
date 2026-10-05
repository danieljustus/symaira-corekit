"""Prove mutation rejection against the actual native SQLite registration."""
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest

from frozen_sqlite_anchors import CAPTURES

ROOT = Path(__file__).resolve().parents[2]


class FrozenSqliteReplayTests(unittest.TestCase):
    def test_original_mutated_restored_fixture_uses_the_real_cli(self):
        goos = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}[platform.system()]
        goarch = {"arm64": "arm64", "aarch64": "arm64", "amd64": "amd64", "x86_64": "amd64"}[platform.machine().lower()]
        row = CAPTURES[goos + "-" + goarch]
        original = (ROOT / row["report"]).read_bytes()
        with tempfile.TemporaryDirectory(prefix="sqlite-frozen-mutation-") as directory:
            fixture = Path(directory) / "fixture.json"
            command = [sys.executable, str(ROOT / "scripts/rust-port/frozen_sqlite_replay.py"), "--fixture", str(fixture)]
            fixture.write_bytes(original)
            clean = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(clean.returncode, 0, clean.stderr)
            fixture.write_bytes(original + b"\n")
            negative = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(negative.returncode, 1, negative.stdout + negative.stderr)
            self.assertIn("fixed reviewed anchor", negative.stderr)
            fixture.write_bytes(original)
            restored = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(restored.returncode, 0, restored.stderr)


if __name__ == "__main__":
    unittest.main()
