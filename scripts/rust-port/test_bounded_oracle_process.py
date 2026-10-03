"""Real child-process controls for bounded_oracle_process (no Go/Cargo runs)."""
from __future__ import annotations

import json
import os
import re
import select
import subprocess
import sys
import threading
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bounded_oracle_process as bop


ROOT = Path(__file__).resolve().parent


def _test_env():
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(ROOT),
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
    }
    for key in ("SystemRoot", "WINDIR", "TEMP", "TMP"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def _run(code: str, *, timeout=4.0, limit=2 * 1024 * 1024, merge_stderr=False):
    return bop.run_bounded(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=_test_env(),
        timeout=timeout,
        limit=limit,
        merge_stderr=merge_stderr,
    )


def _reader_threads():
    return [thread.name for thread in threading.enumerate() if thread.name.startswith("bounded-oracle-reader-")]


def _fd_count():
    try:
        return len(os.listdir("/dev/fd"))
    except OSError:
        return None


def _assert_posix_pid_not_live(testcase: unittest.TestCase, pid: int):
    probe = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=2.0,
        check=False,
    )
    state = probe.stdout.decode("ascii", "replace").strip()
    testcase.assertTrue(probe.returncode in (0, 1) and (not state or state[0].upper() == "Z"), f"pid {pid} still live: {state!r}; ps exit {probe.returncode}")


class _CaptureAssertions(unittest.TestCase):
    def assert_clean(self, result):
        self.assertTrue(result["cleanup_verified"], result)
        self.assertEqual(_reader_threads(), [])


