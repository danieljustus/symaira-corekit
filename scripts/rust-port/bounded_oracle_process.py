"""Bounded, owned process-tree capture for trusted Go/Cargo fixtures.

This is a test-harness helper, not a sandbox. POSIX owns one new session and
kills its process group. Windows starts suspended, assigns a private kill-on-
close Job before resuming, and does not permit intentional job breakaway.
Deliberately detached or hostile descendants are outside this helper's scope.
"""
from __future__ import annotations

import math
import os
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
from itertools import count
from typing import Mapping, Sequence

DEFAULT_LIMIT = 2 * 1024 * 1024
_READ_CHUNK = 64 * 1024
_TERM_GRACE = 0.15
_CLEANUP_WAIT = 3.0
_CAPTURE_IDS = count()


class BoundedProcessError(RuntimeError):
    """Execution/setup/cleanup error; ``result`` retains any captured bytes."""

    def __init__(self, message: str, result: dict | None = None):
        super().__init__(message)
        self.result = result


class _WindowsOwnedHandleError(OSError):
    """A Win32 auxiliary handle remained open after the bounded close retry."""


class _Capture:
    def __init__(self, streams, limit: int):
        self.streams = streams
        self.limit = limit
        self.buffers = [bytearray() for _ in streams]
        self.ended = [False for _ in streams]
        self.exceeded = False
        self.errors: list[BaseException] = []
        self.lock = threading.Lock()
        self.threads: list[threading.Thread] = []

    def start(self) -> None:
        capture_id = next(_CAPTURE_IDS)
        for index, stream in enumerate(self.streams):
            thread = threading.Thread(
                target=self._read,
                args=(stream, index),
                name=f"bounded-oracle-reader-{capture_id}-{index}",
                daemon=True,
            )
            thread.start()
            self.threads.append(thread)

    def _read(self, stream, index: int) -> None:
        output = self.buffers[index]
        try:
            while True:
                room = self.limit - len(output)
                # One extra byte distinguishes exact-limit EOF from overflow.
                chunk = stream.read(min(_READ_CHUNK, room + 1))
                if not chunk:
                    break
                if len(chunk) > room:
                    output.extend(chunk[:room])
                    with self.lock:
                        self.exceeded = True
                    break
                output.extend(chunk)
        except BaseException as exc:
            with self.lock:
                self.errors.append(exc)
        finally:
            try:
                stream.close()
            except BaseException as exc:
                with self.lock:
                    self.errors.append(exc)
            with self.lock:
                self.ended[index] = True

    def has_exceeded(self) -> bool:
        with self.lock:
            return self.exceeded

    def failures(self) -> list[BaseException]:
        with self.lock:
            return list(self.errors)

    def join(self, seconds: float) -> bool:
        end = time.monotonic() + seconds
        for thread in self.threads:
            thread.join(max(0.0, end - time.monotonic()))
        with self.lock:
            readers_ended = all(self.ended)
        return readers_ended and not any(thread.is_alive() for thread in self.threads)

    def raw(self, merge_stderr: bool) -> tuple[bytes, bytes]:
        stdout = bytes(self.buffers[0]) if self.buffers else b""
        stderr = b"" if merge_stderr or len(self.buffers) == 1 else bytes(self.buffers[1])
        return stdout, stderr


def _result(proc, capture, *, merge_stderr, timed_out, output_exceeded, cleanup_verified):
    stdout, stderr = capture.raw(merge_stderr) if capture else (b"", b"")
    return {
        "returncode": proc.returncode if proc else None,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": bool(timed_out),
        "output_exceeded": bool(output_exceeded),
        "cleanup_verified": bool(cleanup_verified),
    }


def _validate(command, cwd, env, timeout, limit, merge_stderr) -> None:
    if isinstance(command, (str, bytes, bytearray)) or not isinstance(command, Sequence) or not command:
        raise TypeError("command must be a non-empty argument sequence, not a shell string")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a finite positive number of seconds")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("limit must be a non-negative integer")
    if not isinstance(merge_stderr, bool):
        raise TypeError("merge_stderr must be bool")
    if cwd is None:
        raise TypeError("cwd is required")
    if env is not None and not isinstance(env, Mapping):
        raise TypeError("env must be a mapping or None")


