"""Focused FS/SEC oracle guard tests; all observations here are synthetic structure only.

These tests do not run or impersonate Go, Cargo, Git, Rust, native capture, or
native acceptance. Real native evidence is produced only by fs_secret_oracle.py
with a fresh pinned Go execution and then independently anchored for replay.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import fs_secret_oracle as oracle
from fs_secret_anchors import TRUSTED_CAPTURE_SHA256


NATIVE = ("darwin", "arm64")


def _record(path: str, fill: str) -> dict[str, str]:
    return {"path": path, "sha256": hashlib.sha256(fill.encode()).hexdigest()}


def _synthetic_payload() -> dict:
    """Make a schema-only object; never an oracle result or native observation."""
    candidate_files = [
        _record("candidate/Cargo.lock", "lock"),
        _record("candidate/scripts/rust-port/fs_secret_oracle.py", "capture harness"),
        _record("candidate/scripts/rust-port/go-oracle/cmd/fssecret/main.go", "current helper"),
    ]
    oracle_files = [
        _record("oracle/fsutil/atomicwrite.go", "source"),
        _record("oracle/fsutil/pathutil.go", "source"),
        _record("oracle/fsutil/safewrite.go", "source"),
        _record("oracle/secretref/secretref.go", "source"),
        _record("oracle/secretref/symvault.go", "source"),
    ]
    files = candidate_files + oracle_files + [
        _record("modules/current-helper/effective.mod", "quoted replacement"),
        _record("modules/replacement/go.sum", "historical module sum"),
        _record("sdk/bin/go", "compiler hash only"),
        _record("sdk/pkg/tool/darwin_arm64/compile", "compiler tool hash only"),
    ]
    files.sort(key=lambda item: item["path"])
    groups = oracle._group_digests(files)
    cases = {case_id: {"outcomes": {}} for case_id in oracle.CASE_IDS}
    cases["FS-001"] = {"outcomes": {"valid/file": {"ok": True}}}
    controls = {
        "0000": False, "001f": False, "0020": True, "007e": True,
        "007f": True, "0080": True, "0085": True, "009f": True, "00a0": True,
    }
    empty_digest = hashlib.sha256(b"").hexdigest()

    def command(name: str) -> dict:
        return {
            "id": name,
            "exit_code": 0,
            "timed_out": False,
            "output_exceeded": False,
            "cleanup_verified": True,
            "stdout_bytes": 0,
            "stderr_bytes": 0,
            "stdout_sha256": empty_digest,
            "stderr_sha256": empty_digest,
        }

    commands = [command(name) for name in sorted(oracle.REQUIRED_COMMANDS)]
    commands.append(command("go-env-000"))
    capture = {
        "oracle": {
            "commit": oracle.ORACLE,
            "source_sha256": "a" * 64,
            "source_files": [
                _record("fsutil/atomicwrite.go", "source"),
                _record("fsutil/pathutil.go", "source"),
                _record("fsutil/safewrite.go", "source"),
                _record("secretref/secretref.go", "source"),
                _record("secretref/symvault.go", "source"),
            ],
        },
        "candidate": {
            "head_before": "b" * 40,
            "head_after": "b" * 40,
            "clean_before": True,
            "clean_after": True,
            "go_helper_sha256": candidate_files[-1]["sha256"],
            "files": candidate_files,
        },
        "native": {"goos": NATIVE[0], "goarch": NATIVE[1]},
        "go": {
            "version": "go version go1.26.6 darwin/arm64",
            "goversion": "go1.26.6",
            "goos": NATIVE[0],
            "goarch": NATIVE[1],
            "binary_sha256": next(item["sha256"] for item in files if item["path"] == "sdk/bin/go"),
            "probe_binary_sha256": "c" * 64,
            "goroot_label": "installed-go-sdk",
            "gomodcache_policy": "existing-cache-offline-read-only",
            "sdk_sha256": groups["sdk"],
            "modules_sha256": groups["modules"],
        },
        "inputs": {
            "before_sha256": oracle._inventory_digest(files),
            "after_sha256": oracle._inventory_digest(files),
            "files": files,
            "groups": groups,
        },
        "commands": commands,
        "raw": {
            "artifact_id": "private-run",
            "observations": {
                "cases": {
                    "exit_code": 0, "stdout_bytes": 0, "stderr_bytes": 0,
                    "stdout_sha256": empty_digest, "stderr_sha256": empty_digest,
                },
                "path_controls": {
                    "exit_code": 0, "stdout_bytes": 0, "stderr_bytes": 0,
                    "stdout_sha256": empty_digest, "stderr_sha256": empty_digest,
                },
            },
        },
        "case_inventory": {
            "case_ids": list(oracle.CASE_IDS),
            "path_control_ids": list(oracle.PATH_CONTROL_IDS),
        },
    }
    return {
        "schema_version": 1,
        "capture": capture,
        "observations": {
            "oracle_commit": oracle.ORACLE,
            "native_target": "darwin-arm64",
            "cases": cases,
            "path_controls": controls,
        },
    }


def _bytes(payload: dict) -> bytes:
    return oracle._json_bytes(payload)


def _anchored_validate(payload: dict, native=NATIVE) -> dict:
    raw = _bytes(payload)
    return oracle.validate_capture_bytes(raw, native, anchors={oracle._target_key(*native): oracle.sha256(raw)})


class FrozenOracleGuardTests(unittest.TestCase):
    def test_anchor_map_is_separate_and_well_formed(self):
        self.assertIsInstance(TRUSTED_CAPTURE_SHA256, dict)
        self.assertIsInstance(oracle.TRUSTED_CAPTURE_SHA256, dict)
        for target, digest in TRUSTED_CAPTURE_SHA256.items():
            self.assertRegex(target, r"^(darwin|linux|windows)-(amd64|arm64)$")
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertNotIn("register", oracle.main.__code__.co_names)

    def test_capture_refuses_to_discover_a_parent_git_checkout(self):
        with tempfile.TemporaryDirectory(prefix="fs-secret-no-git-root-") as directory:
            with self.assertRaisesRegex(oracle.OracleError, "refusing parent discovery"):
                oracle._require_explicit_git_root(Path(directory))

    def test_raw_go_bytes_are_retained_before_failure_classification(self):
        with tempfile.TemporaryDirectory(prefix="fs-secret-raw-retention-") as directory:
            artifact_root = Path(directory) / "evidence"
            artifact_root.mkdir()
            recorder = oracle._Recorder(artifact_root)
            failed = subprocess.CompletedProcess(["synthetic"], 7, bytes((114, 97, 119, 0, 13, 10)), bytes((100, 105, 97, 103, 110, 111, 115, 116, 105, 99, 255)))
            with mock.patch.object(oracle, "run_checked", return_value=failed):
                result = recorder.run("go-cases", ["synthetic"], cwd=Path(directory), env={}, timeout=1)
            with self.assertRaisesRegex(oracle.OracleError, "stage failed"):
                oracle._require_zero(result, "run pinned Go FS/SEC oracle")
            self.assertEqual((artifact_root / "raw/go-cases.stdout.raw").read_bytes(), failed.stdout)
            self.assertEqual((artifact_root / "raw/go-cases.stderr.raw").read_bytes(), failed.stderr)
            report = json.loads((artifact_root / "run.json").read_bytes())
            self.assertEqual(report["commands"][0]["exit_code"], 7)
            self.assertEqual(report["commands"][0]["stdout_sha256"], hashlib.sha256(failed.stdout).hexdigest())
            self.assertEqual(report["commands"][0]["stderr_sha256"], hashlib.sha256(failed.stderr).hexdigest())

    def test_default_replay_fails_before_any_subprocess_without_reviewed_anchor(self):
        native = oracle._native_goos_arch()
        if oracle._target_key(*native) in TRUSTED_CAPTURE_SHA256:
            self.skipTest("this native target now has a separately reviewed anchor")
        with mock.patch.object(oracle, "run_checked", side_effect=AssertionError("replay tried Go/Git/Cargo without an anchor")) as runner:
            with self.assertRaisesRegex(oracle.OracleError, "no independently reviewed.*anchor"):
                oracle.replay_native()
        runner.assert_not_called()

    def test_capture_requires_go_oracle_opt_in_before_go_or_git(self):
        with tempfile.TemporaryDirectory(prefix="fs-secret-opt-in-guard-") as directory:
            output = Path(directory) / "native.json"
            artifacts = Path(directory) / "raw"
            with mock.patch.dict(os.environ, {"GO_ORACLE": "0"}), mock.patch.object(
                oracle, "run_checked", side_effect=AssertionError("Go/Git started without opt-in")
            ) as runner:
                code = oracle.main(["--capture", "--output", str(output), "--artifacts-dir", str(artifacts)])
            self.assertEqual(code, 1)
            runner.assert_not_called()
            self.assertFalse(output.exists())
            self.assertFalse(artifacts.exists())

    def test_synthetic_structural_object_passes_only_with_explicit_test_anchor(self):
        # This deliberate test-only anchor authenticates no native observation.
        accepted = _anchored_validate(_synthetic_payload())
        self.assertEqual(accepted["capture"]["case_inventory"]["case_ids"], list(oracle.CASE_IDS))
        self.assertEqual(len(accepted["observations"]["path_controls"]), 9)

    def test_actual_validator_rejects_missing_null_and_wrong_json_types(self):
        mutations = [
            ("schema_version bool-is-not-int", lambda p: p.update(schema_version=True), "unsupported frozen-v1 schema_version"),
            ("clean int-is-not-bool", lambda p: p["capture"]["candidate"].update(clean_before=1), "clean candidate"),
            ("missing candidate head", lambda p: p["capture"]["candidate"].pop("head_after"), "candidate source identity schema"),
            ("wrong oracle pin", lambda p: p["capture"]["oracle"].update(commit="d" * 40), "production-oracle identity"),
            ("missing native arch", lambda p: p["capture"]["native"].pop("goarch"), "native target schema"),
            ("exit bool-is-not-int", lambda p: p["capture"]["commands"][0].update(exit_code=False), "did not exit successfully"),
            ("stdout count bool-is-not-int", lambda p: p["capture"]["commands"][0].update(stdout_bytes=True), "byte count"),
            ("nonboolean path value", lambda p: p["observations"]["path_controls"].update({"007f": 1}), "JSON booleans"),
            ("missing one case", lambda p: p["observations"]["cases"].pop("SEC-006"), "all 13 FS/SEC cases"),
            ("missing one ASCII key", lambda p: p["observations"]["path_controls"].pop("0085"), "all nine ASCII path-control keys"),
            ("incomplete declared IDs", lambda p: p["capture"]["case_inventory"]["case_ids"].pop(), "does not declare all required"),
            ("false strict DEL observation", lambda p: p["observations"]["path_controls"].update({"007f": False}), "Go DEL/C1 acceptance"),
            ("wrong input group digest", lambda p: p["capture"]["inputs"]["groups"].update({"sdk": "e" * 64}), "group digest mismatch"),
            ("changed post inventory", lambda p: p["capture"]["inputs"].update(after_sha256="f" * 64), "inputs changed"),
        ]
        for name, mutate, message in mutations:
            with self.subTest(name=name):
                payload = _synthetic_payload()
                mutate(payload)
                raw = _bytes(payload)
                trusted = {oracle._target_key(*NATIVE): oracle.sha256(raw)}
                with self.assertRaisesRegex(oracle.OracleError, message):
                    oracle.validate_capture_bytes(raw, NATIVE, anchors=trusted)

    def test_anchor_type_syntax_and_digest_are_strict(self):
        raw = _bytes(_synthetic_payload())
        for invalid in (None, True, 7, "A" * 64, "0" * 63, "g" * 64):
            with self.subTest(anchor=repr(invalid)):
                with self.assertRaisesRegex(oracle.OracleError, "not lowercase SHA-256"):
                    oracle.validate_capture_bytes(raw, NATIVE, anchors={oracle._target_key(*NATIVE): invalid})
        with self.assertRaisesRegex(oracle.OracleError, "no independently reviewed"):
            oracle.validate_capture_bytes(raw, NATIVE, anchors={})

    def test_coordinated_observation_and_editable_hash_changes_fail_fixed_anchor(self):
        original = _synthetic_payload()
        original_bytes = _bytes(original)
        external = {oracle._target_key(*NATIVE): oracle.sha256(original_bytes)}
        self.assertEqual(oracle.validate_capture_bytes(original_bytes, NATIVE, anchors=external)["schema_version"], 1)

        changed = copy.deepcopy(original)
        changed["observations"]["cases"]["FS-001"]["outcomes"]["valid/file"]["ok"] = False
        editable_hash = hashlib.sha256(b"changed probe stdout").hexdigest()
        changed["capture"]["raw"]["observations"]["cases"]["stdout_sha256"] = editable_hash
        for record in changed["capture"]["commands"]:
            if record["id"] == "go-cases":
                record["stdout_sha256"] = editable_hash
        changed_bytes = _bytes(changed)
        # Even internally refreshed metadata and a refreshed sidecar-style hash
        # are not the separately reviewed anchor.
        refreshed_editable_anchor = {oracle._target_key(*NATIVE): oracle.sha256(changed_bytes)}
        self.assertEqual(oracle.validate_capture_bytes(changed_bytes, NATIVE, anchors=refreshed_editable_anchor)["schema_version"], 1)
        with self.assertRaisesRegex(oracle.OracleError, "independent trusted anchor"):
            oracle.validate_capture_bytes(changed_bytes, NATIVE, anchors=external)

    def test_native_platform_and_clean_source_mutations_reject_at_validator(self):
        payload = _synthetic_payload()
        raw = _bytes(payload)
        linux_anchor = {"linux-amd64": oracle.sha256(raw)}
        with self.assertRaisesRegex(oracle.OracleError, "native OS/architecture"):
            oracle.validate_capture_bytes(raw, ("linux", "amd64"), anchors=linux_anchor)

        dirty = copy.deepcopy(payload)
        dirty["capture"]["candidate"]["clean_after"] = False
        with self.assertRaisesRegex(oracle.OracleError, "clean candidate"):
            _anchored_validate(dirty)

        changed_head = copy.deepcopy(payload)
        changed_head["capture"]["candidate"]["head_after"] = "d" * 40
        with self.assertRaisesRegex(oracle.OracleError, "HEAD changed"):
            _anchored_validate(changed_head)

    def test_duplicate_json_keys_reject_after_anchor_check(self):
        raw = b'{"schema_version":1,"schema_version":1,"capture":{},"observations":{}}'
        with self.assertRaisesRegex(oracle.OracleError, "duplicate JSON object key"):
            oracle.validate_capture_bytes(raw, NATIVE, anchors={oracle._target_key(*NATIVE): oracle.sha256(raw)})

    def test_fixture_reader_reads_raw_bytes_once_and_rejects_symlinks(self):
        raw = _bytes(_synthetic_payload())
        anchors = {oracle._target_key(*NATIVE): oracle.sha256(raw)}
        with tempfile.TemporaryDirectory(prefix="fs-secret-read-once-") as directory:
            path = Path(directory) / "fixture.json"
            path.write_bytes(raw)
            original = Path.read_bytes
            calls = []

            def counted(instance):
                if instance == path:
                    calls.append(instance)
                return original(instance)

            with mock.patch.object(Path, "read_bytes", counted):
                loaded, payload = oracle.read_capture_once(path, NATIVE, anchors=anchors)
            self.assertEqual(calls, [path])
            self.assertEqual(loaded, raw)
            self.assertEqual(payload["schema_version"], 1)

            link = Path(directory) / "linked.json"
            link.symlink_to(path)
            with self.assertRaisesRegex(oracle.OracleError, "regular non-symlink"):
                oracle.read_capture_once(link, NATIVE, anchors=anchors)

    def test_path_control_schema_requires_exact_ids_and_python_bools(self):
        payload = _synthetic_payload()
        self.assertEqual(tuple(payload["observations"]["path_controls"]), oracle.PATH_CONTROL_IDS)
        payload["observations"]["path_controls"]["0080"] = 1
        with self.assertRaisesRegex(oracle.OracleError, "JSON booleans"):
            _anchored_validate(payload)

    def test_windows_and_unix_normalization_matches_existing_diff_contract(self):
        unix = {
            "oracle_commit": oracle.ORACLE,
            "native_target": "darwin-arm64",
            "cases": {"SEC-005": {"platform": "darwin", "mode": 384, "files": [{"mode": 448}], "value": "unchanged"}},
        }
        normalized_unix = oracle.normalized_probe(unix)
        self.assertNotIn("native_target", normalized_unix)
        self.assertEqual(normalized_unix["cases"]["SEC-005"]["platform"], "${TARGET_OS}")
        self.assertEqual(normalized_unix["cases"]["SEC-005"]["mode"], 384)
        self.assertEqual(normalized_unix["cases"]["SEC-005"]["files"][0]["mode"], 448)
        self.assertEqual(normalized_unix["cases"]["SEC-005"]["value"], "unchanged")

        windows = copy.deepcopy(unix)
        windows["native_target"] = "windows-amd64"
        normalized_windows = oracle.normalized_probe(windows)
        case = normalized_windows["cases"]["SEC-005"]
        self.assertEqual(case["platform"], "${TARGET_OS}")
        self.assertNotIn("mode", case)
        self.assertNotIn("mode", case["files"][0])
        self.assertEqual(case["value"], "unchanged")

    def test_real_comparison_rejects_one_mutated_fs001_observation(self):
        payload = _synthetic_payload()["observations"]
        actual = copy.deepcopy(payload)
        actual["native_target"] = "macos-aarch64"
        changed = copy.deepcopy(payload)
        changed["cases"] = oracle.mutate_known_observation({"cases": payload["cases"]})["cases"]
        with mock.patch.object(oracle, "_native_goos_arch", return_value=NATIVE):
            oracle.compare_observations(payload, actual)
            with self.assertRaisesRegex(oracle.OracleError, "complete normalized Go FS/SEC observations"):
                oracle.compare_observations(changed, actual)
            wrong_type = copy.deepcopy(actual)
            wrong_type["cases"]["FS-001"]["outcomes"]["valid/file"]["ok"] = 1
            with self.assertRaisesRegex(oracle.OracleError, "complete normalized Go FS/SEC observations"):
                oracle.compare_observations(payload, wrong_type)
            wrong_target = copy.deepcopy(actual)
            wrong_target["native_target"] = "linux-aarch64"
            with self.assertRaisesRegex(oracle.OracleError, "native identities differ"):
                oracle.compare_observations(payload, wrong_target)

    def test_named_test_guard_requires_one_named_pass_and_exact_failure_reason(self):
        name = "fs001_strict_v1_replays_go_controls"
        passing = subprocess.CompletedProcess([], 0, f"test {name} ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 5 filtered out;\n".encode(), b"")
        oracle._assert_named_test_result(passing, passed=True)
        zero_match = subprocess.CompletedProcess([], 0, b"test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;\n", b"")
        with self.assertRaisesRegex(oracle.OracleError, "explicitly pass"):
            oracle._assert_named_test_result(zero_match, passed=True)
        wrong_name = subprocess.CompletedProcess([], 1, b"test another_test ... FAILED\ntest result: FAILED. 0 passed; 1 failed; 0 ignored;\n", b"Go must actually accept the versioned control case")
        with self.assertRaisesRegex(oracle.OracleError, "named test"):
            oracle._assert_named_test_result(wrong_name, passed=False, exact_reason="Go must actually accept the versioned control case")
        failed = subprocess.CompletedProcess([], 1, f"test {name} ... FAILED\ntest result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; 5 filtered out;\n".encode(), b"Go must actually accept the versioned control case")
        oracle._assert_named_test_result(failed, passed=False, exact_reason="Go must actually accept the versioned control case")
        compile_failure = subprocess.CompletedProcess([], 1, b"error: could not compile\n", b"")
        with self.assertRaisesRegex(oracle.OracleError, "named test"):
            oracle._assert_named_test_result(compile_failure, passed=False, exact_reason="compile")

    def test_cargo_metadata_guard_binds_workspace_package_target_and_source(self):
        root = Path("/candidate").resolve()
        target = Path("/candidate/private-target").resolve()
        metadata = {
            "workspace_root": str(root),
            "target_directory": str(target),
            "packages": [{
                "name": "symaira-core-foundation",
                "manifest_path": str(root / "rust/test-support/symaira-core-foundation/Cargo.toml"),
                "targets": [{
                    "name": "rust-fs-secret", "kind": ["bin"],
                    "src_path": str(root / "rust/test-support/symaira-core-foundation/src/bin/rust_fs_secret.rs"),
                }],
            }],
        }
        oracle._validate_cargo_metadata(json.dumps(metadata).encode(), root, target)
        metadata["workspace_root"] = "/wrong"
        with self.assertRaisesRegex(oracle.OracleError, "outside the candidate"):
            oracle._validate_cargo_metadata(json.dumps(metadata).encode(), root, target)


if __name__ == "__main__":
    unittest.main(verbosity=2)
