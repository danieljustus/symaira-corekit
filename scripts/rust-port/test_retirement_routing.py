"""Terminal consumer-local decisions must never masquerade as shared parity."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "retirement_validator", ROOT / "docs/rust-port/validate.py"
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class RetirementRoutingTests(unittest.TestCase):
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