class BoundedCaptureTests(_CaptureAssertions):
    def test_exact_limit_preserves_nul_crlf_and_non_utf8_bytes(self):
        stdout = b"\x00A\r\n\xffz"
        stderr = stdout[::-1]
        self.assertEqual(len(stdout), len(stderr))
        code = f"import os; os.write(1, {stdout!r}); os.write(2, {stderr!r})"
        result = _run(code, timeout=3.0, limit=len(stdout))
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["stdout"], stdout)
        self.assertEqual(result["stderr"], stderr)
        self.assertFalse(result["output_exceeded"])
        self.assertFalse(result["timed_out"])
        self.assert_clean(result)

    def test_stdout_overflow_keeps_only_bounded_raw_prefix(self):
        limit = 73
        # Closing the bounded reader can interrupt a pending native pipe write.
        code = "import os\ntry: os.write(1, b'O' * 8192)\nexcept OSError: pass\n"
        result = _run(code, limit=limit)
        self.assertTrue(result["output_exceeded"])
        self.assertLessEqual(len(result["stdout"]), limit)
        self.assertEqual(result["stdout"], b"O" * limit)
        self.assertEqual(result["stderr"], b"")
        self.assert_clean(result)

    def test_stderr_overflow_keeps_only_bounded_raw_prefix(self):
        limit = 67
        result = _run("import os; os.write(2, b'E' * 8192)", limit=limit)
        self.assertTrue(result["output_exceeded"])
        self.assertLessEqual(len(result["stderr"]), limit)
        self.assertEqual(result["stderr"], b"E" * limit)
        self.assertEqual(result["stdout"], b"")
        self.assert_clean(result)

    def test_simultaneous_stdout_stderr_flood_is_bounded(self):
        limit = 8192
        code = r'''
import os, threading
# Both streams emit a readiness byte before either flood can exceed the cap.
os.write(1, b"A")
os.write(2, b"B")
def flood(fd, byte):
    block = byte * 8192
    for _ in range(128):
        os.write(fd, block)
a = threading.Thread(target=flood, args=(1, b"A"))
b = threading.Thread(target=flood, args=(2, b"B"))
a.start(); b.start(); a.join(); b.join()
'''
        result = _run(code, timeout=4.0, limit=limit)
        self.assertTrue(result["output_exceeded"])
        self.assertLessEqual(len(result["stdout"]), limit)
        self.assertLessEqual(len(result["stderr"]), limit)
        self.assertTrue(result["stdout"].startswith(b"A"))
        self.assertTrue(result["stderr"].startswith(b"B"))
        self.assert_clean(result)

    def test_timeout_flag_and_bounded_reaping(self):
        code = "import os,time; os.write(1,b'READY\\n'); time.sleep(30)"
        started = time.monotonic()
        result = _run(code, timeout=0.25, limit=64)
        elapsed = time.monotonic() - started
        self.assertTrue(result["timed_out"])
        self.assertLess(elapsed, 3.0, f"timeout cleanup took {elapsed:.3f}s")
        self.assertIn(b"READY\n", result["stdout"])
        self.assertIsNotNone(result["returncode"])
        self.assert_clean(result)

    def test_merged_stderr_is_one_ordered_child_pipe(self):
        code = "import os; os.write(1,b'A'); os.write(2,b'B'); os.write(1,b'C'); os.write(2,b'D')"
        result = _run(code, limit=4, merge_stderr=True)
        self.assertEqual(result["stdout"], b"ABCD")
        self.assertEqual(result["stderr"], b"")
        self.assertFalse(result["output_exceeded"])
        self.assert_clean(result)

    def test_nonzero_exit_is_returned_without_losing_bytes(self):
        result = _run("import os; os.write(1,bytes([114,97,119,0])); os.write(2,b'diagnostic'); raise SystemExit(7)")
        self.assertEqual(result["returncode"], 7)
        self.assertEqual(result["stdout"], bytes([114, 97, 119, 0]))
        self.assertEqual(result["stderr"], b"diagnostic")
        self.assert_clean(result)

    def test_checked_wrapper_retains_failed_raw_bytes_before_raising(self):
        probes = [
            ("nonzero", "import os; os.write(1,b'failed\\x00\\r\\n'); raise SystemExit(7)", 3.0),
            ("timeout", "import os,time; os.write(1,b'ready'); time.sleep(30)", 0.3),
            ("overflow", "import os; os.write(1,b'X'*(3*1024*1024))", 3.0),
        ]
        for label, code, timeout in probes:
            with self.subTest(label=label), tempfile.TemporaryDirectory(prefix="bounded-failure-evidence-") as directory:
                with self.assertRaises((bop.BoundedProcessError, subprocess.CalledProcessError)):
                    bop.run_checked([sys.executable, "-c", code], cwd=ROOT, env=_test_env(), timeout=timeout, artifact_dir=Path(directory), check=True)
                records = list(Path(directory).iterdir())
                self.assertEqual(len(records), 1)
                metadata = json.loads((records[0] / "result.json").read_bytes())
                self.assertIs(metadata["success"], False)
                self.assertIs(metadata["cleanup_verified"], True)
                output = (records[0] / "stdout.raw").read_bytes()
                if label == "nonzero":
                    self.assertEqual(output, b"failed\x00\r\n")
                    self.assertEqual(metadata["returncode"], 7)
                elif label == "timeout":
                    self.assertIs(metadata["timed_out"], True)
                else:
                    self.assertIs(metadata["output_exceeded"], True)
                    self.assertEqual(output, b"X" * bop.DEFAULT_LIMIT)
                self.assertEqual(_reader_threads(), [])

    def test_invalid_invocation_fails_explicitly(self):
        with self.assertRaises(TypeError):
            bop.run_bounded("python -V", cwd=ROOT, env=_test_env(), timeout=1)
        with self.assertRaises(ValueError):
            bop.run_bounded([sys.executable, "-V"], cwd=ROOT, env=_test_env(), timeout=0)


