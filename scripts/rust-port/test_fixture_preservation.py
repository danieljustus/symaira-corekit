"""Exercise the real pinned Go generator only in disposable fixture trees."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings


SPEC = importlib.util.spec_from_file_location("fixture_generator", Path(__file__).with_name("generate.py"))
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class FixturePreservationTest(unittest.TestCase):
    def test_real_regeneration_preserves_independent_corpora(self):
        with tempfile.TemporaryDirectory(prefix="corekit-preservation path-") as raw:
            root = Path(raw)
            fixtures = root / "fixtures"
            local_foundation = root / "local" / "foundation"
            original = {}
            for family in ("fs-secret", "llm", "update"):
                source = GENERATOR.FIXTURES / family
                paths = [path for path in source.rglob("*") if path.is_file()]
                self.assertTrue(paths, f"missing real {family} oracle corpus")
                shutil.copytree(source, fixtures / family)
                original.update({path.relative_to(GENERATOR.FIXTURES): path.read_bytes() for path in paths})
            (fixtures / "public-api.json").write_bytes(b"deliberate stale owned artifact")
            with patch.object(GENERATOR, "FIXTURES", fixtures), patch.object(
                GENERATOR, "LOCAL_FOUNDATION", local_foundation
            ), patch.object(sys, "argv", ["generate.py"]), contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always", ResourceWarning)
                self.assertEqual(GENERATOR.main(), 0)
            self.assertFalse([str(item.message) for item in captured if issubclass(item.category, ResourceWarning)])
            for relative, content in original.items():
                self.assertTrue((fixtures / relative).is_file(), f"independent fixture removed: {relative}")
                self.assertEqual((fixtures / relative).read_bytes(), content, str(relative))
            index = json.loads((fixtures / "index.json").read_text())
            self.assertEqual(index["oracle"]["commit"], GENERATOR.ORACLE_COMMIT)
            self.assertEqual(len(index["public_api"]["targets"]), 6)
            self.assertGreater(index["oracle"]["source_files"], 0)
            GENERATOR.compare_trees(fixtures / "foundation", local_foundation)
            expected = root / "expected"
            expected.mkdir()
            owned = fixtures / "oracle-probe.json"
            shutil.copy2(owned, expected / owned.name)
            GENERATOR.compare_tree_subset(expected, fixtures)
            owned.write_bytes(owned.read_bytes() + b"\ncontrolled owned-fixture drift")
            with self.assertRaisesRegex(RuntimeError, "fixture drift: oracle-probe.json"):
                GENERATOR.compare_tree_subset(expected, fixtures)


if __name__ == "__main__":
    unittest.main()
