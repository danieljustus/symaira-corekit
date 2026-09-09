"""Mutation controls over an unchanged real, deliberately partial capture."""
import copy
import hashlib
import json
import unittest
import diff

CAPTURE = diff.ROOT / 'testdata/rust-port/sqlite/differential-macos-partial.json'
DIGEST = '137e5ffeca6ffd560cf8ded7b5fcc721c2f408cc618c1a47f556d1493579729d'


class DifferentialControls(unittest.TestCase):
    def setUp(self):
        raw = CAPTURE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), DIGEST)
        self.record = json.loads(raw)
        self.go = self.record['go']
        self.rust = copy.deepcopy(self.record['rust'])

    def assert_difference(self, path):
        verdict = diff._compare_observations(self.go, self.rust)
        self.assertEqual(verdict['status'], 'partial')
        self.assertIn(path, [d['path'] for d in verdict['differences']])

    def test_historical_partial_capture_remains_partial(self):
        verdict = diff._compare_observations(self.go, self.rust)
        self.assertEqual(verdict, self.record['verdict'])

    def test_missing_case_rejected(self):
        self.rust['cases'].pop()
        with self.assertRaises(ValueError):
            diff._compare_observations(self.go, self.rust)

    def test_adjacent_large_integer_rejected(self):
        self.rust['cases'][2]['state']['large_integer'] += 1
        self.assert_difference('SQL-003/large_integer')

    def test_missing_null_not_equal_to_null(self):
        del self.rust['cases'][2]['state']['null_value']
        self.assert_difference('SQL-003/null_value')

    def test_boolean_not_equal_to_integer(self):
        self.rust['cases'][0]['state']['ping'] = 1
        self.assert_difference('SQL-001/ping')

    def test_rollback_failure_not_hidden_by_existing_differences(self):
        self.rust['cases'][4]['state']['rollback_probe_absent'] = False
        self.assert_difference('SQL-005/rollback_probe_absent')

    def test_policy_drift_not_hidden_by_existing_differences(self):
        self.rust['cases'][1]['state']['connections'][0]['foreign_keys'] = 0
        self.assert_difference('SQL-002/connections')


if __name__ == '__main__':
    unittest.main()