@unittest.skipUnless(os.name == "posix", "requires POSIX sessions and signals")
class PosixProcessTreeTests(_CaptureAssertions):
    def test_leader_exit_kills_term_resistant_descendant_and_preserves_foreign_sentinel(self):
        sentinel_code = "import os,time; print(os.getpid(), flush=True); time.sleep(30)"
        sentinel = subprocess.Popen(
            [sys.executable, "-c", sentinel_code],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            bufsize=0,
        )
        try:
            ready, _, _ = select.select([sentinel.stdout], [], [], 3.0)
            self.assertTrue(ready, "foreign sentinel did not become ready")
            sentinel_pid = int(sentinel.stdout.readline().strip())
            sentinel_pgid = os.getpgid(sentinel_pid)
            fds_before = _fd_count()
            descendant_code = r'''
import os, signal, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
os.write(int(sys.argv[1]), b"R")
time.sleep(30)
'''
            leader_code = f'''
import os, subprocess, sys
r, w = os.pipe()
child = subprocess.Popen([sys.executable, "-c", {descendant_code!r}, str(w)], pass_fds=(w,), close_fds=True)
os.close(w)
assert os.read(r, 1) == b"R"
os.close(r)
leader, group = os.getpid(), os.getpgrp()
child_group = os.getpgid(child.pid)
print(f"OWNED {{leader}} {{child.pid}} {{group}} {{child_group}}", flush=True)
if group != leader or child_group != group:
    raise SystemExit(91)
'''
            result = _run(leader_code, timeout=4.0, limit=256)
            self.assertEqual(result["returncode"], 0, result)
            match = re.search(rb"OWNED (\d+) (\d+) (\d+) (\d+)", result["stdout"])
            self.assertIsNotNone(match, result["stdout"])
            leader_pid, child_pid, group, child_group = map(int, match.groups())
            self.assertEqual(leader_pid, group)
            self.assertEqual(child_group, group)
            self.assertNotEqual(sentinel_pgid, group)
            _assert_posix_pid_not_live(self, leader_pid)
            _assert_posix_pid_not_live(self, child_pid)
            self.assertIsNone(sentinel.poll(), "foreign sibling/sentinel was killed")
            self.assertTrue(os.kill(sentinel_pid, 0) is None)
            self.assert_clean(result)
            if fds_before is not None:
                self.assertEqual(_fd_count(), fds_before, "capture leaked a pipe descriptor")
        finally:
            if sentinel.poll() is None:
                sentinel.terminate()
                sentinel.wait(timeout=3.0)
            if sentinel.stdout is not None:
                sentinel.stdout.close()

    def test_lost_wnowait_identity_fails_closed_without_pid_signal(self):
        code = "import os,time; os.write(1,b'finished'); time.sleep(0.05)"
        with mock.patch.object(
            bop, "_leader_exited_without_reaping", side_effect=OSError("injected WNOWAIT failure")
        ), mock.patch.object(bop.os, "killpg") as killpg:
            with self.assertRaises(bop.BoundedProcessError) as caught:
                _run(code, timeout=2.0, limit=32)
        result = caught.exception.result
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["stdout"], b"finished")
        self.assertFalse(result["cleanup_verified"])
        killpg.assert_not_called()
        self.assertEqual(_reader_threads(), [])

    def test_timeout_kills_owned_descendant_tree_and_keeps_readiness_bytes(self):
        descendant_code = r'''
import os, signal, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
os.write(int(sys.argv[1]), b"R")
time.sleep(30)
'''
        leader_code = f'''
import os, subprocess, sys, time
r, w = os.pipe()
child = subprocess.Popen([sys.executable, "-c", {descendant_code!r}, str(w)], pass_fds=(w,), close_fds=True)
os.close(w)
assert os.read(r, 1) == b"R"
os.close(r)
print(f"TREE {{os.getpid()}} {{child.pid}}", flush=True)
time.sleep(30)
'''
        started = time.monotonic()
        result = _run(leader_code, timeout=0.3, limit=128)
        self.assertTrue(result["timed_out"])
        self.assertLess(time.monotonic() - started, 3.0)
        match = re.search(rb"TREE (\d+) (\d+)", result["stdout"])
        self.assertIsNotNone(match, result["stdout"])
        for pid in map(int, match.groups()):
            _assert_posix_pid_not_live(self, pid)
        self.assert_clean(result)


