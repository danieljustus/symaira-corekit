"""Synthetic fail-closed controls for the SQL-006 cost gate."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("sql006_cost_gate", HERE / "cost_gate.py")
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


class Sql006CostGateTests(unittest.TestCase):
    def test_p95_uses_95th_percentile_rank_for_ten_samples(self):
        self.assertEqual(gate.p95([float(value) for value in range(10)]), 9.0)

    def test_self_test_runs_without_cargo(self):
        result = subprocess.run(
            [sys.executable, str(HERE / "cost_gate.py"), "--self-test"],
            cwd=HERE.parents[3],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("wrong pin", result.stdout)

    def test_frozen_matrix_has_two_consumers_and_four_cells(self):
        self.assertEqual({item["name"] for item in gate.CONTRACT["consumers"]}, {"desktop", "eraseme"})
        self.assertEqual(len(gate.CONTRACT["consumers"]) * len(gate.CONTRACT["modes"]), 4)
        self.assertEqual(gate.CONTRACT["samples_per_cell"] * 4 * 2, 80)


if __name__ == "__main__":
    unittest.main()
