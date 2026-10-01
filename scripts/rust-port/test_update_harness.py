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
        module = load("update-extract")
        fixture = json.loads(module.FIXTURE.read_text(encoding="utf-8"))
        native = json.loads(json.dumps(fixture))
        native["goos"] = module.goos_name()
        assertion = native["cases"][0]["id"] + " content"
        for recorded in (native, dict(fixture, goos="foreign")):
            for status, output, accepted in ((101, assertion, True), (0, "", False), (101, "compile failed", False)):
                with self.subTest(goos=recorded["goos"], status=status, output=output):
                    with tempfile.TemporaryDirectory() as directory:
                        path = Path(directory) / "fixture.json"
                        path.write_text(json.dumps(recorded), encoding="utf-8")
                        def replay(candidate):
                            mutated = json.loads(candidate.read_text(encoding="utf-8"))
                            self.assertEqual(mutated["goos"], module.goos_name())
                            self.assertEqual(mutated["cases"][0]["files"][0]["content"], "mutated")
                            return subprocess.CompletedProcess([], status, stdout=output)
                        with patch.object(sys, "argv", ["test", "--negative-control", "--fixture", str(path)]), patch.object(module, "live_observation", return_value=native), patch.object(module, "replay", side_effect=replay) as runner:
                            if accepted:
                                self.assertEqual(module.main(), 0)
                            else:
                                with self.assertRaises(RuntimeError):
                                    module.main()
                            runner.assert_called_once()

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
