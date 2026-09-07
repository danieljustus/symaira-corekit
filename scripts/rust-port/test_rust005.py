#!/usr/bin/env python3
"""Focused RUST-005 validator negative controls."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    path = ROOT / "scripts" / "rust-port" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Rust005NegativeControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adoption = load("adoption")
        cls.bench = load("bench")
        spec = importlib.util.spec_from_file_location("rust_port_validate", ROOT / "docs/rust-port/validate.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load docs/rust-port/validate.py")
        cls.validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.validator)

    def test_one_consumer_fails_minimum(self):
        with self.assertRaises(ValueError):
            self.adoption.validate_minimum([{"repository": "one/consumer"}], 2)

    def test_metric_regression_fails_ten_percent_ceiling(self):
        measurement = {"repository": "one/consumer", "maximum_regression_ratio": 1.100001}
        self.assertEqual(len(self.bench.check_regressions([measurement])), 1)

    def test_build_distributions_are_reported_but_not_in_perf_001_ceiling(self):
        ratios = {
            "binary_size_bytes": 0.5,
            "startup_p95_ms": 0.8,
            "peak_rss_median_bytes": 0.7,
            "clean_build_ms": 2.0,
            "warm_build_ms": 1.5,
        }
        maximum = max(ratios[name] for name in self.bench.REGRESSION_GATED_METRICS)
        self.assertLessEqual(maximum, 1.1)

    def test_script_self_test_covers_pin_path_and_lock_controls(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/rust-port/adoption.py"), "--self-test"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("manipulated pin", completed.stdout)

    def test_gate_summary_is_bound_to_benchmark(self):
        benchmark = {
            "measurements": [{"repository": "one/repo", "workload": "version --json", "baseline_commit": "1" * 40, "candidate_commit": "2" * 40, "runs": 50, "maximum_regression_ratio": 0.5}],
            "standalone_smokes": [{"repository": "one/repo", "passed": True}],
        }
        metrics = [dict(benchmark["measurements"][0])]
        smokes = [{"repository": "one/repo", "passed": True}]
        self.validator.validate_gate_benchmark_binding(metrics, smokes, benchmark)
        metrics[0]["repository"] = "fabricated/repo"
        with self.assertRaises(ValueError):
            self.validator.validate_gate_benchmark_binding(metrics, smokes, benchmark)

    def test_integrity_digest_normalizes_windows_line_endings(self):
        with tempfile.TemporaryDirectory() as raw:
            lf = Path(raw) / "lf.txt"
            crlf = Path(raw) / "crlf.txt"
            lf.write_bytes(b"one\ntwo\n")
            crlf.write_bytes(b"one\r\ntwo\r\n")
            self.assertEqual(self.validator.integrity_digest(lf), self.validator.integrity_digest(crlf))


if __name__ == "__main__":
    unittest.main()