@unittest.skipUnless(os.name == "nt", "native Windows Job Object acceptance runs on Windows CI")
class WindowsJobTests(_CaptureAssertions):
    def _windows_pid_live(self, pid):
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x00100000 | 0x1000, False, pid)
        if not handle:
            code = ctypes.get_last_error()
            if code == 87:  # ERROR_INVALID_PARAMETER means no such PID.
                return False
            raise ctypes.WinError(code)
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 258
        finally:
            self.assertTrue(kernel32.CloseHandle(handle))

    def _injected_api(self, method, replacement):
        api = bop._new_windows_api()
        patcher = mock.patch.object(bop, "_new_windows_api", return_value=api)
        patcher.start()
        self.addCleanup(patcher.stop)
        method_patcher = mock.patch.object(api, method, side_effect=replacement)
        method_patcher.start()
        self.addCleanup(method_patcher.stop)
        return api

    def test_job_configuration_failure_closes_unassigned_job(self):
        self._injected_api("configure_job", OSError("injected job configuration failure"))
        with self.assertRaises(bop.BoundedProcessError) as caught:
            _run("raise SystemExit('must not start')")
        self.assertTrue(caught.exception.result["cleanup_verified"])

    def test_assignment_failure_terminates_and_reaps_suspended_child(self):
        self._injected_api("assign_job", OSError("injected assignment failure"))
        with self.assertRaises(bop.BoundedProcessError) as caught:
            _run("import time; time.sleep(30)")
        self.assertIsNotNone(caught.exception.result["returncode"])
        self.assertTrue(caught.exception.result["cleanup_verified"])
        self.assert_clean(caught.exception.result)

    def test_resume_failure_terminates_assigned_job_before_return(self):
        self._injected_api("resume_primary", OSError("injected resume failure"))
        with self.assertRaises(bop.BoundedProcessError) as caught:
            _run("import time; time.sleep(30)")
        self.assertIsNotNone(caught.exception.result["returncode"])
        self.assertTrue(caught.exception.result["cleanup_verified"])
        self.assert_clean(caught.exception.result)

    def test_job_close_failure_is_reported_and_retried(self):
        api = bop._new_windows_api()
        job_handles = []
        original_create = api.create_job
        original_close = api.close_handle
        attempts = {"count": 0}

        def create_job():
            handle = original_create()
            job_handles.append(int(handle))
            return handle

        def close_handle(handle):
            if job_handles and int(handle) == job_handles[0] and attempts["count"] == 0:
                attempts["count"] += 1
                raise OSError("injected first Job CloseHandle failure")
            return original_close(handle)

        with mock.patch.object(bop, "_new_windows_api", return_value=api):
            with mock.patch.object(api, "create_job", side_effect=create_job):
                with mock.patch.object(api, "close_handle", side_effect=close_handle):
                    with self.assertRaises(bop.BoundedProcessError) as caught:
                        _run("print('captured before close failure')")
        self.assertEqual(attempts["count"], 1)
        self.assertIn(b"captured before close failure", caught.exception.result["stdout"])
        self.assertTrue(caught.exception.result["cleanup_verified"])
        self.assert_clean(caught.exception.result)

    def test_timeout_and_leader_exit_reap_job_descendant(self):
        child_code = "import os,time; print('DESC', os.getpid(), flush=True); time.sleep(30)"
        parent_code = f'''
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", {child_code!r}], stdout=subprocess.PIPE, text=True)
line = child.stdout.readline()
print(line.strip(), flush=True)
time.sleep(30)
'''
        result = _run(parent_code, timeout=0.3, limit=256)
        self.assertTrue(result["timed_out"])
        self.assertTrue(result["cleanup_verified"])
        match = re.search(rb"DESC (\d+)", result["stdout"])
        self.assertIsNotNone(match, result["stdout"])
        self.assertFalse(self._windows_pid_live(int(match.group(1))), "Job descendant survived cleanup")
        self.assert_clean(result)

    def test_leader_exit_identity_and_job_accounting(self):
        """Retain the same descendant object before releasing its parent."""
        if os.name != "nt":
            raise unittest.SkipTest("requires native Windows process handles")
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        kernel.GetProcessTimes.restype = wintypes.BOOL
        kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        kernel.IsProcessInJob.restype = wintypes.BOOL
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        api = bop._new_windows_api()
        job_holder = []
        counts = []
        original_create = api.create_job
        original_active = api.active_processes
        result_holder = {}
        handle = None

        def create():
            job = original_create()
            job_holder.append(job)
            return job

        def active(job):
            count = original_active(job)
            counts.append(count)
            return count

        def creation_time():
            values = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
                raise ctypes.WinError(ctypes.get_last_error())
            return (values[0].dwHighDateTime << 32) | values[0].dwLowDateTime

        with tempfile.TemporaryDirectory(prefix="windows-held-identity-") as directory:
            root = Path(directory)
            ready, release = root / "pid", root / "release"
            child_code = "import os,time; print('DESC',os.getpid(),flush=True); time.sleep(30)"
            parent_code = f'''import pathlib,subprocess,sys,time
child = subprocess.Popen([sys.executable, "-c", {child_code!r}], stdout=subprocess.PIPE, text=True)
line = child.stdout.readline()
pathlib.Path({str(ready)!r}).write_text(line.strip().split()[1])
print(line.strip(), flush=True)
while not pathlib.Path({str(release)!r}).exists(): time.sleep(0.005)
'''

            def run():
                try:
                    result_holder["result"] = _run(parent_code, timeout=5.0, limit=1024)
                except BaseException as exc:
                    result_holder["error"] = exc

            with mock.patch.object(bop, "_new_windows_api", return_value=api), mock.patch.object(api, "create_job", side_effect=create), mock.patch.object(api, "active_processes", side_effect=active):
                thread = threading.Thread(target=run, name="held-process-identity-probe")
                thread.start()
                observations = {"test": "leader-exit-held-process-identity", "job_active_counts": counts}
                try:
                    deadline = time.monotonic() + 3.0
                    while not ready.exists() or not ready.read_bytes():
                        self.assertLess(time.monotonic(), deadline, result_holder)
                        time.sleep(0.005)
                    pid = int(ready.read_text())
                    handle = kernel.OpenProcess(0x00100000 | 0x1000 | 0x0001, False, pid)
                    self.assertTrue(handle, ctypes.get_last_error())
                    before = creation_time()
                    member = wintypes.BOOL()
                    self.assertTrue(kernel.IsProcessInJob(handle, job_holder[0], ctypes.byref(member)))
                    observations.update(pid=pid, creation_time=before, member_before=bool(member.value), wait_before=kernel.WaitForSingleObject(handle, 0))
                    self.assertTrue(member.value, observations)
                    self.assertEqual(observations["wait_before"], 258, observations)
                    release.write_bytes(b"release parent")
                    thread.join(10.0)
                    self.assertFalse(thread.is_alive(), "bounded helper did not return")
                    error = result_holder.get("error")
                    result = result_holder.get("result") or getattr(error, "result", {}) or {}
                    observations.update(wait_after=kernel.WaitForSingleObject(handle, 0), creation_time_after=creation_time(), cleanup_verified=result.get("cleanup_verified"), returncode=result.get("returncode"), timed_out=result.get("timed_out"), cleanup_errors=result.get("cleanup_errors"), error_type=type(error).__name__ if error else None)
                    print("WINDOWS_HELD_IDENTITY " + json.dumps(observations, sort_keys=True), flush=True)
                    if error:
                        raise error
                    self.assertEqual(observations["creation_time_after"], before)
                    self.assertEqual(observations["wait_after"], 0, observations)
                    self.assertEqual(result["returncode"], 0)
                    self.assertFalse(result["timed_out"])
                    self.assert_clean(result)
                finally:
                    release.write_bytes(b"release parent")
                    if handle:
                        if kernel.WaitForSingleObject(handle, 0) == 258:
                            self.assertTrue(kernel.TerminateProcess(handle, 1))
                            self.assertEqual(kernel.WaitForSingleObject(handle, 3000), 0)
                        self.assertTrue(kernel.CloseHandle(handle))
                    thread.join(10.0)
                    self.assertFalse(thread.is_alive())

    def test_leader_exit_alone_closes_inherited_pipe_descendant(self):
        child_code = "import os,time; print('DESC', os.getpid(), flush=True); time.sleep(30)"
        parent_code = f'''
import subprocess, sys
child = subprocess.Popen([sys.executable, "-c", {child_code!r}], stdout=subprocess.PIPE, text=True)
line = child.stdout.readline()
print(line.strip(), flush=True)
'''
        result = _run(parent_code, timeout=3.0, limit=256)
        self.assertEqual(result["returncode"], 0)
        self.assertTrue(result["cleanup_verified"])
        match = re.search(rb"DESC (\d+)", result["stdout"])
        self.assertIsNotNone(match, result["stdout"])
        self.assertFalse(self._windows_pid_live(int(match.group(1))), "Job descendant survived leader exit")
        self.assert_clean(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
