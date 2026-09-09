"""Approved differences must not hide wrong phases, causes or state."""
import copy
import hashlib
import json
import unittest
import diff
import typed_contract


class TypedControls(unittest.TestCase):
    def setUp(self):
        raw = (diff.ROOT / 'testdata/rust-port/sqlite/differential-macos-typed.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '7552ed5cf28ebdedd169d703a970a8a8f6776d175a3b2116f91b8e9119aa98d3')
        self.record = json.loads(raw)
        self.go = self.record['go']
        self.rust = copy.deepcopy(self.record['rust'])

    def verdict(self):
        return typed_contract.apply(self.go, self.rust, diff._compare_observations(self.go, self.rust))

    def test_real_capture_passes_with_explicit_differences(self):
        self.assertEqual(self.verdict(), self.record['verdict'])
        self.assertEqual(len(self.verdict()['accepted_differences']), 9)

    def test_strict_contract_stays_red(self):
        self.assertEqual(diff._compare_observations(self.go, self.rust)['status'], 'partial')

    def test_wrong_phase_rejected(self):
        self.rust['cases'][4]['errors']['exec_failure']['kind'] = 'record'
        self.assertEqual(self.verdict()['status'], 'partial')

    def test_wrong_cause_rejected(self):
        self.rust['cases'][4]['errors']['exec_failure']['cause']['code'] = 14
        self.assertEqual(self.verdict()['status'], 'partial')

    def test_missing_cause_rejected(self):
        del self.rust['cases'][5]['errors']['read_file']['cause']
        self.assertEqual(self.verdict()['status'], 'partial')

    def test_equal_unknown_causes_rejected(self):
        self.go['cases'][4]['negative'][0]['cause'] = {'type': 'unclassified'}
        self.rust['cases'][4]['errors']['exec_failure']['cause'] = {'type': 'unclassified'}
        self.assertEqual(self.verdict()['status'], 'partial')

    def test_state_drift_not_waived(self):
        self.rust['cases'][4]['state']['rollback_probe_absent'] = False
        self.assertEqual(self.verdict()['status'], 'partial')

    def test_unknown_lifecycle_difference_rejected(self):
        self.rust['cases'][5]['unsupported'].append('another omission')
        self.assertEqual(self.verdict()['status'], 'partial')


if __name__ == '__main__':
    unittest.main()
