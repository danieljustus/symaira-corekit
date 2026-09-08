#!/usr/bin/env python3
"""Deterministic negative and fixture tests for the consumer verifier."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("consumer_verify", Path(__file__).with_name("verify.py"))
assert SPEC and SPEC.loader
verify = importlib.util.module_from_spec(SPEC)
import sys
sys.modules[SPEC.name] = verify
SPEC.loader.exec_module(verify)


class ConsumerVerifierTests(unittest.TestCase):
    def test_pseudoversion_is_preserved_exactly(self) -> None:
        text = "module example.invalid/tool\n\nrequire (\n\tgithub.com/danieljustus/symaira-corekit v0.0.0-20260908091500-0123456789ab\n)\n"
        self.assertEqual(verify.parse_go_pin(text), "v0.0.0-20260908091500-0123456789ab")

    def test_current_manifest_is_fail_closed_and_covers_all_records(self) -> None:
        report = verify.verify_manifest(
            verify.MANIFEST,
            workspace_root=Path("/definitely/missing/workspace"),
            corekit_root=verify.ROOT,
        )
        self.assertEqual(report["consumer_count"], 5)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual({item["repository"] for item in report["findings"]}, set(report["checked_repositories"]))

    def test_fixture_git_pin_requires_verified_evidence_and_lock_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            corekit = root / "symaira-corekit"
            consumer = root / "fixture"
            subprocess.run(["git", "init", "-q", "-b", "main", str(corekit)], check=True)
            (corekit / "marker").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(corekit), "add", "marker"], check=True)
            subprocess.run(["git", "-C", str(corekit), "-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
            commit = subprocess.check_output(["git", "-C", str(corekit), "rev-parse", "HEAD"], text=True).strip()
            subprocess.run(["git", "-C", str(corekit), "tag", "v0.17.0"], check=True)
            (consumer / "crates" / "app").mkdir(parents=True)
            (consumer / "cmd").mkdir()
            (consumer / "go.mod").write_text("module example.invalid/consumer\n\nrequire github.com/danieljustus/symaira-corekit v0.17.0\n", encoding="utf-8")
            (consumer / "cmd" / "main.go").write_text('package main\nimport _ "github.com/danieljustus/symaira-corekit/versionkit"\n', encoding="utf-8")
            (consumer / "Cargo.toml").write_text(
                '[package]\nname = "fixture"\nversion = "1.0.0"\n\n[dependencies]\n'
                f'symaira-core-version = {{ git = "{verify.COREKIT_URL}", rev = "{commit}", version = "=0.0.0" }}\n',
                encoding="utf-8",
            )
            source = f"git+{verify.COREKIT_URL}?rev={commit}#{commit}"
            (consumer / "Cargo.lock").write_text(
                f'version = 4\n\n[[package]]\nname = "{verify.COREKIT_PACKAGE}"\nversion = "0.0.0"\nsource = "{source}"\n\n[[package]]\nname = "fixture"\nversion = "1.0.0"\ndependencies = ["{verify.COREKIT_PACKAGE}"]\n',
                encoding="utf-8",
            )
            manifest = {
                "schema_version": 2,
                "corekit": {"repository": "danieljustus/symaira-corekit", "go_module": verify.COREKIT_MODULE, "release_tag": "v0.17.0", "release_commit": commit, "rust_registry": {"package": verify.COREKIT_PACKAGE, "status": "not_released"}},
                "consumers": [{
                    "repo": "example/fixture", "pins": ["go.mod"],
                    "rust": {"status": "git", "package": verify.COREKIT_PACKAGE, "version": "0.0.0", "revision": commit,
                             "manifest_paths": ["Cargo.toml"], "release": {"tag": "v0.17.0", "commit": commit},
                             "registry": {"status": "not_released"},
                             "evidence": {"standalone": {"status": "verified", "command": "./artifact version"}, "rollback": {"status": "verified", "command": "./rollback-fixture"}}}
                }]
            }
            manifest_path = root / "consumers.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            report = verify.verify_manifest(manifest_path, workspace_root=root, corekit_root=corekit)
            self.assertEqual(report["status"], "passed", report)
            lock = (consumer / "Cargo.lock").read_text(encoding="utf-8").replace("git+", "registry+")
            (consumer / "Cargo.lock").write_text(lock, encoding="utf-8")
            blocked = verify.verify_manifest(manifest_path, workspace_root=root, corekit_root=corekit)
            self.assertEqual(blocked["status"], "blocked")
            self.assertTrue(any(item["code"] == "rust.lock.source" for item in blocked["findings"]))

    def test_cli_returns_blocked_status_instead_of_success(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest = Path(raw) / "consumers.json"
            manifest.write_text(json.dumps({"corekit": {"repository": "danieljustus/symaira-corekit", "go_module": verify.COREKIT_MODULE, "release_tag": "v0.17.0", "release_commit": "0" * 40, "rust_registry": {"package": verify.COREKIT_PACKAGE, "status": "not_released"}}, "consumers": [{"repo": "example/missing", "pins": ["go.mod"]}]}), encoding="utf-8")
            result = subprocess.run(
                ["python3", str(Path(__file__).with_name("verify.py")), "--released-consumers", "--manifest", str(manifest), "--workspace-root", raw, "--corekit-root", str(verify.ROOT)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn('"status": "blocked"', result.stdout)


if __name__ == "__main__":
    unittest.main()
