#!/usr/bin/env python3
"""Executable integrity and native-slice controls for frozen update observations."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import static_update_oracle as oracle

EXPECTED_COUNTS = {
    "version": 30,
    "response": 9,
    "install-method": 15,
    "extract": 12,
    "swap": 8,
    "checker": 21,
}


class StaticUpdateOracleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="static-update-provenance-test-")
        self.addCleanup(self.temporary.cleanup)
        # Structural tests inspect actual retained Darwin evidence, not native
        # Linux/Windows acceptance. No cross-platform oracle claim is made here.
        self.native = mock.patch.object(oracle, "native_goos_arch", return_value=("darwin", "arm64"))
        self.native.start()
        self.addCleanup(self.native.stop)

    def _temporary_capture(self, lane: str):
        root = Path(self.temporary.name) / lane
        destination = oracle.fixture_path(lane, root=root, target=("darwin", "arm64"), historical=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(oracle.fixture_path(lane, historical=True), destination)
        helper = root / "scripts/rust-port/static_update_oracle.py"
        helper.parent.mkdir(parents=True)
        shutil.copyfile(Path(oracle.__file__), helper)
        shutil.copyfile(Path(oracle.__file__).with_name("static_update_anchors.py"), helper.with_name("static_update_anchors.py"))
        shutil.copyfile(Path(oracle.__file__).with_name("bounded_oracle_process.py"), helper.with_name("bounded_oracle_process.py"))
        source_index = json.loads((oracle.HISTORICAL_ROOT / "index-v2.json").read_bytes())
        key = "darwin/arm64/" + lane
        index = {"schema_version": 2, "captures": {key: source_index["captures"][key]}}
        index_path = root / "testdata/rust-port/fixtures/update/static-v1/index-v2.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        return root, destination, index_path, index

    def test_all_native_captures_have_exact_live_case_inventories(self):
        for lane, expected_count in EXPECTED_COUNTS.items():
            with self.subTest(lane=lane):
                path = oracle.fixture_path(lane, historical=True)
                payload = oracle.validate_capture(lane, path, diagnostic=True)
                capture = payload["capture"]
                self.assertEqual(capture["case_count"], expected_count)
                self.assertEqual(len(capture["case_ids"]), expected_count)
                self.assertEqual(len(set(capture["case_ids"])), expected_count)
                self.assertEqual(capture["go"]["version"], "go version go1.26.6 darwin/arm64")
                self.assertEqual((capture["go"]["goos"], capture["go"]["goarch"]), ("darwin", "arm64"))
                self.assertRegex(capture["source_commit"], r"^[0-9a-f]{40}$")
                self.assertIs(capture["working_tree_clean"], False)
                self.assertTrue(capture["dirty_paths"])
                self.assertEqual(capture["capture_mode"], "fresh-pinned-go-execution-additive-v1")
                cases = oracle._at_path(payload, oracle.LANES[lane]["case_path"])
                fingerprints = [oracle.sha256(oracle.canonical_json(case)) for case in cases]
                self.assertEqual(capture["case_fingerprints_sha256"], fingerprints)
                legacy = oracle.ROOT / capture["historical_fixture"]["path"]
                self.assertEqual(oracle.sha256(legacy.read_bytes()), capture["historical_fixture"]["sha256"])

    def test_swap_inventory_matches_go_declared_and_historical_eight_ids(self):
        expected_ids = [
            "missing-source",
            "validation-rollback",
            "validation-first-install",
            "preexisting-backup",
            "validation-rollback-failed",
            "validation-remove-failed",
            "validation-remove-failed-existing",
            "backup-cleanup-failed",
        ]
        capture = oracle.validate_capture("swap", oracle.fixture_path("swap", historical=True), diagnostic=True)
        captured_ids = oracle.case_ids("swap", capture)
        legacy_path = oracle.ROOT / capture["capture"]["historical_fixture"]["path"]
        legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
        legacy_ids = [case["input"]["id"] for case in legacy["cases"]]
        go_source = (oracle.ROOT / "updatecheck/updateapply/atomic_swap_oracle_test.go").read_text(encoding="utf-8")
        go_declared_ids = [line.split('ID: "', 1)[1].split('"', 1)[0] for line in go_source.splitlines() if 'ID: "' in line]
        self.assertEqual(captured_ids, expected_ids)
        self.assertEqual(legacy_ids, expected_ids)
        self.assertEqual(go_declared_ids, expected_ids)
        self.assertEqual(capture["capture"]["case_ids"], expected_ids)
        self.assertEqual(oracle.sha256(legacy_path.read_bytes()), capture["capture"]["historical_fixture"]["sha256"])

    def test_static_validation_does_not_spawn_go_or_other_subprocesses(self):
        with mock.patch.object(oracle.subprocess, "run", side_effect=AssertionError("unexpected subprocess")):
            payload = oracle.validate_capture("version", oracle.fixture_path("version", historical=True), diagnostic=True)
        self.assertEqual(len(payload["cases"]), EXPECTED_COUNTS["version"])

    def test_changed_capture_bytes_fail_against_separate_index(self):
        root, path, _index_path, _index = self._temporary_capture("response")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["cases"][0]["result"] = {"code": "mutated"}
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "capture digest mismatch"):
            oracle.validate_capture("response", path, root=root)

    def test_native_platform_index_mutation_is_rejected(self):
        root, path, index_path, index = self._temporary_capture("install-method")
        index["captures"]["darwin/arm64/install-method"]["goos"] = "windows"
        index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "native platform identity mismatch"):
            oracle.validate_capture("install-method", path, root=root)

    def test_case_id_mutation_is_rejected_even_with_refreshed_file_digest(self):
        root, path, index_path, index = self._temporary_capture("checker")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["capture"]["case_ids"][1] = payload["capture"]["case_ids"][0]
        raw = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        path.write_bytes(raw)
        index["captures"]["darwin/arm64/checker"]["sha256"] = hashlib.sha256(raw).hexdigest()
        index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "capture case IDs mismatch"):
            oracle.validate_capture("checker", path, root=root)

    def test_absent_native_slice_fails_closed_without_platform_fallback(self):
        root = Path(self.temporary.name) / "linux-root"
        linux_path = oracle.fixture_path("version", root=root, target=("linux", "amd64"))
        with self.assertRaisesRegex(ValueError, "missing native version Go capture"):
            oracle.validate_capture("version", linux_path, root=root)

    @unittest.skipUnless(oracle.native_goos_arch() == ("darwin", "arm64"), "real CLI controls require the retained native Darwin capture; other native captures remain open")
    def test_actual_cli_rejects_coordinated_capture_index_replacement(self):
        root, path, index_path, index = self._temporary_capture("response")
        command = [sys.executable, str(root / "scripts/rust-port/static_update_oracle.py"), "check", "--lane", "response", "--fixture", str(path), "--diagnostic"]
        result = subprocess.run(command, cwd=root, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(path.read_bytes())
        payload["cases"][0]["result"] = {"code": "changed-expected-result"}
        payload["capture"]["case_fingerprints_sha256"] = oracle._case_fingerprints("response", payload)
        raw = oracle._json_bytes(payload)
        path.write_bytes(raw)
        index["captures"]["darwin/arm64/response"]["sha256"] = oracle.sha256(raw)
        index_path.write_bytes(oracle._json_bytes(index))
        result = subprocess.run(command, cwd=root, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"independently reviewed capture anchor mismatch", result.stderr)
        self.assertEqual(path.read_bytes(), raw)

    @unittest.skipUnless(oracle.native_goos_arch() == ("darwin", "arm64"), "real CLI controls require the retained native Darwin capture; other native captures remain open")
    def test_actual_cli_rejects_missing_null_and_wrong_type_provenance(self):
        root, path, index_path, index = self._temporary_capture("response")
        original = path.read_bytes()
        command = [sys.executable, str(root / "scripts/rust-port/static_update_oracle.py"), "check", "--lane", "response", "--fixture", str(path), "--diagnostic"]
        self.assertEqual(subprocess.run(command, cwd=root, capture_output=True, timeout=10).returncode, 0)
        mutations = [
            ("source_commit", None, True, b"invalid required provenance field"),
            ("source_files", None, True, b"missing required provenance inventory"),
            ("case_fingerprints_sha256", None, True, b"fingerprint inventory mismatch"),
            ("working_tree_clean", None, False, b"working_tree_clean must be boolean"),
            ("schema_version", True, False, b"lacks versioned provenance"),
            ("raw.exit_code", False, False, b"failed Go execution"),
        ]
        for field, value, remove, message in mutations:
            with self.subTest(field=field):
                payload = json.loads(original)
                target = payload["capture"]["raw"] if field == "raw.exit_code" else payload["capture"]
                name = field.split(".")[-1]
                if remove:
                    del target[name]
                else:
                    target[name] = value
                raw = oracle._json_bytes(payload)
                path.write_bytes(raw)
                index["captures"]["darwin/arm64/response"]["sha256"] = oracle.sha256(raw)
                index_path.write_bytes(oracle._json_bytes(index))
                result = subprocess.run(command, cwd=root, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_dirty_history_cannot_grant_acceptance(self):
        path = oracle.fixture_path("response", historical=True)
        self.assertEqual(len(oracle.validate_capture("response", path, diagnostic=True)["cases"]), 9)
        with self.assertRaisesRegex(ValueError, "dirty capture is diagnostic only"):
            oracle.validate_capture("response", path)

    def test_acceptance_generation_cannot_replace_or_fall_back_to_history(self):
        current = oracle.fixture_path("response")
        history = oracle.fixture_path("response", historical=True)
        self.assertNotEqual(current, history)
        self.assertIn("static-v2", current.parts)
        self.assertIn("static-v1", history.parts)
        before = history.read_bytes()
        with self.assertRaisesRegex(ValueError, "missing native response Go capture"):
            oracle.validate_capture("response", oracle.fixture_path("response", root=Path(self.temporary.name)))
        self.assertEqual(history.read_bytes(), before)

    def test_go_discovery_uses_path_or_explicit_launcher_and_requires_sdk_file(self):
        sdk = Path(self.temporary.name) / "SDK with spaces"
        binary = sdk / "bin" / ("go.exe" if oracle.os.name == "nt" else "go")
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"synthetic compiler path control, never executed")
        result = subprocess.CompletedProcess([], 0, (str(sdk) + "\n").encode(), b"")
        for explicit in (None, "/explicit/compiler launcher"):
            with self.subTest(explicit=explicit), mock.patch.dict(oracle.os.environ):
                oracle.os.environ.pop("GO_ORACLE_BIN", None)
                if explicit:
                    oracle.os.environ["GO_ORACLE_BIN"] = explicit
                with mock.patch.object(oracle, "run_checked", return_value=result) as run:
                    self.assertEqual(oracle._resolve_go_tool(), binary.resolve())
                self.assertEqual(run.call_args.args[0], [explicit or "go", "env", "GOROOT"])
                self.assertEqual(run.call_args.kwargs["env"]["GOTOOLCHAIN"], "go1.26.6")
                self.assertEqual(run.call_args.kwargs["env"]["GOPROXY"], "off")
        binary.unlink()
        with mock.patch.object(oracle, "run_checked", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "no compiler executable"):
                oracle._resolve_go_tool()

    def test_go_preparation_rejects_wrong_executed_version(self):
        scratch = Path(self.temporary.name)
        results = [
            subprocess.CompletedProcess([], 0, (str(scratch) + "\n").encode(), b""),
            subprocess.CompletedProcess([], 0, b"go version go1.25.0 darwin/arm64\n", b""),
        ]
        with mock.patch.object(oracle, "_resolve_go_tool", return_value=scratch / "go"), mock.patch.object(oracle, "run_checked", side_effect=results):
            with self.assertRaisesRegex(RuntimeError, "expected executed go1.26.6"):
                oracle._prepare_go_env(scratch / "isolated")

    def test_go_preparation_rejects_cross_target_before_capture(self):
        scratch = Path(self.temporary.name)
        results = [
            subprocess.CompletedProcess([], 0, (str(scratch) + "\n").encode(), b""),
            subprocess.CompletedProcess([], 0, b"go version go1.26.6 darwin/arm64\n", b""),
            subprocess.CompletedProcess([], 0, ("go1.26.6\n" + str(scratch) + "\nlinux\namd64\n" + str(scratch) + "\n").encode(), b""),
        ]
        with mock.patch.object(oracle, "_resolve_go_tool", return_value=scratch / "go"), mock.patch.object(oracle, "run_checked", side_effect=results):
            with self.assertRaisesRegex(RuntimeError, "does not match the native capture platform"):
                oracle._prepare_go_env(scratch / "isolated")

    def test_capture_rejects_input_drift_and_keeps_failed_raw_evidence(self):
        # Synthetic subprocess/snapshot controls only. These reports are not Go
        # observations and must never be registered as native capture evidence.
        for failure in ("input-drift", "malformed-observation"):
            with self.subTest(failure=failure):
                root = Path(self.temporary.name) / failure
                root.mkdir()
                before = {"source_commit": "a" * 40, "working_tree_clean": False, "dirty_paths": ["go.mod"],
                          "source_files": [{"path": "repository/go.mod", "sha256": "b" * 64}], "go_binary_sha256": "c" * 64}
                after = json.loads(json.dumps(before))
                if failure == "input-drift":
                    after["source_files"][0]["sha256"] = "d" * 64
                    output = json.dumps(json.loads(oracle.fixture_path("version", historical=True).read_bytes())["cases"]).encode()
                else:
                    output = b"intentionally invalid observation JSON"
                record = {"stage": "synthetic-unit-control", "command": ["synthetic"], "cwd": "unit-only",
                          "exit_code": 0, "stdout": output, "stderr": b""}
                prepared = ({}, "go version go1.26.6 darwin/arm64", str(root), "darwin", "arm64", str(root), root / "fake-go")
                with mock.patch.dict(oracle.os.environ, {"GO_ORACLE": "1"}), mock.patch.object(oracle, "_prepare_go_env", return_value=prepared), mock.patch.object(oracle, "_capture_inputs", side_effect=[before, after]), mock.patch.object(oracle, "_run", return_value=record):
                    with self.assertRaises(ValueError):
                        oracle.capture_go("version", root / "evidence")
                evidence = list((root / "evidence").iterdir())
                self.assertEqual(len(evidence), 1)
                self.assertEqual((evidence[0] / "observation.raw").read_bytes(), output)
                report = json.loads((evidence[0] / "run.json").read_bytes())
                self.assertIs(report["success"], False)
                self.assertEqual(report["input_snapshot"], before)

    def _registration_candidate(self, name, target=("darwin", "arm64")):
        """Synthetic registration input only; callers explicitly stub its anchor."""
        root = Path(self.temporary.name) / name
        root.mkdir(parents=True, exist_ok=True)
        payload = json.loads(oracle.fixture_path("response", historical=True).read_bytes())
        capture = payload["capture"]
        capture["capturer_sha256"] = oracle.sha256(Path(oracle.__file__).read_bytes())
        capture["go"].update(goos=target[0], goarch=target[1], version="go version go1.26.6 " + "/".join(target))
        candidate = root / ("candidate-" + "-".join(target) + ".json")
        candidate.write_bytes(oracle._json_bytes(payload))
        return root, candidate, oracle.fixture_path("response", root=root, target=target), "/".join((*target, "response"))

    def test_registration_rejects_malformed_candidates_before_any_write(self):
        mutations = [
            ("schema_version", None, True),
            ("schema_version", None, False),
            ("schema_version", True, False),
            ("source_files", None, False),
            ("working_tree_clean", None, False),
            ("raw.exit_code", False, False),
            ("case_count", True, False),
        ]
        for i, (field, value, remove) in enumerate(mutations):
            with self.subTest(field=field, value=value, remove=remove):
                root, candidate, destination, key = self._registration_candidate(f"schema-{i}")
                payload = json.loads(candidate.read_bytes())
                target = payload["capture"]["raw"] if field == "raw.exit_code" else payload["capture"]
                name = field.split(".")[-1]
                if remove:
                    del target[name]
                else:
                    target[name] = value
                candidate.write_bytes(oracle._json_bytes(payload))
                anchors = {key: oracle.sha256(candidate.read_bytes())}
                with mock.patch.dict(oracle.os.environ, {"GO_ORACLE": "1"}), mock.patch.object(oracle, "ANCHORS", anchors):
                    with self.assertRaises(ValueError):
                        oracle.register_capture(candidate, destination, root=root)
                self.assertFalse(destination.exists())
                self.assertFalse((root / "testdata/rust-port/fixtures/update/static-v2/index-v2.json").exists())

    def test_registration_index_failure_rolls_back_owned_capture_and_allows_retry(self):
        root, first, first_destination, first_key = self._registration_candidate("rollback")
        _, second, second_destination, second_key = self._registration_candidate("rollback", ("linux", "amd64"))
        anchors = {first_key: oracle.sha256(first.read_bytes()), second_key: oracle.sha256(second.read_bytes())}
        index_path = first_destination.parents[1] / "index-v2.json"
        with mock.patch.dict(oracle.os.environ, {"GO_ORACLE": "1"}), mock.patch.object(oracle, "ANCHORS", anchors):
            oracle.register_capture(first, first_destination, root=root)
            original_index = index_path.read_bytes()
            original_capture = first_destination.read_bytes()
            with mock.patch.object(oracle.os, "replace", side_effect=PermissionError("injected index publication failure")):
                with self.assertRaisesRegex(PermissionError, "injected"):
                    oracle.register_capture(second, second_destination, root=root)
            self.assertFalse(second_destination.exists())
            self.assertEqual(index_path.read_bytes(), original_index)
            self.assertEqual(first_destination.read_bytes(), original_capture)
            self.assertEqual(list(index_path.parent.glob(".register-*")), [])
            oracle.register_capture(second, second_destination, root=root)
            self.assertEqual(second_destination.read_bytes(), second.read_bytes())
            self.assertEqual(set(json.loads(index_path.read_bytes())["captures"]), set(anchors))

    def test_registration_staging_failure_does_not_publish_capture(self):
        root, candidate, destination, key = self._registration_candidate("stage-failure")
        anchors = {key: oracle.sha256(candidate.read_bytes())}
        original = Path.write_bytes

        def fail_index(path, data):
            if path.name == "index.json" and path.parent.name.startswith(".register-"):
                raise OSError("injected staging failure")
            return original(path, data)

        with mock.patch.dict(oracle.os.environ, {"GO_ORACLE": "1"}), mock.patch.object(oracle, "ANCHORS", anchors), mock.patch.object(Path, "write_bytes", autospec=True, side_effect=fail_index):
            with self.assertRaisesRegex(OSError, "injected staging failure"):
                oracle.register_capture(candidate, destination, root=root)
        self.assertFalse(destination.exists())
        self.assertFalse((destination.parents[1] / "index-v2.json").exists())
        self.assertEqual(list(destination.parents[1].glob(".register-*")), [])

    def test_registration_failure_never_removes_a_foreign_destination(self):
        for phase in ("before-link", "before-index"):
            with self.subTest(phase=phase):
                root, candidate, destination, key = self._registration_candidate(phase)
                anchors = {key: oracle.sha256(candidate.read_bytes())}
                original_link = oracle.os.link

                def racing_link(source, target):
                    destination.write_bytes(b"foreign collision sentinel")
                    return original_link(source, target)

                def racing_replace(source, target):
                    destination.unlink()
                    destination.write_bytes(b"foreign collision sentinel")
                    raise PermissionError("injected replacement race")

                method = "link" if phase == "before-link" else "replace"
                side_effect = racing_link if phase == "before-link" else racing_replace
                with mock.patch.dict(oracle.os.environ, {"GO_ORACLE": "1"}), mock.patch.object(oracle, "ANCHORS", anchors), mock.patch.object(oracle.os, method, side_effect=side_effect):
                    with self.assertRaises(OSError):
                        oracle.register_capture(candidate, destination, root=root)
                self.assertEqual(destination.read_bytes(), b"foreign collision sentinel")
                self.assertFalse((destination.parents[1] / "index-v2.json").exists())
                self.assertEqual(list(destination.parents[1].glob(".register-*")), [])

    def test_synthetic_registration_preserves_two_native_target_entries(self):
        # Synthetic platform records test index mechanics only. Review anchors
        # are explicitly stubbed; neither row is genuine native acceptance.
        root = Path(self.temporary.name) / "registration"
        candidates, anchors = [], {}
        for target in (("darwin", "arm64"), ("linux", "amd64")):
            payload = json.loads(oracle.fixture_path("response", historical=True).read_bytes())
            capture = payload["capture"]
            capture["capturer_sha256"] = oracle.sha256(Path(oracle.__file__).read_bytes())
            capture["go"].update(goos=target[0], goarch=target[1], version="go version go1.26.6 " + "/".join(target))
            raw = oracle._json_bytes(payload)
            candidate = Path(self.temporary.name) / ("-".join(target) + ".json")
            candidate.write_bytes(raw)
            key = "/".join((*target, "response"))
            anchors[key] = oracle.sha256(raw)
            candidates.append((target, candidate, raw))
        with mock.patch.dict(oracle.os.environ, {"GO_ORACLE": "1"}), mock.patch.object(oracle, "ANCHORS", anchors):
            for target, candidate, raw in candidates:
                destination = oracle.fixture_path("response", root=root, target=target)
                oracle.register_capture(candidate, destination, root=root)
                self.assertEqual(destination.read_bytes(), raw)
        index = json.loads((root / "testdata/rust-port/fixtures/update/static-v2/index-v2.json").read_bytes())
        self.assertEqual(set(index["captures"]), set(anchors))
        for target, _candidate, raw in candidates:
            key = "/".join((*target, "response"))
            self.assertEqual(index["captures"][key]["sha256"], oracle.sha256(raw))
            self.assertEqual(oracle.fixture_path("response", root=root, target=target).read_bytes(), raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