def run_bounded(
    command: Sequence[str | bytes | os.PathLike],
    *,
    cwd,
    env: Mapping | None,
    timeout: float,
    limit: int = DEFAULT_LIMIT,
    merge_stderr: bool = False,
) -> dict:
    """Run without a shell, bounding each captured stream during reads.

    ``limit`` applies independently to stdout and stderr. With
    ``merge_stderr=True``, stderr is redirected to stdout at child creation, so
    one pipe preserves the kernel-observed write order and the same single cap
    applies to the combined stream. Overflow and timeout return bounded raw
    bytes with cleanup status; invocation and cleanup failures raise
    ``BoundedProcessError`` (whose ``result`` retains bytes when available).
    """
    _validate(command, cwd, env, timeout, limit, merge_stderr)
    deadline = time.monotonic() + timeout
    if os.name == "nt":
        return _run_windows(command, cwd, env, deadline, timeout, limit, merge_stderr)
    return _run_posix(command, cwd, env, deadline, timeout, limit, merge_stderr)


def run_checked(command, *, cwd, env, timeout, artifact_dir=None, merge_stderr=False, check=False):
    """Retain bounded bytes before classifying Go/Git/Cargo execution failures."""
    error = None
    try:
        result = run_bounded(command, cwd=cwd, env=env, timeout=timeout, merge_stderr=merge_stderr)
    except BoundedProcessError as exc:
        result = exc.result
        error = exc
    except OSError as exc:
        result = None
        error = exc
    if artifact_dir is not None:
        root = Path(artifact_dir)
        root.mkdir(parents=True, exist_ok=True)
        record = Path(tempfile.mkdtemp(prefix="command-", dir=root))
        (record / "stdout.raw").write_bytes(result["stdout"] if result else b"")
        (record / "stderr.raw").write_bytes(result["stderr"] if result else b"")
        metadata = {key: value for key, value in (result or {}).items() if key not in ("stdout", "stderr")}
        metadata.update(command=[os.fsdecode(item) for item in command], timeout_seconds=timeout,
                        success=bool(result and result["returncode"] == 0 and not result["timed_out"] and not result["output_exceeded"] and result["cleanup_verified"] and error is None),
                        error_type=type(error).__name__ if error else None)
        (record / "result.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    if error is not None:
        raise error
    if not isinstance(result, dict):
        raise BoundedProcessError("bounded executor returned no result")
    if result["timed_out"] or result["output_exceeded"] or not result["cleanup_verified"]:
        raise BoundedProcessError("command exceeded runtime/output bound or cleanup is unverified", result)
    completed = subprocess.CompletedProcess(command, result["returncode"], result["stdout"], result["stderr"])
    if check:
        completed.check_returncode()
    return completed


def _waitid_available() -> bool:
    return all(hasattr(os, name) for name in ("waitid", "P_PID", "WEXITED", "WNOHANG", "WNOWAIT"))


def _leader_exited_without_reaping(pid: int) -> bool:
    """Observe exit while retaining the leader PID/PGID against reuse."""
    while True:
        try:
            info = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            return bool(info and info.si_pid)
        except InterruptedError:
            continue


def _signal_group(pgid: int, sig: int, errors: list[str], *, leader_exited: bool) -> None:
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        # The leader is deliberately unreaped until all group signals are sent.
        # An absent group therefore means the OS already has no signal targets.
        pass
    except PermissionError as exc:
        # On Darwin, signalling a process group containing only the retained
        # zombie leader can report EPERM rather than ESRCH. Recheck non-reapingly
        # after the failure to cover a leader exiting between the first check
        # and killpg; ordinary same-user descendants remain signalable.
        if not leader_exited:
            try:
                leader_exited = _leader_exited_without_reaping(pgid)
            except OSError:
                pass
        if not leader_exited:
            # The leader can still be running in the narrow check->killpg race,
            # yet Darwin may reject the group operation. Its PID is still held
            # by WNOWAIT, so signal that exact leader as a bounded fallback;
            # a later group SIGKILL still handles ordinary same-user children.
            try:
                os.kill(pgid, sig)
            except ProcessLookupError:
                pass
            except OSError as direct_exc:
                errors.append(f"killpg and direct leader signal failed ({sig}): {direct_exc}")
    except OSError as exc:
        errors.append(f"killpg({pgid}, {sig}) failed: {exc}")


def _close_streams(proc, errors: list[str]) -> bool:
    streams = (getattr(proc, "stdin", None), getattr(proc, "stdout", None), getattr(proc, "stderr", None))
    for stream in streams:
        if stream is None:
            continue
        for attempt in (1, 2):
            if stream.closed:
                break
            try:
                stream.close()
            except OSError as exc:
                errors.append(f"pipe close attempt {attempt} failed: {exc}")
    return all(stream is None or stream.closed for stream in streams)


def _cleanup_posix(proc, pgid: int, capture: _Capture, merge_stderr: bool) -> tuple[bool, list[str]]:
    errors: list[str] = []
    # Keep the session leader as an unreaped zombie until both group signals
    # have been sent, preventing a recycled PID/PGID from being signalled.
    group_identity_safe = True
    try:
        leader_exited = _leader_exited_without_reaping(proc.pid)
    except OSError as exc:
        # Never signal a possibly recycled PGID when WNOWAIT cannot confirm
        # that the original group leader still anchors that numeric identity.
        errors.append(f"could not retain process-group leader identity: {exc}")
        leader_exited = False
        group_identity_safe = False
    if group_identity_safe:
        _signal_group(pgid, signal.SIGTERM, errors, leader_exited=leader_exited)
        time.sleep(_TERM_GRACE)
        try:
            # Refresh while the leader remains unreaped: it can exit during the
            # grace, which is why the following signal tolerates Darwin zombie EPERM.
            leader_exited = _leader_exited_without_reaping(proc.pid)
        except OSError as exc:
            errors.append(f"could not reconfirm process-group leader identity: {exc}")
            group_identity_safe = False
        if group_identity_safe:
            _signal_group(pgid, signal.SIGKILL, errors, leader_exited=leader_exited)
    # If WNOWAIT identity checks failed, intentionally send no PID/PGID signal:
    # the numeric identity may already be recycled. The bounded wait and reader
    # join below report cleanup as unverified instead of risking a foreign task.
    try:
        proc.wait(timeout=_CLEANUP_WAIT)
    except subprocess.TimeoutExpired:
        errors.append("process-group leader was not reaped within cleanup bound")
    except OSError as exc:
        errors.append(f"leader wait failed: {exc}")

    readers_done = capture.join(_CLEANUP_WAIT)
    if not readers_done:
        errors.append("capture reader did not terminate after process-group cleanup")
    pipes_closed = _close_streams(proc, errors)
    verified = proc.returncode is not None and readers_done and pipes_closed and not errors
    return verified, errors


def _run_posix(command, cwd, env, deadline, timeout, limit, merge_stderr) -> dict:
    if not _waitid_available():
        raise NotImplementedError("safe POSIX process-group cleanup requires waitid(WNOWAIT)")
    proc = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
        bufsize=0,
        start_new_session=True,
    )
    streams = [proc.stdout] + ([] if merge_stderr else [proc.stderr])
    capture = _Capture(streams, limit)
    timed_out = False
    output_exceeded = False
    operation_error: BaseException | None = None
    try:
        capture.start()
        while True:
            now = time.monotonic()
            if now >= deadline:
                timed_out = True
                break
            if capture.has_exceeded():
                output_exceeded = True
                break
            failures = capture.failures()
            if failures:
                operation_error = failures[0]
                break
            if _leader_exited_without_reaping(proc.pid):
                break
            time.sleep(min(0.01, max(0.0, deadline - now)))
    except BaseException as exc:
        operation_error = exc

    cleanup_verified, cleanup_errors = _cleanup_posix(proc, proc.pid, capture, merge_stderr)
    failures = capture.failures()
    result = _result(
        proc,
        capture,
        merge_stderr=merge_stderr,
        timed_out=timed_out,
        output_exceeded=output_exceeded or capture.has_exceeded(),
        cleanup_verified=cleanup_verified,
    )
    if operation_error is not None or failures or cleanup_errors:
        details = [str(operation_error)] if operation_error is not None else []
        details.extend(str(error) for error in failures)
        details.extend(cleanup_errors)
        raise BoundedProcessError("bounded process execution failed: " + "; ".join(details), result) from operation_error
    return result


