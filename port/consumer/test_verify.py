#!/usr/bin/env python3
"""Regression tests for the fail-closed consumer verifier."""
from __future__ import annotations

import copy
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


def git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()


def init_git(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "fixture"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "fixture@example.invalid"], check=True)


def make_fixture(root: Path, *, status: str = "git") -> tuple[Path, Path, Path, str, str]:
    corekit = root / "symaira-corekit"
    consumer = root / "fixture"
    corekit.mkdir()
    consumer.mkdir()
    init_git(corekit)
    (corekit / "marker").write_text("pre-release\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(corekit), "add", "marker"], check=True)
    subprocess.run(["git", "-C", str(corekit), "commit", "-qm", "pre-release"], check=True)
    (corekit / "marker").write_text("release\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(corekit), "add", "marker"], check=True)
    subprocess.run(["git", "-C", str(corekit), "commit", "-qm", "release"], check=True)
    release_commit = git(corekit, "rev-parse", "HEAD")
    subprocess.run(["git", "-C", str(corekit), "tag", "v0.17.0"], check=True)
    (corekit / "marker").write_text("adoption\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(corekit), "add", "marker"], check=True)
    subprocess.run(["git", "-C", str(corekit), "commit", "-qm", "adoption"], check=True)
    adoption_commit = git(corekit, "rev-parse", "HEAD")

    (consumer / "cmd").mkdir()
    (consumer / "bin").mkdir()
    (consumer / "evidence").mkdir()
    (consumer / "go.mod").write_text(
        "module example.invalid/consumer\n\n"
        "require github.com/danieljustus/symaira-corekit v0.17.0\n",
        encoding="utf-8",
    )
    (consumer / "cmd" / "main.go").write_text(
        'package main\nimport _ "github.com/danieljustus/symaira-corekit/versionkit"\n',
        encoding="utf-8",
    )
    (consumer / "bin" / "fixture").write_text("artifact\n", encoding="utf-8")

    if status == "git":
        cargo_spec = (
            f'symaira-core-version = {{ git = "{verify.COREKIT_URL}", '
            f'rev = "{adoption_commit}", version = "=0.0.0" }}\n'
        )
        source = f"git+{verify.COREKIT_URL}?rev={adoption_commit}#{adoption_commit}"
        lock_extra = ""
    else:
        cargo_spec = 'symaira-core-version = { version = "=0.0.0" }\n'
        source = "registry+https://github.com/rust-lang/crates.io-index"
        lock_extra = 'checksum = "' + "a" * 64 + '"\n'
    (consumer / "Cargo.toml").write_text(
        '[package]\nname = "fixture"\nversion = "1.0.0"\n\n[dependencies]\n' + cargo_spec,
        encoding="utf-8",
    )
    (consumer / "Cargo.lock").write_text(
        'version = 4\n\n[[package]]\n'
        f'name = "{verify.COREKIT_PACKAGE}"\nversion = "0.0.0"\n'
        f'source = "{source}"\n{lock_extra}\n'
        '[[package]]\nname = "fixture"\nversion = "1.0.0"\n'
        f'dependencies = ["{verify.COREKIT_PACKAGE}"]\n',
        encoding="utf-8",
    )

    def evidence(name: str, command: str) -> dict[str, object]:
        report_path = f"evidence/{name}.json"
        result = {"exit_code": 0, "stdout": "fixture version\n", "stderr": ""}
        (consumer / report_path).write_text(
            json.dumps({
                "tag": "v0.17.0",
                "commit": release_commit,
                "artifact": "bin/fixture",
                "observed": {"command": command, **result},
            }),
            encoding="utf-8",
        )
        return {
            "status": "verified",
            "report": report_path,
            "artifact": "bin/fixture",
            "command": command,
            "result": result,
        }

    rust: dict[str, object] = {
        "status": status,
        "package": verify.COREKIT_PACKAGE,
        "version": "0.0.0",
        "manifest_paths": ["Cargo.toml"],
        "release": {"tag": "v0.17.0", "commit": release_commit},
        "registry": {"status": "published" if status == "registry" else "not_released"},
        "evidence": {
            "standalone": evidence("standalone", "./bin/fixture version"),
            "rollback": evidence("rollback", "./bin/fixture rollback"),
        },
    }
    if status == "git":
        rust["revision"] = adoption_commit
    else:
        rust["registry_version"] = "0.0.0"
    manifest = {
        "schema_version": 2,
        "corekit": {
            "repository": "danieljustus/symaira-corekit",
            "go_module": verify.COREKIT_MODULE,
            "release_tag": "v0.17.0",
            "release_commit": release_commit,
            "rust_registry": {"package": verify.COREKIT_PACKAGE, "status": "not_released"},
        },
        "consumers": [{"repo": "example/fixture", "pins": ["go.mod"], "rust": rust}],
    }
    manifest_path = root / "consumers.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    init_git(consumer)
    subprocess.run(["git", "-C", str(consumer), "add", "."], check=True)
    subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "fixture"], check=True)
    return manifest_path, corekit, consumer, release_commit, adoption_commit


class ConsumerVerifierTests(unittest.TestCase):
    def test_pseudoversion_is_preserved_exactly(self) -> None:
        text = "module example.invalid/tool\n\nrequire (\n\tgithub.com/danieljustus/symaira-corekit v0.0.0-20260908091500-0123456789ab\n)\n"
        self.assertEqual(verify.parse_go_pin(text), "v0.0.0-20260908091500-0123456789ab")

    def test_go_import_parser_ignores_comments_and_strings(self) -> None:
        text = '''package main
const fake = "import \\\"github.com/danieljustus/symaira-corekit/versionkit\\\""
/* import "github.com/danieljustus/symaira-corekit/fake" */
import (
    _ "github.com/danieljustus/symaira-corekit/versionkit"
)
'''
        self.assertEqual(verify.go_imports(text), ["github.com/danieljustus/symaira-corekit/versionkit"])

    def test_tracked_go_imports_ignore_nested_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            checkout = Path(raw) / "consumer"
            checkout.mkdir()
            init_git(checkout)
            (checkout / "main.go").write_text(
                'package main\nconst fake = "github.com/danieljustus/symaira-corekit/versionkit"\n'
                '// github.com/danieljustus/symaira-corekit/comment\n', encoding="utf-8")
            nested = checkout / ".worktrees" / "nested"
            nested.mkdir(parents=True)
            (nested / "main.go").write_text(
                'package main\nimport _ "github.com/danieljustus/symaira-corekit/versionkit"\n', encoding="utf-8")
            subprocess.run(["git", "-C", str(checkout), "add", "main.go"], check=True)
            subprocess.run(["git", "-C", str(checkout), "commit", "-qm", "fixture"], check=True)
            self.assertEqual(verify.tracked_go_imports(checkout), [])

    def test_current_manifest_is_fail_closed_and_covers_all_records(self) -> None:
        report = verify.verify_manifest(
            verify.MANIFEST,
            workspace_root=Path("/definitely/missing/workspace"),
            corekit_root=verify.ROOT,
        )
        self.assertEqual(report["consumer_count"], 5)
        self.assertEqual(report["status"], "blocked")
        finding_repositories = {item["repository"] for item in report["findings"]}
        self.assertTrue(finding_repositories.issubset(set(report["checked_repositories"])))
        self.assertIn("corekit", report["checked_repositories"])

    def test_git_adoption_can_postdate_release(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest, corekit, _, release_commit, adoption_commit = make_fixture(Path(raw), status="git")
            self.assertNotEqual(release_commit, adoption_commit)
            report = verify.verify_manifest(manifest, workspace_root=Path(raw), corekit_root=corekit)
            self.assertEqual(report["status"], "passed", report)

    def test_git_adoption_before_or_unrelated_to_release_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, release_commit, adoption_commit = make_fixture(root, status="git")
            before_release = git(corekit, "rev-list", "--max-parents=0", "HEAD")
            empty_tree = subprocess.run(
                ["git", "-C", str(corekit), "mktree"], input="", text=True,
                stdout=subprocess.PIPE, check=True,
            ).stdout.strip()
            unrelated = subprocess.run(
                ["git", "-C", str(corekit), "commit-tree", empty_tree, "-m", "unrelated"],
                text=True, stdout=subprocess.PIPE, check=True,
            ).stdout.strip()
            original_manifest = json.loads(manifest.read_text(encoding="utf-8"))
            original_cargo = (consumer / "Cargo.toml").read_text(encoding="utf-8")
            original_lock = (consumer / "Cargo.lock").read_text(encoding="utf-8")
            for candidate in (before_release, unrelated):
                with self.subTest(candidate=candidate):
                    document = copy.deepcopy(original_manifest)
                    document["consumers"][0]["rust"]["revision"] = candidate
                    manifest.write_text(json.dumps(document), encoding="utf-8")
                    (consumer / "Cargo.toml").write_text(original_cargo.replace(adoption_commit, candidate), encoding="utf-8")
                    (consumer / "Cargo.lock").write_text(original_lock.replace(adoption_commit, candidate), encoding="utf-8")
                    report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
                    self.assertTrue(any(item["code"] == "release.ancestry" for item in report["findings"]), report)
            self.assertEqual(release_commit, original_manifest["consumers"][0]["rust"]["release"]["commit"])

    def test_git_pin_requires_matching_lock_source_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="git")
            lock = (consumer / "Cargo.lock").read_text(encoding="utf-8").replace('version = "0.0.0"', 'version = "9.9.9"', 1)
            (consumer / "Cargo.lock").write_text(lock, encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertEqual(report["status"], "blocked")
            self.assertTrue(any(item["code"] == "rust.lock.version" for item in report["findings"]))

    def test_rust_package_must_be_canonical_before_cargo_checks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, _, _, _ = make_fixture(root, status="git")
            document = json.loads(manifest.read_text(encoding="utf-8"))
            rust = document["consumers"][0]["rust"]
            rust["package"] = "evil-package"
            rust["manifest_paths"] = ["missing/Cargo.toml"]
            manifest.write_text(json.dumps(document), encoding="utf-8")

            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            codes = {item["code"] for item in report["findings"]}
            self.assertEqual(report["status"], "blocked")
            self.assertIn("rust.package", codes)
            self.assertNotIn("rust.manifest.read", codes)
            self.assertNotIn("rust.lock.source", codes)

    def test_rust_adoption_status_is_closed_and_cannot_bypass_lock_checks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="git")
            document = json.loads(manifest.read_text(encoding="utf-8"))
            rust = document["consumers"][0]["rust"]
            rust["status"] = "bogus"
            rust["registry_version"] = "0.0.0"
            lock = (consumer / "Cargo.lock").read_text(encoding="utf-8").replace(
                verify.COREKIT_URL, "https://evil.example/corekit")
            (consumer / "Cargo.lock").write_text(lock, encoding="utf-8")
            manifest.write_text(json.dumps(document), encoding="utf-8")

            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertEqual(report["status"], "blocked")
            self.assertTrue(any(item["code"] == "rust.status" for item in report["findings"]), report)

    def test_missing_rust_adoption_status_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, _, _, _ = make_fixture(root, status="git")
            document = json.loads(manifest.read_text(encoding="utf-8"))
            del document["consumers"][0]["rust"]["status"]
            manifest.write_text(json.dumps(document), encoding="utf-8")

            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertEqual(report["status"], "blocked")
            self.assertTrue(any(item["code"] == "rust.status" for item in report["findings"]), report)

    def test_top_level_release_commit_must_match_corekit_tag(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, _, release_commit, _ = make_fixture(root, status="git")
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["corekit"]["release_commit"] = "f" * 40
            self.assertNotEqual(document["corekit"]["release_commit"], release_commit)
            # Keep each consumer's release evidence truthful: the top-level
            # release record must still be checked independently.
            manifest.write_text(json.dumps(document), encoding="utf-8")

            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertEqual(report["status"], "blocked")
            self.assertTrue(
                any(item["repository"] == "corekit" and item["code"] == "release.tag" for item in report["findings"]),
                report,
            )
            self.assertIn("corekit", report["checked_repositories"])
            self.assertTrue(
                {item["repository"] for item in report["findings"]}.issubset(set(report["checked_repositories"])),
                report,
            )

    def test_registry_pin_requires_exact_crates_io_source_and_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="registry")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertEqual(report["status"], "passed", report)
            lock = (consumer / "Cargo.lock").read_text(encoding="utf-8").replace(
                "registry+https://github.com/rust-lang/crates.io-index", "registry+https://evil.example/index")
            (consumer / "Cargo.lock").write_text(lock, encoding="utf-8")
            blocked = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "rust.lock.registry_source" for item in blocked["findings"]))

    def test_manifest_dependency_version_must_be_exact_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="git")
            cargo = (consumer / "Cargo.toml").read_text(encoding="utf-8").replace('version = "=0.0.0"', 'version = ">=0.0.0"')
            (consumer / "Cargo.toml").write_text(cargo, encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "rust.pin.exact" for item in report["findings"]))

    def test_registry_lock_version_must_match_recorded_pin(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="registry")
            lock = (consumer / "Cargo.lock").read_text(encoding="utf-8").replace(
                'name = "symaira-core-version"\nversion = "0.0.0"',
                'name = "symaira-core-version"\nversion = "0.1.0"',
            )
            (consumer / "Cargo.lock").write_text(lock, encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "rust.lock.version" for item in report["findings"]), report)

    def test_registry_checksum_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="registry")
            lock = (consumer / "Cargo.lock").read_text(encoding="utf-8")
            (consumer / "Cargo.lock").write_text(lock.replace('checksum = "' + "a" * 64 + '"\n', ""), encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "rust.lock.checksum" for item in report["findings"]))

    def test_command_text_without_structured_report_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="git")
            document = json.loads(manifest.read_text(encoding="utf-8"))
            evidence = document["consumers"][0]["rust"]["evidence"]["standalone"]
            evidence.clear()
            evidence.update({"status": "verified", "command": "true"})
            manifest.write_text(json.dumps(document), encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"].startswith("evidence.standalone") for item in report["findings"]))

    def test_report_content_tampering_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="git")
            report_path = consumer / "evidence/standalone.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["observed"]["stdout"] = "tampered\n"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            subprocess.run(["git", "-C", str(consumer), "add", "evidence/standalone.json"], check=True)
            subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "tamper-report"], check=True)
            blocked = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "evidence.standalone.result" for item in blocked["findings"]), blocked)

    def test_staged_evidence_report_is_blocked_until_committed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="git")
            report_path = consumer / "evidence/standalone.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["observed"]["stdout"] = "staged-only\n"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            subprocess.run(["git", "-C", str(consumer), "add", "evidence/standalone.json"], check=True)
            blocked = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            findings = [item for item in blocked["findings"] if item["code"] == "evidence.standalone.report"]
            self.assertTrue(findings, blocked)
            self.assertIn("staged but uncommitted", findings[0]["message"])

    def test_tracked_source_without_real_import_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="git")
            (consumer / "cmd" / "main.go").write_text(
                'package main\nconst fake = "github.com/danieljustus/symaira-corekit/versionkit"\n', encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "go.imports.missing" for item in report["findings"]))

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
