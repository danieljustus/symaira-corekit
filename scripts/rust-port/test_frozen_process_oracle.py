"""Exercise real frozen captures, actual Rust replay and fail-closed controls."""
from __future__ import annotations

import argparse
import base64
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import unittest
from unittest.mock import patch

import frozen_process_oracle as frozen
from frozen_process_anchors import ANCHORS

HERE = Path(__file__).resolve().parent


def runner(name):
    path = HERE / f"{name}-differential.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FrozenProcessOracleTests(unittest.TestCase):
    def captures(self):
        for name in ("mcp", "mcpcfg"):
            module = runner(name)
            cases = json.loads(module.CASES.read_bytes())["cases"]
            payloads = [module.case_stdin(case) if name == "mcp" else
                        json.dumps(case, separators=(",", ":"), ensure_ascii=False).encode()
                        for case in cases]
            path = module.CASES.parent / "fixtures" / f"{name}-differential-{frozen.native_os()}.json"
            yield module, cases, payloads, path

    def load(self, module, cases, payloads, path, digest):
        source = HERE / f"{module.__name__}-differential.py"
        return frozen.load_capture(path, digest, source, module.HELPER,
                                   module.CASES, module.ORACLE_COMMIT, cases, payloads)

    def test_default_replays_every_real_rust_case_without_go_or_git(self):
        for module, cases, _, _ in self.captures():
            with self.subTest(module=module.__name__), patch.dict(os.environ, {"GO_ORACLE": "0"}), \
                    patch.object(sys, "argv", [module.__file__, "--check"]), \
                    patch.object(frozen, "capture", side_effect=AssertionError("Go capture called")), \
                    patch.object(module, "build_go_oracle", side_effect=AssertionError("Go build called")), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(module.main(), 0)
                self.assertEqual(sum(line.startswith("PASS ") and line[5:].startswith(("MCP-", "MCFG-"))
                                     for line in output.getvalue().splitlines()), len(cases))
                self.assertIn("PASS negative control", output.getvalue())

    def test_corrupted_capture_is_rejected_before_comparison(self):
        for module, cases, payloads, source in self.captures():
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as raw:
                document = json.loads(source.read_bytes())
                document["cases"][0]["stdout_base64"] = base64.b64encode(b"CORRUPTED-TEST-OUTPUT").decode()
                path = Path(raw) / "mutated.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                digest = ANCHORS[f"{module.__name__}-differential:{frozen.native_os()}"]
                with self.assertRaisesRegex(ValueError, "capture integrity mismatch"):
                    self.load(module, cases, payloads, path, digest)

    def test_schema_case_identity_input_and_provenance_fail_closed(self):
        for module, cases, payloads, source in self.captures():
            mutations = [
                (lambda d: d.update(case_count=0), "schema/count"),
                (lambda d: d["cases"].pop(), "identity/order"),
                (lambda d: d["cases"][0].update(id="UNKNOWN-TEST-CASE"), "identity/order"),
                (lambda d: d["cases"][0].update(stdin_sha256="0" * 64), "input/exit"),
                (lambda d: d["cases"][0].update(exit_code=True), "input/exit"),
                (lambda d: d["provenance"].update(oracle_commit="0" * 40), "provenance"),
            ]
            for mutate, message in mutations:
                with self.subTest(module=module.__name__, control=message), tempfile.TemporaryDirectory() as raw:
                    document = copy.deepcopy(json.loads(source.read_bytes()))
                    mutate(document)
                    path = Path(raw) / "malformed-test-capture.json"
                    path.write_text(json.dumps(document), encoding="utf-8")
                    # Deliberately pass the test document's hash to exercise the
                    # inner schema controls separately from the outer trust pin.
                    with self.assertRaisesRegex(ValueError, message):
                        self.load(module, cases, payloads, path, frozen.sha256(path.read_bytes()))

    def test_go_helper_absence_does_not_change_frozen_replay(self):
        for module, cases, payloads, path in self.captures():
            with self.subTest(module=module.__name__):
                digest = ANCHORS[f"{module.__name__}-differential:{frozen.native_os()}"]
                source = HERE / f"{module.__name__}-differential.py"
                observed = frozen.load_capture(path, digest, source, HERE / "absent.go",
                                               module.CASES, module.ORACLE_COMMIT, cases, payloads)
                self.assertEqual(len(observed), len(cases))

    def test_capture_requires_explicit_opt_in(self):
        module = runner("mcp")
        args = argparse.Namespace(capture=Path("never-created-test-output.json"))
        with patch.dict(os.environ, {"GO_ORACLE": "0"}), \
                patch.object(frozen, "capture", side_effect=AssertionError("Go capture called")):
            with self.assertRaisesRegex(ValueError, "requires GO_ORACLE=1"):
                frozen.check(HERE / "mcp-differential.py", module.HELPER, module.CASES, module.ORACLE_COMMIT,
                             [], [], None, None, None, args)

    def test_same_process_panic_exchange_is_repeatable_and_timeout_reaps_child(self):
        module = runner("mcp")
        cases = json.loads(module.CASES.read_bytes())["cases"]
        case = next(case for case in cases if case["id"] == "MCP-011")
        binary = module.REPO / "target" / "debug" / (module.RUST_BIN + (".exe" if os.name == "nt" else ""))
        for _ in range(30):
            code, stdout, _ = module.run(binary, module.case_stdin(case), case)
            self.assertEqual(code, 0)
            self.assertEqual([json.loads(line)["id"] for line in stdout.splitlines()], [9, 10, 11])
        real_popen = frozen.subprocess.Popen
        owned = []
        def launch(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            owned.append(process)
            return process
        notification = module.case_stdin({"mode": "line", "request": {
            "jsonrpc": "2.0", "method": "notifications/initialized"}})
        with patch.object(frozen.subprocess, "Popen", side_effect=launch):
            with self.assertRaises(queue.Empty):
                frozen.serial_line_exchange(binary, notification, dict(os.environ), timeout=1)
        self.assertEqual(len(owned), 1)
        self.assertIsNotNone(owned[0].poll())


if __name__ == "__main__":
    unittest.main()
