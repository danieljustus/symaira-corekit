"""Acceptance regression tests use the real source-bound capture."""
import copy
import json
import unittest
from unittest.mock import patch
import candidate
import diff
import typed_contract


class AcceptanceControls(unittest.TestCase):
    CURRENT_CAPTURE = 'testdata/rust-port/sqlite/differential-macos-bound-rust006-20260916.json'

    def setUp(self):
        self.record = json.loads((diff.ROOT / self.CURRENT_CAPTURE).read_text())
        self.go = self.record['go']
        self.rust = copy.deepcopy(self.record['rust'])
        historical = json.loads((diff.ROOT / 'testdata/rust-port/sqlite/differential-macos-bound-rust014.json').read_text())
        self.stale_rust = historical['rust']
        self.manifest, self.manifest_sha = candidate.load()

    def test_source_bound_current_capture_passes(self):
        self.assertEqual(candidate.snapshot(), self.manifest['source_hashes'])
        verdict = diff.evaluate(self.go, self.rust, self.manifest, self.manifest_sha)
        self.assertEqual(typed_contract.apply(self.go, self.rust, verdict)['status'], 'passed')

    def test_current_capture_is_bound_to_post_squash_checkout(self):
        base = self.manifest['base']
        checkout = candidate.generate.run(['git', 'rev-parse', 'HEAD'], cwd=candidate.ROOT).decode().strip()
        self.assertEqual(self.rust['candidate_base'], base)
        candidate.generate.run(['git', 'merge-base', '--is-ancestor', base, self.rust['candidate_revision']], cwd=candidate.ROOT)
        candidate.generate.run(['git', 'merge-base', '--is-ancestor', self.rust['candidate_revision'], checkout], cwd=candidate.ROOT)

    def test_historical_capture_is_rejected_for_current_source(self):
        # This retained capture is bound to the prior Rust-014 candidate. It
        # remains useful evidence, but cannot certify the current source.
        #
        # Give it the current manifest digest deliberately, so the digest
        # check cannot be what rejects it: this asserts the source-hash
        # binding specifically, and the digest has its own control above.
        stale = copy.deepcopy(self.stale_rust)
        stale['candidate_manifest_sha256'] = self.manifest_sha
        with self.assertRaisesRegex(ValueError, 'Rust report differs from frozen source manifest'):
            diff.evaluate(self.go, stale, self.manifest, self.manifest_sha)

    def test_false_success_rejected(self):
        for value in (False, None, 1, 'true'):
            with self.subTest(value=value):
                self.rust['cases'][0]['success'] = value
                with self.assertRaisesRegex(ValueError, 'success'):
                    diff.evaluate(self.go, self.rust, self.manifest, self.manifest_sha)

    def test_missing_success_rejected(self):
        del self.rust['cases'][0]['success']
        with self.assertRaisesRegex(ValueError, 'success'):
            diff.evaluate(self.go, self.rust, self.manifest, self.manifest_sha)

    def test_source_hash_mutation_rejected(self):
        name = next(iter(self.rust['source_hashes']))
        self.rust['source_hashes'][name] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'frozen source'):
            diff.evaluate(self.go, self.rust, self.manifest, self.manifest_sha)

    def test_go_source_provenance_mutation_rejected(self):
        name = next(iter(self.go['oracle']['source_hashes']))
        self.go['oracle']['source_hashes'][name] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Go oracle source provenance'):
            diff.evaluate(self.go, self.rust, self.manifest, self.manifest_sha)

    def test_go_helper_provenance_mutation_rejected(self):
        name = next(iter(self.go['oracle']['artifact_hashes']))
        self.go['oracle']['artifact_hashes'][name] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Go oracle helper provenance'):
            diff.evaluate(self.go, self.rust, self.manifest, self.manifest_sha)

    def test_co_mutated_candidate_manifest_and_report_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        name = next(iter(manifest['source_hashes']))
        manifest['source_hashes'][name] = '0' * 64
        rust = copy.deepcopy(self.rust)
        rust['source_hashes'] = copy.deepcopy(manifest['source_hashes'])
        # Even matching report/manifest fields cannot replace the real source.
        rust['candidate_manifest_sha256'] = self.manifest_sha
        with self.assertRaisesRegex(ValueError, 'not bound to the current candidate source'):
            diff.evaluate(self.go, rust, manifest, self.manifest_sha)

    def test_candidate_base_mutation_rejected(self):
        self.rust['candidate_base'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'candidate base'):
            diff.evaluate(self.go, self.rust, self.manifest, self.manifest_sha)

    def test_native_identity_mutation_rejected(self):
        self.rust['native']['goos'] = 'not-this-host'
        with self.assertRaisesRegex(ValueError, 'native platform'):
            diff.evaluate(self.go, self.rust, self.manifest, self.manifest_sha)

    def test_wrong_source_rejected_before_cargo(self):
        with patch.object(candidate, 'snapshot', return_value={}):
            with self.assertRaisesRegex(ValueError, 'explicit source freeze'):
                diff.rust_capture(self.manifest)

    def test_missing_revision_rejected(self):
        del self.rust['candidate_revision']
        with self.assertRaisesRegex(ValueError, 'candidate revision'):
            diff.evaluate(self.go, self.rust, self.manifest, self.manifest_sha)

    def test_malformed_revision_rejected_before_git(self):
        for value in ('HEAD', '--help', 'a' * 39, None):
            self.rust['candidate_revision'] = value
            with patch.object(candidate.generate, 'run') as command:
                with self.assertRaisesRegex(ValueError, 'candidate revision'):
                    diff.evaluate(self.go, self.rust, self.manifest, self.manifest_sha)
                command.assert_not_called()

    def test_unrelated_revision_rejected(self):
        self.rust['candidate_revision'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'verified descendant'):
            diff.evaluate(self.go, self.rust, self.manifest, self.manifest_sha)

    def test_baseline_ancestor_revision_is_rejected(self):
        ancestor = candidate.generate.run(
            ['git', 'rev-parse', f"{self.manifest['base']}^"], cwd=candidate.ROOT
        ).decode().strip()
        self.rust['candidate_revision'] = ancestor
        with self.assertRaisesRegex(ValueError, 'verified descendant'):
            diff.evaluate(self.go, self.rust, self.manifest, self.manifest_sha)

    def test_non_ancestor_revision_rejected_for_current_checkout(self):
        with patch.object(candidate.generate, 'run') as mock_run:
            def side_effect(cmd, **kwargs):
                if cmd[:3] == ['git', 'merge-base', '--is-ancestor'] and cmd[4] == 'HEAD':
                    raise RuntimeError('not ancestor')
                return b''
            mock_run.side_effect = side_effect
            with self.assertRaisesRegex(ValueError, 'ancestor of the actual checkout'):
                diff.evaluate(self.go, self.rust, self.manifest, self.manifest_sha)

    def test_co_mutated_valid_ancestor_baseline_is_rejected(self):
        ancestor = candidate.generate.run(
            ['git', 'rev-parse', f"{candidate.EXPECTED_BASE}^"], cwd=candidate.ROOT
        ).decode().strip()
        manifest = copy.deepcopy(self.manifest)
        manifest['base'] = ancestor
        rust = copy.deepcopy(self.rust)
        rust['candidate_base'] = ancestor
        with self.assertRaisesRegex(ValueError, 'immutable expected base'):
            candidate.verify(rust, manifest, self.manifest_sha)

    def test_old_capture_is_not_current_acceptance(self):
        old = json.loads((diff.ROOT / 'testdata/rust-port/sqlite/differential-macos-typed.json').read_text())
        with self.assertRaises(ValueError):
            diff.evaluate(old['go'], old['rust'], self.manifest, self.manifest_sha)

    def test_candidate_manifest_digest_mutation_rejected(self):
        # The capture records the frozen manifest digest; a report that does
        # not match it must not be accepted just because its source hashes do.
        for value in ('0' * 64, None):
            with self.subTest(value=value):
                rust = copy.deepcopy(self.rust)
                rust['candidate_manifest_sha256'] = value
                with self.assertRaisesRegex(ValueError, 'candidate manifest digest'):
                    diff.evaluate(self.go, rust, self.manifest, self.manifest_sha)

    def test_equal_nonexistent_base_rejected(self):
        # When the revision equals the declared base the descendant check is
        # skipped, so the base itself must be proven to exist first.
        manifest = copy.deepcopy(self.manifest)
        manifest['base'] = '0' * 40
        rust = copy.deepcopy(self.rust)
        rust['candidate_base'] = manifest['base']
        rust['candidate_revision'] = manifest['base']
        with self.assertRaisesRegex(ValueError, 'immutable expected base'):
            candidate.verify(rust, manifest, self.manifest_sha)

    def test_manifest_base_rejected_before_git(self):
        for value in ('HEAD', 'origin/main', 'HEAD~1', 'a' * 39, 'A' * 40, 'not-a-base'):
            with self.subTest(value=value):
                manifest = copy.deepcopy(self.manifest)
                manifest['base'] = value
                rust = copy.deepcopy(self.rust)
                rust['candidate_base'] = value
                with patch.object(candidate.generate, 'run') as command:
                    with self.assertRaisesRegex(ValueError, 'candidate base'):
                        diff.evaluate(self.go, rust, manifest, self.manifest_sha)
                    command.assert_not_called()

    def test_manifest_base_non_commit_rejected(self):
        non_commit = candidate.generate.run(['git', 'rev-parse', 'HEAD^{tree}'], cwd=candidate.ROOT).decode().strip()
        manifest = copy.deepcopy(self.manifest)
        manifest['base'] = non_commit
        rust = copy.deepcopy(self.rust)
        rust['candidate_base'] = non_commit
        rust['candidate_revision'] = non_commit
        with self.assertRaisesRegex(ValueError, 'candidate base'):
            diff.evaluate(self.go, rust, manifest, self.manifest_sha)


if __name__ == '__main__':
    unittest.main()