# The Windows implementation uses only documented Win32 Job/Toolhelp APIs.
# CPython's subprocess.py calls _winapi.CreateProcess, retains hp and closes
# ht before Popen returns (see Lib/subprocess.py Popen._execute_child); hence
# the primary thread is re-opened by its documented Toolhelp thread ID.
if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _IOCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class _BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimitInformation),
            ("IoInfo", _IOCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _BasicAccountingInformation(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_int64),
            ("TotalKernelTime", ctypes.c_int64),
            ("ThisPeriodTotalUserTime", ctypes.c_int64),
            ("ThisPeriodTotalKernelTime", ctypes.c_int64),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    class _ThreadEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG),
            ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]

    class _WindowsAPI:
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
        JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
        TH32CS_SNAPTHREAD = 0x00000004
        THREAD_SUSPEND_RESUME = 0x0002
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        def __init__(self):
            self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k = self.kernel32
            k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            k.CreateJobObjectW.restype = ctypes.c_void_p
            k.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            k.SetInformationJobObject.restype = wintypes.BOOL
            k.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            k.AssignProcessToJobObject.restype = wintypes.BOOL
            k.TerminateJobObject.argtypes = [ctypes.c_void_p, wintypes.UINT]
            k.TerminateJobObject.restype = wintypes.BOOL
            k.QueryInformationJobObject.argtypes = [
                ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
            ]
            k.QueryInformationJobObject.restype = wintypes.BOOL
            k.CloseHandle.argtypes = [ctypes.c_void_p]
            k.CloseHandle.restype = wintypes.BOOL
            k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
            k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
            k.Thread32First.argtypes = [ctypes.c_void_p, ctypes.POINTER(_ThreadEntry32)]
            k.Thread32First.restype = wintypes.BOOL
            k.Thread32Next.argtypes = [ctypes.c_void_p, ctypes.POINTER(_ThreadEntry32)]
            k.Thread32Next.restype = wintypes.BOOL
            k.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            k.OpenThread.restype = ctypes.c_void_p
            k.ResumeThread.argtypes = [ctypes.c_void_p]
            k.ResumeThread.restype = wintypes.DWORD

        @staticmethod
        def _winerror(message: str) -> OSError:
            return ctypes.WinError(ctypes.get_last_error(), message)

        def create_job(self):
            handle = self.kernel32.CreateJobObjectW(None, None)
            if not handle:
                raise self._winerror("CreateJobObjectW failed")
            return handle

        def configure_job(self, job) -> None:
            limits = _ExtendedLimitInformation()
            limits.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            ok = self.kernel32.SetInformationJobObject(
                job,
                self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(limits),
                ctypes.sizeof(limits),
            )
            if not ok:
                raise self._winerror("SetInformationJobObject failed")

        def assign_job(self, job, process_handle) -> None:
            if not self.kernel32.AssignProcessToJobObject(job, process_handle):
                raise self._winerror("AssignProcessToJobObject failed")

        def terminate_job(self, job) -> None:
            if not self.kernel32.TerminateJobObject(job, 1):
                raise self._winerror("TerminateJobObject failed")

        def active_processes(self, job) -> int:
            info = _BasicAccountingInformation()
            returned = wintypes.DWORD()
            ok = self.kernel32.QueryInformationJobObject(
                job,
                self.JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
                ctypes.byref(info),
                ctypes.sizeof(info),
                ctypes.byref(returned),
            )
            if not ok:
                raise self._winerror("QueryInformationJobObject failed")
            if returned.value < ctypes.sizeof(info):
                raise OSError(f"short Job accounting result: {returned.value} bytes")
            return int(info.ActiveProcesses)

        def wait_job_empty(self, job, timeout: float) -> bool:
            # A Job handle is not signaled when ordinary processes exit; poll
            # the documented ActiveProcesses accounting field instead.
            deadline = time.monotonic() + timeout
            while True:
                if self.active_processes(job) == 0:
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                time.sleep(min(0.01, remaining))

        def primary_thread_id(self, pid: int) -> int:
            snapshot = self.kernel32.CreateToolhelp32Snapshot(self.TH32CS_SNAPTHREAD, 0)
            if snapshot is None or snapshot == self.INVALID_HANDLE_VALUE:
                raise self._winerror("CreateToolhelp32Snapshot failed")
            errors: list[str] = []
            thread_ids: list[int] = []
            try:
                entry = _ThreadEntry32()
                entry.dwSize = ctypes.sizeof(entry)
                ok = self.kernel32.Thread32First(snapshot, ctypes.byref(entry))
                if not ok:
                    raise self._winerror("Thread32First failed")
                while True:
                    if entry.th32OwnerProcessID == pid:
                        thread_ids.append(int(entry.th32ThreadID))
                    entry.dwSize = ctypes.sizeof(entry)
                    ctypes.set_last_error(0)
                    if not self.kernel32.Thread32Next(snapshot, ctypes.byref(entry)):
                        code = ctypes.get_last_error()
                        if code not in (0, 18):  # ERROR_NO_MORE_FILES is normal.
                            raise self._winerror("Thread32Next failed")
                        break
            finally:
                snapshot_closed = _close_owned_handle(self, snapshot, "thread snapshot", errors)
            if not snapshot_closed:
                raise _WindowsOwnedHandleError("thread snapshot handle remained open after retry")
            if errors:
                raise OSError("; ".join(errors))
            if len(thread_ids) != 1:
                raise OSError(f"expected one suspended primary thread for pid {pid}, found {len(thread_ids)}")
            return thread_ids[0]

        def resume_primary(self, thread_id: int) -> None:
            thread = self.kernel32.OpenThread(self.THREAD_SUSPEND_RESUME, False, thread_id)
            if not thread:
                raise self._winerror("OpenThread failed")
            errors: list[str] = []
            try:
                previous = self.kernel32.ResumeThread(thread)
                if previous == 0xFFFFFFFF:
                    raise self._winerror("ResumeThread failed")
                if previous != 1:
                    raise OSError(f"unexpected primary-thread suspend count: {previous}")
            finally:
                thread_closed = _close_owned_handle(self, thread, "primary thread", errors)
            if not thread_closed:
                raise _WindowsOwnedHandleError("primary thread handle remained open after retry")
            if errors:
                raise OSError("; ".join(errors))

        def close_handle(self, handle) -> None:
            if not self.kernel32.CloseHandle(handle):
                raise self._winerror("CloseHandle failed")


