"""Regression controls for the real SQLite capture validator and runner."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

SPEC = importlib.util.spec_from_file_location("sqlite_capture", Path(__file__).with_name("generate.py"))
assert SPEC is not None and SPEC.loader is not None
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads(generator.OUT.read_bytes())

    def rejected(self, mutation):
        candidate = copy.deepcopy(self.report)
        mutation(candidate)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            generator.compare(self.report, candidate)

    def test_unchanged_capture_is_accepted(self):
        generator.compare(self.report, copy.deepcopy(self.report))

    def test_wrong_journal_mode_is_rejected(self):
        self.rejected(lambda r: r["cases"][1]["state"]["connections"][0].update(journal_mode="delete"))

    def test_wrong_timeout_is_rejected(self):
        self.rejected(lambda r: r["cases"][1]["state"]["connections"][1].update(busy_timeout=0))

    def test_missing_case_is_rejected(self):
        self.rejected(lambda r: r["cases"].pop())

    def test_failed_rollback_is_rejected(self):
        self.rejected(lambda r: r["cases"][4]["negative"][0].update(rolled_back=False))

    def test_wrong_error_is_rejected(self):
        self.rejected(lambda r: r["cases"][4]["negative"][1].update(error="other error: wrong cause"))

    def test_changed_error_cause_is_rejected(self):
        self.rejected(lambda r: r["cases"][4]["negative"][1].update(error="failed to record migration 001_test: altered cause"))

    def test_missing_contention_is_rejected(self):
        self.rejected(lambda r: r["cases"][1]["state"]["contention"].update(observed=False))

    def test_schema_change_is_rejected(self):
        self.rejected(lambda r: r["cases"][2]["state"]["schema"][0].update(sql="CREATE INDEX wrong ON test_items(id)"))

    def test_wrong_toolchain_is_rejected(self):
        self.rejected(lambda r: r["oracle"].update(go_version="go1.27.1"))

    def test_changed_source_hash_is_rejected(self):
        self.rejected(lambda r: r["oracle"]["source_hashes"].update({"sqlitekit/sqlitekit.go": "0" * 64}))

    def test_changed_helper_hash_is_rejected(self):
        self.rejected(lambda r: r["oracle"]["artifact_hashes"].update({"scripts/rust-port/sqlite/main.go": "0" * 64}))

    def test_changed_dependency_identity_is_rejected(self):
        self.rejected(lambda r: r["oracle"].update(dependencies={"modernc.org/sqlite": {"Version": "v0.0.0"}}))

    def test_invalid_application_time_is_rejected(self):
        self.rejected(lambda r: r["cases"][2]["state"]["applied_at"].__setitem__(0, "0001-01-01T00:00:00Z"))

    def test_changed_idempotence_is_rejected(self):
        self.rejected(lambda r: r["cases"][3]["state"].update(applied_at_unchanged=False))

    def test_adjacent_large_integer_is_rejected(self):
        self.rejected(lambda r: r["cases"][2]["state"].update(large_integer=9007199254740992))

    def test_pinned_compiler_uses_windows_executable_name(self):
        compiler = Path("C:/hostedtoolcache/windows/go/1.26.6/x64/bin")
        self.assertEqual(generator.compiler_executable(compiler, "nt").name, "go.exe")
        self.assertEqual(generator.compiler_executable(compiler, "posix").name, "go")


class ProcessTests(unittest.TestCase):
    def test_nonzero_exit_is_not_hidden(self):
        with self.assertRaisesRegex(RuntimeError, "command failed \\(7\\)"):
            generator.run([sys.executable, "-c", "raise SystemExit(7)"], cwd=generator.ROOT)

    @unittest.skipIf(os.name == "nt", "POSIX group test; native Windows taskkill proof remains open")
    def test_timeout_reaps_parent_and_descendant(self):
        with tempfile.TemporaryDirectory() as name:
            pidfile = Path(name) / "child.pid"
            code = ("import subprocess,sys,time; from pathlib import Path; "
                    "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                    "Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(60)")
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                generator.run([sys.executable, "-c", code, str(pidfile)],
                              cwd=generator.ROOT, timeout=1)
            self.assertLess(time.monotonic() - started, 5)
            pid = int(pidfile.read_text())
            state = subprocess.run(["ps", "-p", str(pid), "-o", "stat="],
                                   capture_output=True, text=True, timeout=3).stdout.strip()
            self.assertTrue(not state or state.startswith("Z"), state)

    @unittest.skipIf(os.name == "nt", "Unix umask contract only")
    def test_runner_does_not_modify_parent_umask(self):
        previous = os.umask(0o022)
        try:
            generator.run([sys.executable, "-c", "pass"], cwd=generator.ROOT)
            actual = os.umask(0o022)
            self.assertEqual(actual, 0o022)
        finally:
            os.umask(previous)


if __name__ == "__main__":
    unittest.main()
