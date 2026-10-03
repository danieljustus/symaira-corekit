"""Regression controls for native extraction replay and Apply temp isolation."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


def load(name):
    path = Path(__file__).with_name(name + "-differential.py")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UpdateHarnessTests(unittest.TestCase):
    def test_extraction_negative_requires_native_rust_assertion(self):
        entry = load("update-extract")
        module = sys.modules[entry.main_for_lane.__module__]
        native = module.oracle.fixture_path("extract")
        assertion = "tar-success content"
        failed = "test result: FAILED"
        controls = (
            (101, assertion + "\n" + failed, True),
            (0, "", False),
            (101, "compile failed", False),
            (101, assertion, False),
            (101, failed, False),
        )
        for status, output, accepted in controls:
            with self.subTest(status=status, output=output):
                def replay(lane, candidate, filter_name=None):
                    self.assertEqual(lane, "extract")
                    self.assertIsNone(filter_name)
                    if candidate == native:
                        return subprocess.CompletedProcess(
                            [], 0, stdout="test result: ok. 2 passed; 0 failed; 0 ignored;"
                        )
                    mutated = json.loads(candidate.read_bytes())
                    self.assertEqual(mutated["cases"][0]["files"][0]["content"], "mutated")
                    return subprocess.CompletedProcess([], status, stdout=output)
                with patch.dict(os.environ, {"GO_ORACLE": "0"}), patch.object(module, "_rust", side_effect=replay) as runner:
                    if accepted:
                        self.assertEqual(entry.main_for_lane("extract", ["--negative-control"]), 0)
                    else:
                        with self.assertRaises(RuntimeError):
                            entry.main_for_lane("extract", ["--negative-control"])
                    self.assertEqual(runner.call_count, 2)

    def test_apply_real_oracle_ignores_parent_temp_contamination(self):
        module = load("update-apply")
        with tempfile.TemporaryDirectory(prefix="update-harness-parent-") as directory:
            parent = Path(directory)
            with patch.dict(os.environ, {name: directory for name in ("TMPDIR", "TMP", "TEMP")}), patch.object(tempfile, "tempdir", directory):
                clean = module.observed()
                sentinel = parent / "updateapply-unrelated-regression"
                sentinel.write_text("preserve", encoding="utf-8")
                contaminated = module.observed()
                self.assertEqual(clean, contaminated)
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")
                self.assertFalse(list(parent.glob("update-apply-run-*")))
                fixture = json.loads(module.FIXTURE.read_text(encoding="utf-8"))
                if fixture["goos"] == clean["goos"]:
                    self.assertEqual(clean, fixture)
                self.assertTrue(any(row["observation"]["stage_during_download"] for row in clean["cases"]))
                self.assertTrue(all("temp_during_download" in row["observation"] for row in clean["cases"]))


if __name__ == "__main__":
    unittest.main()