def _new_windows_api():
    if os.name != "nt":
        raise NotImplementedError("Windows Job Objects are unavailable on this host")
    return _WindowsAPI()


def _close_owned_handle(api, handle, label: str, errors: list[str]) -> bool:
    """Close an owned handle, retry once, and retain the first failure."""
    first_error = None
    for _ in range(2):
        try:
            api.close_handle(handle)
            if first_error is not None:
                errors.append(f"{label} CloseHandle first attempt failed: {first_error}")
            return True
        except BaseException as exc:
            if first_error is None:
                first_error = exc
    errors.append(f"{label} CloseHandle failed after retry: {first_error}")
    return False


def _close_popen_process_handle(api, proc, errors: list[str]) -> bool:
    handle = getattr(proc, "_handle", None)
    if handle is None:
        return True
    closed = _close_owned_handle(api, int(handle), "process", errors)
    if closed:
        # CPython's Handle.__del__ otherwise closes the same native handle.
        if hasattr(handle, "closed"):
            handle.closed = True
        proc._handle = None
    return closed


def _windows_cleanup(proc, job, assigned, capture, api) -> tuple[bool, list[str]]:
    errors: list[str] = []
    job_empty = job is None or not assigned
    job_closed = job is None
    process_handle_closed = proc is None
    termination_errors: list[str] = []

    if proc is not None:
        try:
            leader_running = proc.poll() is None
        except BaseException as exc:
            errors.append(f"Windows leader poll failed: {exc}")
            leader_running = True
        if leader_running:
            if assigned and job is not None:
                try:
                    api.terminate_job(job)
                except BaseException as exc:
                    termination_errors.append(f"TerminateJobObject failed: {exc}")
                    try:
                        proc.kill()
                    except BaseException as direct_exc:
                        errors.append(f"direct process termination fallback failed: {direct_exc}")
            else:
                # Assignment/setup failure occurs while the child is suspended;
                # it cannot have descendants, so terminate the direct process.
                try:
                    proc.kill()
                except BaseException as exc:
                    errors.append(f"suspended process termination failed: {exc}")
        try:
            proc.wait(timeout=_CLEANUP_WAIT)
        except subprocess.TimeoutExpired as exc:
            errors.append(f"Windows leader did not reap within cleanup bound: {exc}")
            if assigned and job is not None:
                try:
                    api.terminate_job(job)
                except BaseException as term_exc:
                    termination_errors.append(f"TerminateJobObject retry failed: {term_exc}")
            try:
                proc.kill()
                proc.wait(timeout=_CLEANUP_WAIT)
            except BaseException as retry_exc:
                errors.append(f"Windows leader reaping retry failed: {retry_exc}")
        except BaseException as exc:
            errors.append(f"Windows leader wait failed: {exc}")
        if proc.returncode is not None:
            # QueryInformationJobObject's ActiveProcesses count is decremented
            # after process references are released, so close Popen's retained
            # process handle before declaring the Job empty.
            process_handle_closed = _close_popen_process_handle(api, proc, errors)

    if job is not None and assigned and process_handle_closed:
        try:
            job_empty = api.wait_job_empty(job, 0.0)
        except BaseException as exc:
            errors.append(f"initial Job accounting query failed: {exc}")
            job_empty = False
        if not job_empty:
            for attempt in (1, 2):
                try:
                    api.terminate_job(job)
                except BaseException as exc:
                    termination_errors.append(f"TerminateJobObject attempt {attempt} failed: {exc}")
                try:
                    job_empty = api.wait_job_empty(job, _CLEANUP_WAIT)
                except BaseException as exc:
                    errors.append(f"Job ActiveProcesses query failed: {exc}")
                    job_empty = False
                    break
                if job_empty:
                    break
        if termination_errors:
            errors.extend(termination_errors)
        if not job_empty:
            errors.append("Windows Job still has active processes after termination")
            # The private kill-on-close limit remains the tree-wide fallback.
            job_closed = _close_owned_handle(api, job, "Job fallback", errors)
            if job_closed:
                job = None

    readers_done = True
    if capture is not None:
        readers_done = capture.join(_CLEANUP_WAIT)
        if not readers_done:
            errors.append("capture reader did not terminate after Job cleanup")
    pipes_closed = _close_streams(proc, errors) if proc is not None else True
    if job is not None:
        job_closed = _close_owned_handle(api, job, "Job", errors)
    if proc is not None and proc.returncode is None:
        process_handle_closed = False
    verified = (
        job_empty and job_closed and process_handle_closed and pipes_closed and readers_done
        and (proc is None or proc.returncode is not None)
    )
    return verified, errors


