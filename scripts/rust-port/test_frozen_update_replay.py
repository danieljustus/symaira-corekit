"""Mutate actual native recordings and prove rejection before Rust execution."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import frozen_update_replay as replay


class FrozenUpdateTests(unittest.TestCase):
    def _copy_replay_inputs(self, root, lane):
        target = "-".join(replay.native_goos_arch())
        source_fixture = replay.FIXTURES / target
        fixture_root = root / "testdata/rust-port/fixtures/update/native-v1"
        fixture_dir = fixture_root / target
        fixture_dir.mkdir(parents=True)
        for suffix in ("json", "stdout", "stderr"):
            shutil.copyfile(source_fixture / f"{lane}.{suffix}", fixture_dir / f"{lane}.{suffix}")
        payload = json.loads((fixture_dir / f"{lane}.json").read_bytes())
        repository_paths = {
            item["path"]
            for item in payload["capture"]["source_files"] + [payload["capture"]["producer"]]
            if item["path"].startswith("repository/")
        }
        for name in repository_paths:
            relative = name.removeprefix("repository/")
            source = replay.ROOT / relative
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        receipt = root / "docs/rust-port/evidence/update-module-compat-v1.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(replay.ROOT / "docs/rust-port/evidence/update-module-compat-v1.json", receipt)
        return fixture_dir

    def test_all_original_native_inventories_remain_fixed(self):
        historical_modules, _ = replay._module_compatibility_inputs()
        fixture_root = replay.ROOT / "testdata/rust-port/fixtures/update/native-v1"
        for target, lanes in replay.ANCHORS.items():
            goos, goarch = target.split("-", 1)
            for lane, expected in lanes.items():
                with self.subTest(target=target, lane=lane):
                    path = fixture_root / target / f"{lane}.json"
                    raw = path.read_bytes()
                    self.assertEqual(replay.digest(raw), expected)
                    payload = json.loads(raw)
                    record = payload["capture"]
                    self.assertEqual(record["source_commit"], replay.CAPTURE_SOURCE_COMMIT)
                    self.assertIs(record["working_tree_clean"], True)
                    self.assertEqual(record["dirty_paths"], [])
                    self.assertEqual(record["capture_mode"], "native-go-update-original-v1")
                    self.assertEqual((record["go"]["goos"], record["go"]["goarch"]), (goos, goarch))
                    self.assertEqual(record["go"]["goversion"], "go1.26.6")
                    for stream in ("stdout", "stderr"):
                        stream_path = path.with_name(f"{lane}.{stream}")
                        self.assertEqual(replay.digest(stream_path.read_bytes()), record["raw"][stream + "_sha256"])
                    source_files = record["source_files"]
                    self.assertFalse(any(item["path"].startswith("modules/") for item in source_files))
                    module_pair = {
                        item["path"]: item["sha256"]
                        for item in source_files
                        if item["path"] in replay.MODULE_INPUT_PATHS
                    }
                    self.assertEqual(module_pair, historical_modules)
                    cases = payload["observations"]
                    cases = cases if isinstance(cases, list) else cases["cases"]
                    case_ids = [case["input"]["id"] if lane == "apply" else case["id"] for case in cases]
                    self.assertEqual(len(cases), replay.COUNTS[lane])
                    self.assertEqual(record["case_count"], replay.COUNTS[lane])
                    self.assertEqual(record["case_ids"], case_ids)
                    self.assertEqual(
                        record["case_fingerprints_sha256"],
                        [replay.digest(replay.canonical_json(case)) for case in cases],
                    )
                    for item in source_files + [record["producer"]]:
                        name = item["path"]
                        if name.startswith("repository/") and name not in replay.MODULE_INPUT_PATHS:
                            source = replay.ROOT / name.removeprefix("repository/")
                            self.assertTrue(source.is_file(), name)
                            self.assertEqual(replay.digest(source.read_bytes()), item["sha256"], name)

    def test_actual_read_capture_accepts_only_exact_module_pair_and_bound_inputs(self):
        lane = "request"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            fixture_dir = self._copy_replay_inputs(root, lane)
            fixture_root = root / "testdata/rust-port/fixtures/update/native-v1"
            with mock.patch.object(replay, "ROOT", root), mock.patch.object(replay, "FIXTURES", fixture_root):
                original_raw = (replay.FIXTURES / "-".join(replay.native_goos_arch()) / f"{lane}.json").read_bytes()
                accepted_raw, _ = replay.read_capture(lane)
                self.assertEqual(accepted_raw, original_raw)

                go_mod = root / "go.mod"
                approved_manifest = go_mod.read_bytes()
                go_mod.write_bytes(approved_manifest + b"\n")
                with self.assertRaisesRegex(ValueError, "approved frozen-update compatibility pair"):
                    replay.read_capture(lane)
                go_mod.write_bytes(approved_manifest)

                relevant_source = root / "updatecheck/updatecheck.go"
                source_bytes = relevant_source.read_bytes()
                relevant_source.write_bytes(source_bytes + b"\n")
                with self.assertRaisesRegex(ValueError, "repository input changed"):
                    replay.read_capture(lane)
                relevant_source.write_bytes(source_bytes)

                fixture = fixture_dir / f"{lane}.json"
                fixture.write_bytes(original_raw + b" ")
                with self.assertRaisesRegex(ValueError, "fixed reviewed bytes"):
                    replay.read_capture(lane)

    def test_actual_read_capture_rejects_external_module_closure(self):
        lane = "request"
        target = "-".join(replay.native_goos_arch())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            fixture_dir = self._copy_replay_inputs(root, lane)
            fixture = fixture_dir / f"{lane}.json"
            payload = json.loads(fixture.read_bytes())
            payload["capture"]["source_files"].append(
                {"path": "modules/golang.org/x/net@v0.60.0/net.go", "sha256": "0" * 64}
            )
            mutated_raw = json.dumps(payload).encode("utf-8")
            fixture.write_bytes(mutated_raw)
            test_anchors = copy.deepcopy(replay.ANCHORS)
            test_anchors[target][lane] = replay.digest(mutated_raw)
            fixture_root = root / "testdata/rust-port/fixtures/update/native-v1"
            # The test-only digest lets the real read_capture reach the closure
            # check; production anchors and original captures remain untouched.
            with (
                mock.patch.object(replay, "ROOT", root),
                mock.patch.object(replay, "FIXTURES", fixture_root),
                mock.patch.object(replay, "ANCHORS", test_anchors),
            ):
                with self.assertRaisesRegex(ValueError, "external Go module inputs"):
                    replay.read_capture(lane)

    def test_every_original_family_rejects_changed_bytes_and_restores(self):
        for lane in replay.COUNTS:
            with self.subTest(lane=lane):
                raw, observations = replay.read_capture(lane)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "recording.json"
                    path.write_bytes(raw)
                    self.assertEqual(replay.read_capture(lane, path)[0], raw)
                    mutated = json.loads(raw)
                    value = mutated["observations"]
                    cases = value if isinstance(value, list) else value["cases"]
                    row = cases[0]["input"] if lane == "apply" else cases[0]
                    row["id"] += "-mutated"
                    path.write_text(json.dumps(mutated), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "fixed reviewed bytes"):
                        replay.read_capture(lane, path)
                    path.write_bytes(raw.replace(b"\n", b"\r\n"))
                    with self.assertRaisesRegex(ValueError, "fixed reviewed bytes"):
                        replay.read_capture(lane, path)
                    path.write_bytes(raw)
                    self.assertEqual(replay.read_capture(lane, path)[1], observations)

    def test_original_raw_stream_drift_is_rejected_and_restored(self):
        target = "-".join(replay.native_goos_arch())
        for lane in replay.COUNTS:
            with self.subTest(lane=lane):
                path = replay.FIXTURES / target / f"{lane}.stdout"
                raw = path.read_bytes()
                try:
                    path.write_bytes(raw + b" ")
                    with self.assertRaisesRegex(ValueError, "raw stream changed"):
                        replay.read_capture(lane)
                finally:
                    path.write_bytes(raw)
                replay.read_capture(lane)


if __name__ == "__main__":
    unittest.main()
