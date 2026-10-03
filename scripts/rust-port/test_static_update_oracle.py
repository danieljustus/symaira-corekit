#!/usr/bin/env python3
"""Regression checks for native Go-free update-oracle replay metadata."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import static_update_oracle as oracle  # noqa: E402
import update_static_runner as runner  # noqa: E402


class StaticUpdateOracleTests(unittest.TestCase):
    def test_committed_native_slices_have_consistent_case_inventories(self):
        for lane in ("version", "response", "install-method", "extract"):
            with self.subTest(lane=lane):
                record = oracle.validate_capture(lane)
                ids = oracle._case_ids(lane, record)
                self.assertEqual(len(ids), oracle.LANES[lane]["count"])
                self.assertEqual(len(set(ids)), len(ids))
                self.assertEqual(record["capture"]["case_count"], len(ids))
                self.assertEqual(record["capture"]["case_ids"], ids)
                self.assertEqual(record["capture"]["go"]["version"], "go version go1.26.6 darwin/arm64")
                self.assertFalse(record["capture"]["working_tree_clean"])

    def test_swap_requires_exact_original_eight_case_inventory(self):
        expected = [
            "missing-source",
            "validation-rollback",
            "validation-first-install",
            "preexisting-backup",
            "validation-rollback-failed",
            "validation-remove-failed",
            "validation-remove-failed-existing",
            "backup-cleanup-failed",
        ]
        self.assertEqual(oracle.LANES["swap"]["expected_case_ids"], expected)
        old_candidate = ROOT / "target/static-update-candidates/swap-darwin-arm64.json"
        self.assertTrue(old_candidate.is_file(), "retain the actual six-case capture as diagnostic evidence")
        record = oracle.json.loads(old_candidate.read_text(encoding="utf-8"))
        observed = oracle._case_ids("swap", record)
        self.assertEqual(
            observed,
            [
                "missing-source",
                "validation-rollback",
                "validation-first-install",
                "preexisting-backup",
                "validation-rollback-failed",
                "validation-remove-failed",
            ],
        )
        self.assertEqual([case for case in expected if case not in observed], [
            "validation-remove-failed-existing",
            "backup-cleanup-failed",
        ])
        index = oracle.json.loads(oracle.INDEX.read_text(encoding="utf-8"))
        self.assertNotIn("swap", index["captures"], "six cases must not be registered as the eight-case lane")
        self.assertFalse(oracle.fixture_path("swap").exists())
        with self.assertRaisesRegex(ValueError, "candidate swap case inventory is invalid"):
            oracle.register(old_candidate)

    def test_swap_static_replay_fails_closed_when_native_capture_is_absent(self):
        with self.assertRaisesRegex(ValueError, "missing native swap Go capture for darwin/arm64"):
            oracle.validate_capture("swap")
        self.assertFalse(oracle.fixture_path("version", target=("linux", "amd64")).exists())

    def test_swap_retains_three_assertion_mutation_controls(self):
        ids = oracle.LANES["swap"]["expected_case_ids"]
        source = {
            "cases": [
                {
                    "input": {"id": case_id},
                    "observation": {
                        "target_content": "original",
                        "error_prefix": "original error family",
                        "backup_exists": True,
                    },
                }
                for case_id in ids
            ]
        }
        mutations = runner._mutations("swap", source)
        self.assertEqual(
            [marker for _, marker in mutations],
            [
                "missing-source observation",
                "validation-rollback-failed error family",
                "backup-cleanup-failed observation",
            ],
        )
        self.assertNotEqual(mutations[0][0]["cases"][0]["observation"]["target_content"], "original")
        self.assertEqual(
            mutations[1][0]["cases"][4]["observation"]["error_prefix"],
            "wrong rollback error family",
        )
        self.assertFalse(mutations[2][0]["cases"][7]["observation"]["backup_exists"])


if __name__ == "__main__":
    unittest.main()