def _run_windows(command, cwd, env, deadline, timeout, limit, merge_stderr) -> dict:
    import _winapi

    api = _new_windows_api()
    job = None
    proc = None
    capture = None
    assigned = False
    timed_out = False
    output_exceeded = False
    setup_error: BaseException | None = None
    try:
        # Own/configure the Job before creating a process that can execute.
        job = api.create_job()
        api.configure_job(job)
        creationflags = getattr(_winapi, "CREATE_SUSPENDED", 0x00000004)
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            bufsize=0,
            creationflags=creationflags,
            close_fds=True,
        )
        streams = [proc.stdout] + ([] if merge_stderr else [proc.stderr])
        capture = _Capture(streams, limit)
        capture.start()
        api.assign_job(job, int(proc._handle))
        assigned = True
        thread_id = api.primary_thread_id(proc.pid)
        api.resume_primary(thread_id)
    except BaseException as exc:
        setup_error = exc

    if setup_error is not None:
        cleanup_verified, cleanup_errors = _windows_cleanup(proc, job, assigned, capture, api)
        result = _result(
            proc, capture, merge_stderr=merge_stderr, timed_out=False,
            output_exceeded=capture.has_exceeded() if capture else False,
            cleanup_verified=cleanup_verified and not isinstance(setup_error, _WindowsOwnedHandleError),
        )
        message = f"Windows process setup failed: {setup_error}"
        if cleanup_errors:
            message += "; cleanup: " + "; ".join(cleanup_errors)
        if isinstance(setup_error, (KeyboardInterrupt, SystemExit)):
            raise setup_error
        raise BoundedProcessError(message, result) from setup_error

    operation_error: BaseException | None = None
    try:
        while True:
            now = time.monotonic()
            if now >= deadline:
                timed_out = True
                break
            if capture.has_exceeded():
                output_exceeded = True
                break
            failures = capture.failures()
            if failures:
                operation_error = failures[0]
                break
            if proc.poll() is not None:
                break
            time.sleep(min(0.01, max(0.0, deadline - now)))
    except BaseException as exc:
        operation_error = exc

    cleanup_verified, cleanup_errors = _windows_cleanup(proc, job, assigned, capture, api)
    failures = capture.failures()
    result = _result(
        proc, capture, merge_stderr=merge_stderr, timed_out=timed_out,
        output_exceeded=output_exceeded or capture.has_exceeded(),
        cleanup_verified=cleanup_verified,
    )
    if operation_error is not None or failures or cleanup_errors:
        details = [str(operation_error)] if operation_error is not None else []
        details.extend(str(error) for error in failures)
        details.extend(cleanup_errors)
        if isinstance(operation_error, (KeyboardInterrupt, SystemExit)):
            raise operation_error
        raise BoundedProcessError("bounded process execution failed: " + "; ".join(details), result) from operation_error
    return result
