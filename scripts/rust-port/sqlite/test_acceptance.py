"""Acceptance regression tests use the real source-bound capture."""
import copy
import json
import unittest
from unittest.mock import patch
import candidate
import diff
import typed_contract


class AcceptanceControls(unittest.TestCase):
    def setUp(self):
        self.record = json.loads((diff.ROOT / 'testdata/rust-port/sqlite/differential-macos-bound-rust014.json').read_text())
        self.go = self.record['go']
        self.rust = copy.deepcopy(self.record['rust'])
        self.manifest, _ = candidate.load()

    def test_source_bound_real_capture_passes(self):
        verdict = diff.evaluate(self.go, self.rust, self.manifest)
        self.assertEqual(typed_contract.apply(self.go, self.rust, verdict)['status'], 'passed')

    def test_false_success_rejected(self):
        for value in (False, None, 1, 'true'):
            with self.subTest(value=value):
                self.rust['cases'][0]['success'] = value
                with self.assertRaisesRegex(ValueError, 'success'):
                    diff.evaluate(self.go, self.rust, self.manifest)

    def test_missing_success_rejected(self):
        del self.rust['cases'][0]['success']
        with self.assertRaisesRegex(ValueError, 'success'):
            diff.evaluate(self.go, self.rust, self.manifest)

    def test_source_hash_mutation_rejected(self):
        name = next(iter(self.rust['source_hashes']))
        self.rust['source_hashes'][name] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'frozen source'):
            diff.evaluate(self.go, self.rust, self.manifest)

    def test_candidate_base_mutation_rejected(self):
        self.rust['candidate_base'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'candidate base'):
            diff.evaluate(self.go, self.rust, self.manifest)

    def test_native_identity_mutation_rejected(self):
        self.rust['native']['goos'] = 'not-this-host'
        with self.assertRaisesRegex(ValueError, 'native platform'):
            diff.evaluate(self.go, self.rust, self.manifest)

    def test_wrong_source_rejected_before_cargo(self):
        with patch.object(candidate, 'snapshot', return_value={}):
            with self.assertRaisesRegex(ValueError, 'explicit source freeze'):
                diff.rust_capture(self.manifest)

    def test_missing_revision_rejected(self):
        del self.rust['candidate_revision']
        with self.assertRaisesRegex(ValueError, 'candidate revision'):
            diff.evaluate(self.go, self.rust, self.manifest)

    def test_malformed_revision_rejected_before_git(self):
        for value in ('HEAD', '--help', 'a' * 39, None):
            self.rust['candidate_revision'] = value
            with patch.object(candidate.generate, 'run') as command:
                with self.assertRaisesRegex(ValueError, 'candidate revision'):
                    diff.evaluate(self.go, self.rust, self.manifest)
                command.assert_not_called()

    def test_unrelated_revision_rejected(self):
        self.rust['candidate_revision'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'verified descendant'):
            diff.evaluate(self.go, self.rust, self.manifest)

    def test_old_capture_is_not_current_acceptance(self):
        old = json.loads((diff.ROOT / 'testdata/rust-port/sqlite/differential-macos-typed.json').read_text())
        with self.assertRaises(ValueError):
            diff.evaluate(old['go'], old['rust'], self.manifest)


if __name__ == '__main__':
    unittest.main()
