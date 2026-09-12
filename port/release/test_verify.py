#!/usr/bin/env python3
"""Tests for the local, non-publishing release verifier."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("release_verify", Path(__file__).with_name("verify.py"))
assert SPEC and SPEC.loader
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


class ManifestShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((Path(__file__).with_name("manifest.json")).read_text())

    def test_checked_in_manifest_is_valid(self) -> None:
        release = verify.validate_manifest_shape(self.manifest)
        self.assertEqual(release["planned_publish_order"], ["symaira-core-version"])
        self.assertFalse(release["publish"])

    def test_tag_requires_plain_stable_repository_tag(self) -> None:
        for value in ("0.17.0", "v0.17.0-rc.1", "v1.2.3+build", "rust-v0.1.0"):
            with self.subTest(value=value), self.assertRaises(verify.VerificationError):
                verify.validate_tag(value)

    def test_publish_order_cannot_include_unadopted_crate(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["release"]["planned_publish_order"].append("symaira-core-exit")
        with self.assertRaisesRegex(verify.VerificationError, "planned_publish_order"):
            verify.validate_manifest_shape(manifest)

    def test_publish_is_fail_closed(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["release"]["publish"] = True
        with self.assertRaisesRegex(verify.VerificationError, "publish must remain false"):
            verify.validate_manifest_shape(manifest)

    def test_dirty_source_is_rejected(self) -> None:
        for status in (" M tracked.py\n", "?? untracked.txt\n"):
            with self.subTest(status=status), patch.object(verify, "run", return_value=status):
                with self.assertRaisesRegex(verify.VerificationError, "clean source checkout"):
                    verify.validate_clean_source()

    def test_clean_source_is_accepted(self) -> None:
        with patch.object(verify, "run", return_value=""):
            verify.validate_clean_source()

    def test_oracle_commit_rejects_missing_object(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["release"]["provenance"]["oracle_commit"] = "0" * 40
        release = verify.validate_manifest_shape(manifest)
        with self.assertRaisesRegex(verify.VerificationError, "command failed.*commit"):
            verify.validate_git_provenance(release, None)

    def test_oracle_commit_rejects_non_commit_objects(self) -> None:
        for revision in ("HEAD^{tree}", "HEAD:port/release/manifest.json"):
            with self.subTest(revision=revision):
                manifest = copy.deepcopy(self.manifest)
                manifest["release"]["provenance"]["oracle_commit"] = verify.run(
                    ["git", "rev-parse", revision]
                ).strip()
                release = verify.validate_manifest_shape(manifest)
                with self.assertRaisesRegex(verify.VerificationError, "command failed.*commit"):
                    verify.validate_git_provenance(release, None)

    def test_existing_oracle_commit_preserves_source_revision(self) -> None:
        current = verify.run(["git", "rev-parse", "HEAD"]).strip()
        oracle = self.manifest["release"]["provenance"]["oracle_commit"]
        for source_revision, expected in (("HEAD", current), (oracle, oracle)):
            with self.subTest(source_revision=source_revision):
                manifest = copy.deepcopy(self.manifest)
                manifest["release"]["source_revision"] = source_revision
                release = verify.validate_manifest_shape(manifest)
                self.assertEqual(verify.validate_git_provenance(release, None), expected)

    def test_non_publishable_crate_requires_explicit_publish_empty_list(self) -> None:
        metadata = copy.deepcopy(verify.cargo_metadata())
        package = next(item for item in metadata["packages"] if item["name"] == "symaira-core-exit")
        package.pop("publish", None)
        with self.assertRaisesRegex(verify.VerificationError, "publish=\\[\\]"):
            verify.validate_workspace(self.manifest["release"], metadata)

    def test_declared_crate_manifest_rejects_forbidden_path(self) -> None:
        metadata = verify.cargo_metadata()
        manifest = copy.deepcopy(self.manifest)
        manifest["release"]["crates"][0]["manifest"] = "vendor/Cargo.toml"
        with self.assertRaisesRegex(verify.VerificationError, "forbidden"):
            verify.validate_workspace(manifest["release"], metadata)


if __name__ == "__main__":
    unittest.main()
