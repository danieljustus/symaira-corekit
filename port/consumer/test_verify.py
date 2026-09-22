#!/usr/bin/env python3
"""Regression tests for the fail-closed consumer verifier."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
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


def pin_consumer_release(document: dict, consumer: Path) -> None:
    """Tag only a disposable fixture snapshot; never a real consumer checkout."""
    snapshot = git(consumer, "rev-parse", "HEAD")
    tag = "v1.0." + git(consumer, "rev-list", "--count", "HEAD")
    git(consumer, "tag", tag)
    document["consumers"][0]["checkout_commit"] = snapshot
    document["consumers"][0]["consumer_release"] = {"tag": tag, "commit": snapshot}


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
                "artifact_sha256": hashlib.sha256((consumer / "bin/fixture").read_bytes()).hexdigest(),
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
        "release_source": "corekit",
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

    init_git(consumer)
    subprocess.run(["git", "-C", str(consumer), "add", "."], check=True)
    subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "fixture"], check=True)
    pin_consumer_release(manifest, consumer)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, corekit, consumer, release_commit, adoption_commit


def release_registry(manifest: Path, consumer: Path) -> None:
    """Add a complete deterministic registry readback to a fixture."""
    checksum = "0123456789abcdef" * 4
    lock_path = consumer / "Cargo.lock"
    lock_path.write_text(
        lock_path.read_text(encoding="utf-8").replace("a" * 64, checksum),
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(consumer), "add", "Cargo.lock"], check=True)
    subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "registry-lock"], check=True)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["corekit"]["rust_registry"] = {
        "package": verify.COREKIT_PACKAGE,
        "status": "released",
        "readback": {
            "package": verify.COREKIT_PACKAGE,
            "version": "0.0.0",
            "owners": ["danieljustus", "crates-io:verified-owner"],
            "index": "https://index.crates.io/2/s/symaira-core-version",
            "public_bytes": checksum,
            "checksum": checksum,
            "source": f"https://crates.io/api/v1/crates/{verify.COREKIT_PACKAGE}/0.0.0",
        },
    }
    pin_consumer_release(document, consumer)
    manifest.write_text(json.dumps(document), encoding="utf-8")


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
        self.assertEqual(report["consumer_count"], 4)
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

    def test_consumer_release_binds_the_exact_consumer_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            original = json.loads(manifest.read_text(encoding="utf-8"))
            snapshot = original["consumers"][0]["checkout_commit"]
            git(consumer, "tag", "v1.2.3")
            git(consumer, "tag", "-a", "v1.2.4", "-m", "annotated fixture release")
            git(consumer, "branch", "v9.9.9")
            git(consumer, "commit", "--allow-empty", "-qm", "post-release")
            later = git(consumer, "rev-parse", "HEAD")
            git(consumer, "tag", "v1.3.0")
            git(consumer, "checkout", "-q", "--detach", snapshot)
            cases = [
                ("lightweight tag", {"tag": "v1.2.3", "commit": snapshot}, None),
                ("annotated tag", {"tag": "v1.2.4", "commit": snapshot}, None),
                ("missing", None, "consumer.release.missing"),
                ("malformed", [], "consumer.release.missing"),
                ("head alias", {"tag": "HEAD", "commit": snapshot}, "consumer.release.shape"),
                ("branch ref", {"tag": "refs/heads/main", "commit": snapshot}, "consumer.release.shape"),
                ("tag ref", {"tag": "refs/tags/v1.2.3", "commit": snapshot}, "consumer.release.shape"),
                ("short revision", {"tag": "v1.2.3", "commit": snapshot[:12]}, "consumer.release.shape"),
                ("branch only", {"tag": "v9.9.9", "commit": snapshot}, "consumer.release.tag"),
                ("library namespace", copy.deepcopy(original["consumers"][0]["rust"]["release"]), "consumer.release.tag"),
                ("wrong target", {"tag": "v1.2.3", "commit": later}, "consumer.release.tag"),
                ("different snapshot", {"tag": "v1.3.0", "commit": later}, "consumer.release.snapshot"),
            ]
            for name, release, expected in cases:
                with self.subTest(case=name):
                    document = copy.deepcopy(original)
                    if release is None:
                        document["consumers"][0].pop("consumer_release", None)
                    else:
                        document["consumers"][0]["consumer_release"] = release
                    manifest.write_text(json.dumps(document), encoding="utf-8")
                    report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
                    if expected is None:
                        self.assertEqual(report["status"], "passed", report)
                    else:
                        self.assertEqual(report["status"], "blocked", report)
                        self.assertIn(expected, {item["code"] for item in report["findings"]}, report)
            # A record-only refresh cannot relabel post-release HEAD as released.
            git(consumer, "checkout", "-q", "--detach", later)
            original["consumers"][0]["checkout_commit"] = later
            original["consumers"][0]["consumer_release"] = {"tag": "v1.2.3", "commit": snapshot}
            manifest.write_text(json.dumps(original), encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertEqual([item["code"] for item in report["findings"]], ["consumer.release.snapshot"])

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
            release_registry(manifest, consumer)
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

    def test_cargo_root_reads_a_nested_workspace_lock(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, adoption_commit = make_fixture(root, status="git")
            nested = consumer / "browse"
            nested.mkdir()
            (consumer / "Cargo.toml").unlink()
            (consumer / "Cargo.lock").rename(nested / "Cargo.lock")
            spec = (
                f'symaira-core-version = {{ git = "{verify.COREKIT_URL}", '
                f'rev = "{adoption_commit}", version = "=0.0.0" }}'
            )
            (nested / "Cargo.toml").write_text(
                '[workspace]\nmembers = ["protocol"]\nresolver = "2"\n\n'
                f"[workspace.dependencies]\n{spec}\n",
                encoding="utf-8",
            )
            (nested / "protocol").mkdir()
            (nested / "protocol" / "Cargo.toml").write_text(
                '[package]\nname = "nested-protocol"\nversion = "0.0.0"\n\n'
                '[dependencies]\nsymaira-core-version.workspace = true\n',
                encoding="utf-8",
            )
            (consumer / "Cargo.toml").write_text("[workspace]\nmembers = []\n", encoding="utf-8")
            (consumer / "Cargo.lock").write_text("version = 4\n", encoding="utf-8")
            document = json.loads(manifest.read_text(encoding="utf-8"))
            rust = document["consumers"][0]["rust"]
            rust["cargo_root"] = "browse"
            rust["manifest_paths"] = ["browse/Cargo.toml", "browse/protocol/Cargo.toml"]
            subprocess.run(["git", "-C", str(consumer), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "nested-workspace"], check=True)
            pin_consumer_release(document, consumer)
            manifest.write_text(json.dumps(document), encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertEqual(report["status"], "passed", report)

    def test_nested_lock_is_not_guessed_without_cargo_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="git")
            nested = consumer / "browse"
            nested.mkdir()
            (consumer / "Cargo.toml").rename(nested / "Cargo.toml")
            (consumer / "Cargo.lock").rename(nested / "Cargo.lock")
            (consumer / "Cargo.toml").write_text("[workspace]\nmembers = []\n", encoding="utf-8")
            (consumer / "Cargo.lock").write_text("version = 4\n", encoding="utf-8")
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["consumers"][0]["rust"]["manifest_paths"] = ["browse/Cargo.toml"]
            subprocess.run(["git", "-C", str(consumer), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "nested-without-cargo-root"], check=True)
            document["consumers"][0]["checkout_commit"] = git(consumer, "rev-parse", "HEAD")
            manifest.write_text(json.dumps(document), encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            codes = [item["code"] for item in report["findings"]]
            self.assertIn("rust.lock.unique", codes, report)

    def test_cargo_root_must_stay_inside_the_checkout(self) -> None:
        for cargo_root in ("../outside", "target", 7):
            with self.subTest(cargo_root=cargo_root), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                manifest, corekit, _, _, _ = make_fixture(root, status="git")
                document = json.loads(manifest.read_text(encoding="utf-8"))
                document["consumers"][0]["rust"]["cargo_root"] = cargo_root
                manifest.write_text(json.dumps(document), encoding="utf-8")
                report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
                self.assertTrue(any(item["code"] == "rust.cargo_root" for item in report["findings"]), report)

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


    def test_checkout_head_must_match_recorded_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["consumers"][0]["checkout_commit"] = "0" * 40
            manifest.write_text(json.dumps(document), encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "checkout.commit" for item in report["findings"]), report)

    def test_tracked_and_untracked_source_changes_block_snapshot(self) -> None:
        for untracked in (False, True):
            with self.subTest(untracked=untracked), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                manifest, corekit, consumer, _, _ = make_fixture(root)
                if untracked:
                    (consumer / "cmd" / "extra.go").write_text("package main\n", encoding="utf-8")
                else:
                    (consumer / "cmd" / "main.go").write_text("package main\n", encoding="utf-8")
                report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
                self.assertTrue(any(item["code"] == "checkout.dirty" for item in report["findings"]), report)

    def test_selected_checkout_symlink_cannot_escape_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            moved = root / "outside-consumer"
            consumer.rename(moved)
            os.symlink(moved, root / "fixture")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "checkout.path" for item in report["findings"]), report)

    def test_evidence_paths_cannot_escape_through_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            report_path = consumer / "evidence/standalone.json"
            outside = root / "outside-report.json"
            report_path.rename(outside)
            os.symlink(outside, report_path)
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "evidence.standalone.report" for item in report["findings"]), report)

    def test_artifact_tampering_and_wrong_digest_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            (consumer / "bin/fixture").write_text("tampered\n", encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "evidence.standalone.artifact.sha256" for item in report["findings"]), report)

            # Commit a report with a wrong digest and move the recorded snapshot
            # with it, so the digest check is isolated from dirty-state checks.
            report_path = consumer / "evidence/standalone.json"
            report_document = json.loads(report_path.read_text(encoding="utf-8"))
            report_document["artifact_sha256"] = "0" * 64
            report_path.write_text(json.dumps(report_document), encoding="utf-8")
            subprocess.run(["git", "-C", str(consumer), "add", "."], check=True)
            subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "wrong-digest"], check=True)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["consumers"][0]["checkout_commit"] = git(consumer, "rev-parse", "HEAD")
            manifest.write_text(json.dumps(document), encoding="utf-8")
            blocked = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "evidence.standalone.artifact.sha256" for item in blocked["findings"]), blocked)

    def test_symlink_and_nonregular_artifacts_are_blocked(self) -> None:
        for kind in ("symlink", "directory"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                manifest, corekit, consumer, _, _ = make_fixture(root)
                artifact = consumer / "bin/fixture"
                artifact.unlink()
                if kind == "symlink":
                    outside = root / "outside-artifact"
                    outside.write_text("artifact\n", encoding="utf-8")
                    os.symlink(outside, artifact)
                else:
                    artifact.mkdir()
                report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
                self.assertTrue(any(item["code"] == "evidence.standalone.artifact" for item in report["findings"]), report)

    def test_consumer_release_reference_requires_tagged_semver(self) -> None:
        for reference in ("HEAD", "main", "refs/heads/main", "refs/tags/v0.17.0"):
            with self.subTest(reference=reference), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                manifest, corekit, _, _, _ = make_fixture(root)
                document = json.loads(manifest.read_text(encoding="utf-8"))
                document["consumers"][0]["rust"]["release"]["tag"] = reference
                manifest.write_text(json.dumps(document), encoding="utf-8")
                report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
                self.assertTrue(any(item["code"] == "release.shape" for item in report["findings"]), report)

    def test_consumer_release_tag_must_resolve_to_recorded_commit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, _, _, _ = make_fixture(root)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["consumers"][0]["rust"]["release"]["tag"] = "v9.9.9"
            manifest.write_text(json.dumps(document), encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "release.tag" for item in report["findings"]), report)

    def test_release_namespace_mapping_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, _, _, _ = make_fixture(root)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            del document["consumers"][0]["rust"]["release_source"]
            manifest.write_text(json.dumps(document), encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "release.namespace" for item in report["findings"]), report)

    def test_all_duplicate_go_pins_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            (consumer / "go.mod").write_text(
                "module example.invalid/consumer\n\nrequire github.com/danieljustus/symaira-corekit v0.17.0\n\n"
                "require (\n  github.com/danieljustus/symaira-corekit v0.18.0\n)\n",
                encoding="utf-8",
            )
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            codes = {item["code"] for item in report["findings"]}
            self.assertIn("go.pin.duplicate", codes)
            self.assertIn("go.pin.inconsistent", codes)

    def test_registry_accepts_exact_string_cargo_form(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="registry")
            cargo = (consumer / "Cargo.toml").read_text(encoding="utf-8").replace(
                'symaira-core-version = { version = "=0.0.0" }',
                'symaira-core-version = "=0.0.0"',
            )
            (consumer / "Cargo.toml").write_text(cargo, encoding="utf-8")
            subprocess.run(["git", "-C", str(consumer), "add", "Cargo.toml"], check=True)
            subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "string-pin"], check=True)
            release_registry(manifest, consumer)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["consumers"][0]["checkout_commit"] = git(consumer, "rev-parse", "HEAD")
            manifest.write_text(json.dumps(document), encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertEqual(report["status"], "passed", report)

    def test_registry_string_cargo_range_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="registry")
            cargo = (consumer / "Cargo.toml").read_text(encoding="utf-8").replace(
                'symaira-core-version = { version = "=0.0.0" }',
                'symaira-core-version = ">=0.0.0"',
            )
            (consumer / "Cargo.toml").write_text(cargo, encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "rust.pin.exact" for item in report["findings"]), report)


    def test_ignored_declared_go_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            (consumer / ".gitignore").write_text("alt/go.mod\n", encoding="utf-8")
            (consumer / "alt").mkdir()
            (consumer / "alt/go.mod").write_text(
                "module example.invalid/alt\n\n"
                "require github.com/danieljustus/symaira-corekit v0.17.0\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "-C", str(consumer), "add", ".gitignore"], check=True)
            subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "ignore-alt-module"], check=True)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["consumers"][0]["checkout_commit"] = git(consumer, "rev-parse", "HEAD")
            document["consumers"][0]["pins"].append("alt/go.mod")
            manifest.write_text(json.dumps(document), encoding="utf-8")

            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            codes = {item["code"] for item in report["findings"]}
            self.assertIn("go.manifest.untracked", codes, report)
            self.assertIn("checkout.untracked_source", codes, report)

    def test_evidence_artifact_rejects_ignored_binlink_directory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            (consumer / ".gitignore").write_text("binlink\n", encoding="utf-8")
            os.symlink("bin", consumer / "binlink")
            subprocess.run(["git", "-C", str(consumer), "add", ".gitignore"], check=True)
            subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "ignore-binlink"], check=True)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            for name in ("standalone", "rollback"):
                evidence = document["consumers"][0]["rust"]["evidence"][name]
                evidence["artifact"] = "binlink/fixture"
                report_path = consumer / evidence["report"]
                report_document = json.loads(report_path.read_text(encoding="utf-8"))
                report_document["artifact"] = "binlink/fixture"
                report_path.write_text(json.dumps(report_document), encoding="utf-8")
            subprocess.run(["git", "-C", str(consumer), "add", "evidence"], check=True)
            subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "binlink-evidence"], check=True)
            document["consumers"][0]["checkout_commit"] = git(consumer, "rev-parse", "HEAD")
            manifest.write_text(json.dumps(document), encoding="utf-8")

            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            artifact_findings = [
                item for item in report["findings"]
                if item["code"] in {"evidence.standalone.artifact", "evidence.rollback.artifact"}
            ]
            self.assertEqual({item["repository"] for item in artifact_findings}, {"example/fixture"}, report)
            self.assertEqual(len(artifact_findings), 2, report)
    def test_not_adopted_scans_tracked_cargo_manifests_and_locks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["consumers"][0]["rust"] = {"status": "not_adopted"}
            manifest.write_text(json.dumps(document), encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            present = [item for item in report["findings"] if item["code"] == "rust.not_adopted.present"]
            self.assertEqual({item["message"].rsplit(" ", 1)[-1] for item in present}, {"Cargo.toml", "Cargo.lock"}, report)

    def test_not_adopted_rejects_aliased_dependency_without_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            cargo_path = consumer / "Cargo.toml"
            cargo_path.write_text(
                cargo_path.read_text(encoding="utf-8").replace(
                    'symaira-core-version = {',
                    'core_version = { package = "symaira-core-version",',
                ),
                encoding="utf-8",
            )
            git(consumer, "rm", "Cargo.lock")
            git(consumer, "add", "Cargo.toml")
            git(consumer, "commit", "-qm", "alias-without-lockfile")
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["consumers"][0]["rust"] = {"status": "not_adopted"}
            pin_consumer_release(document, consumer)
            manifest.write_text(json.dumps(document), encoding="utf-8")

            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertEqual(report["status"], "blocked", report)
            self.assertEqual(
                [item["code"] for item in report["findings"]],
                ["rust.not_adopted.present"],
                report,
            )
            self.assertTrue(report["findings"][0]["message"].endswith("Cargo.toml"), report)

    def test_declared_cargo_paths_reject_forbidden_components_and_symlinks(self) -> None:
        for relative in ("vendor/Cargo.toml", "target/Cargo.toml", ".worktrees/Cargo.toml"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                manifest, corekit, _, _, _ = make_fixture(root)
                document = json.loads(manifest.read_text(encoding="utf-8"))
                document["consumers"][0]["rust"]["manifest_paths"] = [relative]
                manifest.write_text(json.dumps(document), encoding="utf-8")
                report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
                self.assertTrue(any(item["code"] == "rust.manifest.path" for item in report["findings"]), report)

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            (consumer / "real").mkdir()
            os.symlink("real", consumer / "rustlink")
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["consumers"][0]["rust"]["manifest_paths"] = ["rustlink/Cargo.toml"]
            manifest.write_text(json.dumps(document), encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "rust.manifest.path" for item in report["findings"]), report)

    def test_ignored_symlink_directory_cannot_hide_cargo_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            hidden = root / "hidden-rust"
            hidden.mkdir()
            (hidden / "Cargo.toml").write_text(
                '[package]\nname = "symaira-core-version"\nversion = "0.0.0"\n', encoding="utf-8"
            )
            (consumer / ".gitignore").write_text("rustlink\n", encoding="utf-8")
            os.symlink(hidden, consumer / "rustlink")
            subprocess.run(["git", "-C", str(consumer), "add", ".gitignore"], check=True)
            subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "ignore-rustlink"], check=True)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["consumers"][0]["checkout_commit"] = git(consumer, "rev-parse", "HEAD")
            manifest.write_text(json.dumps(document), encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "checkout.path" for item in report["findings"]), report)

    def test_registry_adoption_is_blocked_until_top_level_release(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="registry")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "registry.status" for item in report["findings"]), report)
            self.assertNotEqual(report["status"], "passed")

    def test_registry_readback_rejects_fake_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root, status="registry")
            release_registry(manifest, consumer)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["corekit"]["rust_registry"]["readback"]["checksum"] = "a" * 64
            manifest.write_text(json.dumps(document), encoding="utf-8")
            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertTrue(any(item["code"] == "registry.checksum" for item in report["findings"]), report)

    def test_go_mod_and_work_replace_directives_are_forbidden(self) -> None:
        for filename, replacement in (
            ("go.mod", "replace github.com/danieljustus/symaira-corekit => ../local-corekit\n"),
            ("go.work", "go 1.26.0\n\nuse .\n\nreplace github.com/danieljustus/symaira-corekit => ../local-corekit\n"),
        ):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                manifest, corekit, consumer, _, _ = make_fixture(root)
                path = consumer / filename
                existing = path.read_text(encoding="utf-8") if path.exists() else ""
                path.write_text(existing + replacement, encoding="utf-8")
                subprocess.run(["git", "-C", str(consumer), "add", filename], check=True)
                subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "forbidden-replace"], check=True)
                document = json.loads(manifest.read_text(encoding="utf-8"))
                document["consumers"][0]["checkout_commit"] = git(consumer, "rev-parse", "HEAD")
                manifest.write_text(json.dumps(document), encoding="utf-8")
                report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
                self.assertTrue(any(item["code"] == "go.replace.forbidden" for item in report["findings"]), report)


    def test_not_adopted_ignores_unrelated_manifest_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            (consumer / "Cargo.toml").write_text(
                '[package]\nname = "fixture"\nversion = "1.0.0"\n'
                '[package.metadata]\nsymaira-core-version = "informational metadata"\n',
                encoding="utf-8",
            )
            git(consumer, "rm", "Cargo.lock")
            git(consumer, "add", "Cargo.toml")
            git(consumer, "commit", "-qm", "metadata-only-package-name")
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["consumers"][0]["rust"] = {"status": "not_adopted"}
            pin_consumer_release(document, consumer)
            manifest.write_text(json.dumps(document), encoding="utf-8")

            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertEqual(report["status"], "passed", report)
            self.assertFalse(
                any(item["code"] == "rust.not_adopted.present" for item in report["findings"]),
                report,
            )


    def test_not_adopted_rejects_workspace_dependency_alias(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            cargo_path = consumer / "Cargo.toml"
            cargo_path.write_text(
                "[workspace]\n"
                "members = [\".\"]\n\n"
                "[workspace.dependencies]\n"
                "core_version = { package = \"symaira-core-version\", version = \"=0.0.0\" }\n",
                encoding="utf-8",
            )
            git(consumer, "rm", "Cargo.lock")
            git(consumer, "add", "Cargo.toml")
            git(consumer, "commit", "-qm", "workspace-alias-without-lockfile")
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["consumers"][0]["rust"] = {"status": "not_adopted"}
            pin_consumer_release(document, consumer)
            manifest.write_text(json.dumps(document), encoding="utf-8")

            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertEqual(report["status"], "blocked", report)
            self.assertEqual(
                [item["code"] for item in report["findings"]],
                ["rust.not_adopted.present"],
                report,
            )
            self.assertTrue(report["findings"][0]["message"].endswith("Cargo.toml"), report)

    def test_generated_trees_are_excluded_from_ignored_source_scan(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            generated = (
                ".agents", ".agentsroom", ".app-test-build", ".build", ".claude",
                ".coverage-html", ".cursor", ".mypy_cache", ".omo", ".opencode",
                ".phase0-evidence", ".playwright-cli", ".playwright-mcp",
                ".pytest_cache", ".ruff_cache", ".sisyphus", ".swiftpm", ".venv",
                ".windsurf", ".worktrees", "build", "coverage", "dist",
                "node_modules", "target", "target-run", "vendor",
            )
            (consumer / ".gitignore").write_text("\n".join(generated) + "\n", encoding="utf-8")
            for directory in generated:
                path = consumer / directory
                path.mkdir(parents=True)
                (path / "generated.go").write_text(
                    'package generated\nimport _ "github.com/danieljustus/symaira-corekit/versionkit"\n',
                    encoding="utf-8",
                )
            subprocess.run(["git", "-C", str(consumer), "add", ".gitignore"], check=True)
            subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "ignore-generated-trees"], check=True)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            pin_consumer_release(document, consumer)
            manifest.write_text(json.dumps(document), encoding="utf-8")

            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertEqual(report["status"], "passed", report)

    def test_symlinked_generated_tree_is_excluded_like_a_real_one(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            external = root / "external-build-volume"
            external.mkdir()
            (external / "generated.rs").write_text("fn main() {}\n", encoding="utf-8")
            (consumer / ".gitignore").write_text("target\n", encoding="utf-8")
            os.symlink(external, consumer / "target")
            subprocess.run(["git", "-C", str(consumer), "add", ".gitignore"], check=True)
            subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "ignore-target"], check=True)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            pin_consumer_release(document, consumer)
            manifest.write_text(json.dumps(document), encoding="utf-8")

            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertEqual(report["status"], "passed", report)

    def test_agent_tooling_symlink_trees_are_excluded_from_the_walk(self) -> None:
        """Untracked tooling symlinks under .agents/.windsurf are not findings."""
        for shape in ("symlink-dir", "nested-symlink"):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                manifest, corekit, consumer, _, _ = make_fixture(root)
                (consumer / "skills").mkdir()
                (consumer / "skills" / "skill.md").write_text("name: fixture\n", encoding="utf-8")
                (consumer / ".gitignore").write_text(".agents\n.windsurf\nrustlink\n", encoding="utf-8")
                subprocess.run(["git", "-C", str(consumer), "add", ".gitignore", "skills"], check=True)
                subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "ignore-agent-tooling"], check=True)
                document = json.loads(manifest.read_text(encoding="utf-8"))
                pin_consumer_release(document, consumer)
                manifest.write_text(json.dumps(document), encoding="utf-8")
                for name in (".agents", ".windsurf"):
                    path = consumer / name
                    if shape == "symlink-dir":
                        os.symlink("skills", path)
                    else:
                        (path / "skills").mkdir(parents=True)
                        os.symlink("../../skills", path / "skills" / "symaira-eraseme")
                # The walk only runs on a clean snapshot: prove the fixture is
                # clean so a missing finding cannot come from an early return.
                self.assertEqual(git(consumer, "status", "--porcelain=v1", "--untracked-files=all"), "")
                report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
                self.assertFalse(
                    [item for item in report["findings"] if item["code"] == "checkout.path"],
                    report,
                )
                self.assertEqual(report["status"], "passed", report)

                # Negative control: an equally ignored symlink directory that
                # is not in the forbidden set must still be reported, so the
                # exclusion above is name-scoped rather than walk-wide.
                os.symlink("skills", consumer / "rustlink")
                self.assertEqual(git(consumer, "status", "--porcelain=v1", "--untracked-files=all"), "")
                blocked = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
                path_findings = [
                    item for item in blocked["findings"] if item["code"] == "checkout.path"
                ]
                self.assertEqual(
                    [item["message"] for item in path_findings],
                    ["checkout contains a symlink directory: rustlink"],
                    blocked,
                )
                self.assertEqual(len(blocked["findings"]), 1, blocked)

    def test_tracked_paths_under_agent_tooling_dirs_are_rejected(self) -> None:
        """Excluding a tree from the walk must not exempt its tracked paths."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            manifest, corekit, consumer, _, _ = make_fixture(root)
            planted = (
                ".agents/skills/planted.md",
                ".windsurf/rules/planted.md",
            )
            for relative in planted:
                path = consumer / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("tracked\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(consumer), "add", ".agents", ".windsurf"], check=True)
            subprocess.run(["git", "-C", str(consumer), "commit", "-qm", "tracked-agent-tooling"], check=True)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            pin_consumer_release(document, consumer)
            manifest.write_text(json.dumps(document), encoding="utf-8")

            report = verify.verify_manifest(manifest, workspace_root=root, corekit_root=corekit)
            self.assertEqual(report["status"], "blocked", report)
            self.assertEqual({item["code"] for item in report["findings"]}, {"checkout.path"}, report)
            messages = {item["message"] for item in report["findings"]}
            for relative in planted:
                self.assertIn(f"tracked path is unsafe or forbidden: {relative}", messages)


if __name__ == "__main__":
    unittest.main()
