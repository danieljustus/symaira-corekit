"""Exact case-ID controls discovered by the focused SQLite contract gate."""
import copy
import json
import unittest

import candidate
import diff
import generate
import typed_contract


EXPECTED_IDS = ['SQL-001', 'SQL-002', 'SQL-003', 'SQL-004', 'SQL-005', 'SQL-006']
ID_ERROR = r'case IDs/order mismatch|Rust executed case IDs differ from declared oracle set'


class CaseIdControls(unittest.TestCase):
    def setUp(self):
        self.record = json.loads((diff.ROOT / 'testdata/rust-port/sqlite/differential-macos-bound.json').read_text())
        self.manifest, _ = candidate.load()

    def compare(self, entrypoint, go, rust):
        if entrypoint == 'acceptance':
            return diff.evaluate(go, rust, self.manifest)
        return diff._compare_observations(go, rust)

    def assert_case_ids_rejected(self, mutation):
        # Matching defects on both sides must not turn into a parity pass.
        for sides in (('go',), ('rust',), ('go', 'rust')):
            for entrypoint in ('acceptance', 'historical'):
                with self.subTest(sides=sides, entrypoint=entrypoint):
                    record = copy.deepcopy(self.record)
                    for side in sides:
                        mutation(record[side]['cases'])
                    with self.assertRaisesRegex(ValueError, ID_ERROR):
                        self.compare(entrypoint, record['go'], record['rust'])

    def test_declared_and_executed_ids_are_exact(self):
        self.assertEqual(generate.EXPECTED_IDS, EXPECTED_IDS)
        self.assertEqual(self.record['verdict']['case_ids'], EXPECTED_IDS)
        for side in ('go', 'rust'):
            with self.subTest(side=side):
                self.assertEqual([c['id'] for c in self.record[side]['cases']], EXPECTED_IDS)
        for entrypoint in ('acceptance', 'historical'):
            with self.subTest(entrypoint=entrypoint):
                go, rust = self.record['go'], self.record['rust']
                verdict = self.compare(entrypoint, go, rust)
                self.assertEqual(verdict['case_ids'], EXPECTED_IDS)
                self.assertEqual(typed_contract.apply(go, rust, verdict), self.record['verdict'])

    def test_zero_executed_cases_rejected(self):
        self.assert_case_ids_rejected(lambda cases: cases.clear())

    def test_each_missing_case_rejected(self):
        for index, cid in enumerate(EXPECTED_IDS):
            with self.subTest(missing=cid):
                self.assert_case_ids_rejected(lambda cases: cases.pop(index))

    def test_duplicate_with_all_declared_ids_present_rejected(self):
        # A set-only comparison would silently discard each duplicate.
        for index, cid in enumerate(EXPECTED_IDS):
            with self.subTest(duplicate=cid):
                self.assert_case_ids_rejected(lambda cases: cases.append(copy.deepcopy(cases[index])))

    def test_duplicate_replacing_required_id_rejected(self):
        # Preserve the count and observation bodies; change only the identity.
        for index, cid in enumerate(EXPECTED_IDS):
            with self.subTest(replaced=cid):
                self.assert_case_ids_rejected(
                    lambda cases: cases[index].update(id=EXPECTED_IDS[(index + 1) % len(EXPECTED_IDS)]))

    def test_unknown_extra_id_rejected_at_every_position(self):
        for index in range(len(EXPECTED_IDS) + 1):
            with self.subTest(position=index):
                self.assert_case_ids_rejected(
                    lambda cases: cases.insert(index, {**copy.deepcopy(cases[-1]), 'id': 'SQL-999'}))

    def test_unknown_id_replacing_required_id_rejected(self):
        for index, cid in enumerate(EXPECTED_IDS):
            with self.subTest(replaced=cid):
                self.assert_case_ids_rejected(lambda cases: cases[index].update(id='SQL-999'))

    def test_reordered_cases_rejected(self):
        # Comparison is positional: accepting a permutation would pair wrong SQL cases.
        for index in range(len(EXPECTED_IDS) - 1):
            with self.subTest(position=index):
                self.assert_case_ids_rejected(lambda cases: cases.insert(index, cases.pop(index + 1)))


if __name__ == '__main__':
    unittest.main()
