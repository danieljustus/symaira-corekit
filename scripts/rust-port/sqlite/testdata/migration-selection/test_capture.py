import copy
import json
import unittest

import capture


class RejectionTests(unittest.TestCase):
    def setUp(self):
        self.expected = json.loads((capture.HERE / "observed.json").read_bytes())
        self.actual = copy.deepcopy(self.expected)

    def test_selection_read_order_drift(self):
        self.actual["cases"][0]["reads"].reverse()
        with self.assertRaisesRegex(ValueError, "fixture/source drift"):
            capture.compare(self.expected, self.actual)

    def test_source_identity_drift(self):
        self.actual["source_hashes"]["sqlitekit/sqlitekit.go"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "fixture/source drift"):
            capture.compare(self.expected, self.actual)

    def test_zero_executed_cases(self):
        self.actual["cases"] = []
        with self.assertRaisesRegex(ValueError, "case IDs differ"):
            capture.compare(self.expected, self.actual)


if __name__ == "__main__":
    unittest.main()
