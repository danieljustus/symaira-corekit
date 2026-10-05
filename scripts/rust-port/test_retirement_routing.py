"""Terminal consumer-local decisions must never masquerade as shared parity."""
import copy
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "retirement_validator", ROOT / "docs/rust-port/validate.py"
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class RetirementRoutingTests(unittest.TestCase):
    def test_completed_native_work_preserves_explicit_release_blockers(self):
        work_doc = VALIDATOR.load("work-items.json")
        work = {item["id"]: item for item in work_doc["items"]}
        contracts = {row["id"]: row for row in VALIDATOR.load("contract-matrix.json")["contracts"]}
        for item_id in ("RUST-008", "RUST-017"):
            self.assertEqual(work[item_id]["status"], "complete")
        for contract in ("UPD-013", "UPD-014"):
            self.assertEqual(contracts[contract]["status"], "parity")
        self.assertEqual(work["RUST-016"]["status"], "blocked")
        self.assertEqual(len(work["RUST-016"]["blocking_issues"]), 4)

        original_load = VALIDATOR.load
        for mutation in (None, "missing", "empty", "malformed", "wrong_status"):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(work_doc)
                item = next(item for item in changed["items"] if item["id"] == "RUST-016")
                if mutation == "missing":
                    item.pop("blocking_issues")
                elif mutation == "empty":
                    item["blocking_issues"] = []
                elif mutation == "malformed":
                    item["blocking_issues"] = ["release pending"]
                elif mutation == "wrong_status":
                    item["status"] = "ready"

                def load(name):
                    return changed if name == "work-items.json" else original_load(name)

                with patch.object(VALIDATOR, "load", side_effect=load), patch.dict(
                    os.environ, {"DEV_EXTERNAL": "1"}
                ), contextlib.redirect_stdout(io.StringIO()):
                    if mutation is None:
                        self.assertEqual(VALIDATOR.main(), 0)
                    else:
                        with self.assertRaises(ValueError):
                            VALIDATOR.main()

    def test_terminal_routes_and_negative_controls(self):
        work = json.loads((ROOT / "docs/rust-port/work-items.json").read_text())["items"]
        contracts = json.loads((ROOT / "docs/rust-port/contract-matrix.json").read_text())["contracts"]
        terminal = [item for item in work if item["status"] == "not_shared_consumer_local"]
        self.assertEqual({item["id"] for item in terminal}, {"RUST-009", "RUST-011", "RUST-012"})
        VALIDATOR.validate_consumer_local_routing(work, contracts)
        for mutation in (
            "required", "missing_issue", "shared_parity", "orphan_contract",
            "absolute_evidence", "traversal_evidence",
        ):
            with self.subTest(mutation=mutation):
                changed_work, changed_contracts = copy.deepcopy((work, contracts))
                item = next(item for item in changed_work if item["id"] == "RUST-009")
                row = next(row for row in changed_contracts if row["id"] == "AUD-001")
                if mutation == "required":
                    item["demand_class"] = "required"
                elif mutation == "missing_issue":
                    row.pop("consumer_issue")
                elif mutation == "shared_parity":
                    row["status"] = "parity"
                elif mutation == "orphan_contract":
                    item["status"] = "deferred"
                elif mutation == "absolute_evidence":
                    item["demand_evidence"] = str(ROOT / item["demand_evidence"])
                else:
                    item["demand_evidence"] = f"../{ROOT.name}/{item['demand_evidence']}"
                with self.assertRaises(ValueError):
                    VALIDATOR.validate_consumer_local_routing(changed_work, changed_contracts)

        with tempfile.TemporaryDirectory(prefix="corekit-retirement-routing-") as directory:
            fake_root = Path(directory) / "repo"
            fake_root.mkdir()
            evidence = fake_root / "demand.md"
            evidence.write_text("repository-owned test evidence")
            item = copy.deepcopy(terminal[0])
            item["demand_evidence"] = "demand.md"
            rows = [row for row in contracts if row["id"] in item["contracts"]]
            original_root = VALIDATOR.ROOT
            try:
                setattr(VALIDATOR, "ROOT", fake_root)
                VALIDATOR.validate_consumer_local_routing([item], rows)
                outside = Path(directory) / "outside.md"
                outside.write_text("outside-repository negative control")
                evidence.unlink()
                with self.subTest(mutation="escaping_symlink"):
                    try:
                        evidence.symlink_to(outside)
                    except OSError as error:
                        if not (getattr(error, "winerror", None) == 1314 and os.name == "nt"):
                            raise
                        self.skipTest("Windows runner lacks symlink creation privilege")
                    with self.assertRaises(ValueError):
                        VALIDATOR.validate_consumer_local_routing([item], rows)
            finally:
                setattr(VALIDATOR, "ROOT", original_root)


if __name__ == "__main__":
    unittest.main()
