"""Guard the actual registered corpus against mutation and inventory drift."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import frozen_core_replay as replay


class FrozenCoreReplayTests(unittest.TestCase):
    def test_actual_registered_fixture_mutation_restoration_and_extra_file(self):
        family = replay.FAMILIES["foundation"]
        relative = next(iter(family["files"]))
        original = (replay.ROOT / relative).read_bytes()
        base = Path(relative).parent.as_posix()
        specification = dict(family, files={relative: family["files"][relative]}, directories={base: 1})
        with tempfile.TemporaryDirectory(prefix="frozen-core-corpus-") as directory:
            root = Path(directory).resolve()
            fixture = root / relative
            fixture.parent.mkdir(parents=True)
            fixture.write_bytes(original)
            with patch.object(replay, "ROOT", root), patch.dict(replay.FAMILIES, {"foundation": specification}):
                replay.verify_family("foundation")
                fixture.write_bytes(original + b"\n")
                with self.assertRaisesRegex(ValueError, "byte mismatch"), patch.object(replay, "run_checked") as run:
                    replay.run_rust("foundation")
                run.assert_not_called()
                fixture.write_bytes(original)
                replay.verify_family("foundation")
                (fixture.parent / "extra.json").write_text("{}")
                with self.assertRaisesRegex(ValueError, "inventory drift"):
                    replay.verify_family("foundation")

    def test_all_actual_families_verify_without_processes(self):
        with patch.object(replay, "run_checked") as run:
            for family in replay.FAMILIES:
                replay.verify_family(family)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
