#!/usr/bin/env python3
"""Tests for the local, non-publishing release verifier."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


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
        self.assertEqual(release["publish_order"], ["symaira-core-version"])
        self.assertFalse(release["publish"])

    def test_tag_requires_plain_stable_repository_tag(self) -> None:
        for value in ("0.17.0", "v0.17.0-rc.1", "v1.2.3+build", "rust-v0.1.0"):
            with self.subTest(value=value), self.assertRaises(verify.VerificationError):
                verify.validate_tag(value)

    def test_publish_order_cannot_include_unadopted_crate(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["release"]["publish_order"].append("symaira-core-exit")
        with self.assertRaisesRegex(verify.VerificationError, "publish_order"):
            verify.validate_manifest_shape(manifest)

    def test_publish_is_fail_closed(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["release"]["publish"] = True
        with self.assertRaisesRegex(verify.VerificationError, "publish must remain false"):
            verify.validate_manifest_shape(manifest)


if __name__ == "__main__":
    unittest.main()
