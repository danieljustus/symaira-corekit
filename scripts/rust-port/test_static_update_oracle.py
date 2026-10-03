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
        destination = oracle.fixture_path(lane, root=root, target=("darwin", "arm64"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(oracle.fixture_path(lane), destination)
        helper = root / "scripts/rust-port/static_update_oracle.py"
        helper.parent.mkdir(parents=True)
        shutil.copyfile(Path(oracle.__file__), helper)
        shutil.copyfile(Path(oracle.__file__).with_name("static_update_anchors.py"), helper.with_name("static_update_anchors.py"))
        source_index = json.loads(oracle.INDEX_PATH.read_text(encoding="utf-8"))
        key = "darwin/arm64/" + lane
        index = {"schema_version": 2, "captures": {key: source_index["captures"][key]}}
        index_path = root / "testdata/rust-port/fixtures/update/static-v1/index-v2.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        return root, destination, index_path, index

    def test_all_native_captures_have_exact_live_case_inventories(self):
        for lane, expected_count in EXPECTED_COUNTS.items():
            with self.subTest(lane=lane):
                path = oracle.fixture_path(lane)
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
        capture = oracle.validate_capture("swap", oracle.fixture_path("swap"), diagnostic=True)
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
            payload = oracle.validate_capture("version", oracle.fixture_path("version"), diagnostic=True)
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
        path = oracle.fixture_path("response")
        self.assertEqual(len(oracle.validate_capture("response", path, diagnostic=True)["cases"]), 9)
        with self.assertRaisesRegex(ValueError, "dirty capture is diagnostic only"):
            oracle.validate_capture("response", path)

    def test_synthetic_registration_preserves_two_native_target_entries(self):
        # Synthetic platform records test index mechanics only. Review anchors
        # are explicitly stubbed; neither row is genuine native acceptance.
        root = Path(self.temporary.name) / "registration"
        candidates, anchors = [], {}
        for target in (("darwin", "arm64"), ("linux", "amd64")):
            payload = json.loads(oracle.fixture_path("response").read_bytes())
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
        index = json.loads((root / "testdata/rust-port/fixtures/update/static-v1/index-v2.json").read_bytes())
        self.assertEqual(set(index["captures"]), set(anchors))
        for target, _candidate, raw in candidates:
            key = "/".join((*target, "response"))
            self.assertEqual(index["captures"][key]["sha256"], oracle.sha256(raw))
            self.assertEqual(oracle.fixture_path("response", root=root, target=target).read_bytes(), raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
