"""Acceptance regression tests use the real source-bound capture."""
import copy
import json
import unittest
from unittest.mock import patch
import candidate
import diff
import typed_contract


class AcceptanceControls(unittest.TestCase):
    CURRENT_CAPTURE = 'testdata/rust-port/sqlite/differential-macos-refreeze-20260920T175852Z.json'
    # A file that genuinely determines the built artifact and its observations.
    ENFORCED_KEY = 'rust/symaira-core-sqlite/src/lib.rs'

    def setUp(self):
        self.record = json.loads((diff.ROOT / self.CURRENT_CAPTURE).read_text())
        self.go = self.record['go']
        self.rust = copy.deepcopy(self.record['rust'])
        historical = json.loads((diff.ROOT / 'testdata/rust-port/sqlite/differential-macos-bound-rust014.json').read_text())
        self.stale_rust = historical['rust']
        self.manifest, self.manifest_sha = candidate.load()

    def test_source_bound_current_capture_passes(self):
        self.assertEqual(candidate.enforced(candidate.snapshot()),
                         candidate.enforced(self.manifest['source_hashes']))
        verdict = diff.evaluate(self.go, self.rust, self.manifest, self.manifest_sha)
        self.assertEqual(typed_contract.apply(self.go, self.rust, verdict)['status'], 'passed')

    def test_enforced_scope_is_the_port_input_class(self):
        # Build inputs and the port sources are enforced; CI orchestration,
        # checkout attributes and crates outside the dependency closure are
        # recorded forensics only, so routine maintenance cannot invalidate
        # retained evidence (docs/rust-port/adr-rust-003-candidate-source-scope.md).
        for path in (self.ENFORCED_KEY, 'rust/symaira-core-sqlite/Cargo.toml',
                     'rust/symaira-core-fs/src/lib.rs', 'Cargo.toml', 'Cargo.lock',
                     'rust-toolchain.toml', 'scripts/rust-port/sqlite/main.go',
                     'scripts/rust-port/sqlite/test_acceptance.py'):
            with self.subTest(enforced=path):
                self.assertTrue(candidate.is_enforced(path))
        for path in ('.gitattributes', '.github/workflows/ci.yml',
                     'rust/symaira-core-config/src/lib.rs',
                     'rust/symaira-core-log/src/lib.rs',
                     'rust/test-support/symaira-contract-fixtures/src/lib.rs'):
            with self.subTest(forensic=path):
                self.assertFalse(candidate.is_enforced(path))
        recorded = set(self.manifest['source_hashes'])
        self.assertTrue(recorded - set(candidate.enforced(self.manifest['source_hashes'])))

    def test_scope_covers_the_crate_dependency_closure(self):
        self.assertEqual(candidate.port_path_dependencies(), ['rust/symaira-core-fs'])
        candidate.validate_scope()
        with patch.object(candidate, 'port_path_dependencies',
                          return_value=['rust/symaira-core-log']):
            with self.assertRaisesRegex(ValueError, 'does not cover path dependency'):
                candidate.validate_scope()

    def test_workflow_and_unrelated_class_drift_does_not_invalidate_capture(self):
        # The reported defect: a workflow-only edit invalidated the whole
        # suite even though it cannot change the built bytes or observations.
        drifted = copy.deepcopy(self.manifest)
        for path in ('.gitattributes', '.github/workflows/ci.yml',
                     'rust/symaira-core-config/src/lib.rs'):
            drifted['source_hashes'][path] = '0' * 64
        verdict = diff.evaluate(self.go, self.rust, drifted, self.manifest_sha)
        self.assertEqual(typed_contract.apply(self.go, self.rust, verdict)['status'], 'passed')

    def test_enforced_class_drift_invalidates_capture(self):
        drifted = copy.deepcopy(self.manifest)
        drifted['source_hashes'][self.ENFORCED_KEY] = '0' * 64
        rust = copy.deepcopy(self.rust)
        rust['source_hashes'] = copy.deepcopy(drifted['source_hashes'])
        rust['candidate_manifest_sha256'] = self.manifest_sha
        with self.assertRaisesRegex(ValueError, 'not bound to the current candidate source'):
            diff.evaluate(self.go, rust, drifted, self.manifest_sha)

    def test_current_capture_is_bound_to_post_squash_checkout(self):
        base = self.manifest['base']
        checkout = candidate.generate.run(['git', 'rev-parse', 'HEAD'], cwd=candidate.ROOT).decode().strip()
        self.assertEqual(self.rust['candidate_base'], base)
        candidate.generate.run(['git', 'merge-base', '--is-ancestor', base, self.rust['candidate_revision']], cwd=candidate.ROOT)
        candidate.generate.run(['git', 'merge-base', '--is-ancestor', self.rust['candidate_revision'], checkout], cwd=candidate.ROOT)

    def test_current_capture_revision_survives_a_squash_merge(self):
        # #300: the capture must name a revision that stays an ancestor of the
        # base branch. Generated on a feature branch that is later squash-merged,
        # the recorded revision is destroyed and every ancestry control fails on
        # `main` although this branch's CI was green. Asserting it here makes the
        # defect visible before the merge instead of after it.
        survives, base_tip = candidate.merge_survival(self.rust['candidate_revision'])
        self.assertIsNotNone(base_tip, 'no base ref resolvable to check merge survival')
        self.assertTrue(survives,
                        f"capture revision {self.rust['candidate_revision']} is not reachable "
                        f"from {base_tip}; re-freeze with HEAD on the base branch (#300)")

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
        name = self.ENFORCED_KEY
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

    def test_go_oracle_isolation_provenance_platform_branches(self):
        # Exercises validator provenance platform branches; simulated Windows
        # observation does not claim to serve as native Windows runtime evidence.
        # 1. Unix branch (e.g. self.go on darwin): requires umask '0077'.
        diff.validate_oracle_provenance(self.go)
        mismatched_unix = copy.deepcopy(self.go)
        mismatched_unix['oracle']['isolation']['umask'] = 'not-applicable'
        with self.assertRaisesRegex(ValueError, 'Go oracle isolation provenance'):
            diff.validate_oracle_provenance(mismatched_unix)

        # 2. Windows branch: requires umask 'not-applicable'.
        simulated_win = copy.deepcopy(self.go)
        simulated_win['cases'][0]['state']['native_goos'] = 'windows'
        simulated_win['oracle']['isolation']['umask'] = 'not-applicable'
        diff.validate_oracle_provenance(simulated_win)
        mismatched_win = copy.deepcopy(simulated_win)
        mismatched_win['oracle']['isolation']['umask'] = '0077'
        with self.assertRaisesRegex(ValueError, 'Go oracle isolation provenance'):
            diff.validate_oracle_provenance(mismatched_win)

        # 3. Fail-closed on missing native platform identity.
        missing_platform = copy.deepcopy(self.go)
        del missing_platform['cases'][0]['state']['native_goos']
        with self.assertRaisesRegex(ValueError, 'native platform identity'):
            diff.validate_oracle_provenance(missing_platform)

    def test_co_mutated_candidate_manifest_and_report_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        name = self.ENFORCED_KEY
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
