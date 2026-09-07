#!/usr/bin/env python3
"""Language-neutral process comparator for Go↔Rust contract cases."""

from __future__ import annotations

import argparse
import base64
import binascii
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any, cast

REPO = Path(__file__).resolve().parents[2]
GENERATE = REPO / "scripts" / "rust-port" / "generate.py"
HELPER = REPO / "scripts" / "rust-port" / "go-oracle"
CASE_FILE = REPO / "testdata" / "rust-port" / "cases" / "oracle-selftest.json"
RESERVED = {
    "HOME", "USERPROFILE", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
    "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "TZ",
    "TERM", "NO_COLOR", "SYMCOREKIT_PORT_CLOCK", "SYMCOREKIT_PORT_SEED",
}
INHERITED = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")
MAX_STREAM = 8 * 1024 * 1024


@dataclass
class Result:
    exit_code: int
    signal_name: str
    timed_out: bool
    stdout: bytes
    stderr: bytes
    files: list[dict[str, Any]]
    sqlite: dict[str, Any]
    http_transcript: Any
    process_argv: Any


def allowed_env(name: str) -> bool:
    upper = name.upper()
    return upper.startswith(("PORT_", "SYMCOREKIT_")) or upper in {"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"}


def replace(value: str, roots: dict[str, str]) -> str:
    for marker in sorted(roots):
        value = value.replace(marker, roots[marker])
    return value


def replace_json_strings(value: Any, roots: dict[str, str]) -> Any:
    if isinstance(value, str):
        return replace(value, roots)
    if isinstance(value, list):
        return [replace_json_strings(item, roots) for item in value]
    if isinstance(value, dict):
        return {key: replace_json_strings(item, roots) for key, item in value.items()}
    return value


def decode_bytes(container: dict[str, Any], prefix: str, roots: dict[str, str]) -> bytes:
    fields = [name for name in (f"{prefix}_utf8", f"{prefix}_base64", f"{prefix}_json") if name in container]
    if len(fields) > 1:
        raise ValueError(f"{prefix} must use exactly one byte representation")
    if prefix in container:
        raise ValueError(f"legacy text field {prefix!r} is forbidden; use {prefix}_utf8, {prefix}_base64 or {prefix}_json")
    if not fields:
        return b""
    field = fields[0]
    value = container[field]
    if field.endswith("_base64"):
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a base64 string")
        try:
            return base64.b64decode(value, validate=True)
        except binascii.Error as error:
            raise ValueError(f"{field} is invalid base64") from error
    if field.endswith("_utf8"):
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a UTF-8 string")
        return replace(value, roots).encode("utf-8")
    replaced = replace_json_strings(value, roots)
    return json.dumps(replaced, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def isolated_env(roots: dict[str, str], extra: dict[str, str], clock: str, seed: str) -> dict[str, str]:
    for key in extra:
        upper = key.upper()
        if upper in RESERVED:
            raise ValueError(f"case environment cannot override reserved variable {key!r}")
        if not allowed_env(upper):
            raise ValueError(f"case environment variable is not allowlisted: {key!r}")
    env = {
        "HOME": roots["${HOME}"], "USERPROFILE": roots["${HOME}"],
        "XDG_CONFIG_HOME": str(Path(roots["${HOME}"]) / ".config"),
        "XDG_DATA_HOME": str(Path(roots["${HOME}"]) / ".local" / "share"),
        "XDG_CACHE_HOME": str(Path(roots["${HOME}"]) / ".cache"),
        "XDG_STATE_HOME": str(Path(roots["${HOME}"]) / ".local" / "state"),
        "XDG_RUNTIME_DIR": roots["${RUNTIME}"],
        "TMPDIR": roots["${TMPDIR}"], "TMP": roots["${TMPDIR}"], "TEMP": roots["${TMPDIR}"],
        "LANG": "C", "LC_ALL": "C", "TZ": "UTC", "TERM": "dumb", "NO_COLOR": "1",
        "SYMCOREKIT_PORT_CLOCK": clock, "SYMCOREKIT_PORT_SEED": seed,
    }
    for key in INHERITED:
        if key in os.environ:
            env[key] = os.environ[key]
    for key in sorted(extra):
        env[key] = replace(extra[key], roots)
    return env


def safe_path(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError(f"sandbox path must be non-empty and relative: {relative!r}")
    candidate = (root / relative).resolve()
    if root.resolve() not in candidate.parents and candidate != root.resolve():
        raise ValueError(f"sandbox path escapes root: {relative!r}")
    return candidate


def manifest(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        stat = path.lstat()
        entry: dict[str, Any] = {"path": path.relative_to(root).as_posix(), "mode": stat.st_mode & 0o777}
        if path.is_symlink():
            entry.update({"type": "symlink", "target": os.readlink(path)})
        elif path.is_dir():
            entry["type"] = "dir"
        elif path.is_file():
            entry.update({"type": "file", "size": stat.st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        else:
            entry["type"] = "other"
        records.append(entry)
    return records


def sqlite_snapshots(root: Path, specs: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for spec in specs:
        path = safe_path(root, spec["path"])
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            result[spec["path"]] = [
                {"sql": query, "rows": connection.execute(query).fetchall()}
                for query in spec.get("queries", [])
            ]
        finally:
            connection.close()
    return result


def read_json_observation(root: Path, relative: str | None) -> Any:
    if not relative:
        return []
    return json.loads(safe_path(root, relative).read_text())


def terminate_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_case(binary: Path, case: dict[str, Any]) -> Result:
    binary = binary.resolve()
    with tempfile.TemporaryDirectory(prefix="corekit-port-") as raw:
        root = Path(raw)
        home, workspace, temporary, runtime = (root / name for name in ("home", "workspace", "tmp", "runtime"))
        for directory in (home, workspace, temporary, runtime, home / ".local" / "state"):
            directory.mkdir(parents=True, mode=0o700)
        roots = {"${SANDBOX}": str(root), "${HOME}": str(home), "${WORKSPACE}": str(workspace), "${TMPDIR}": str(temporary), "${RUNTIME}": str(runtime)}
        for setup in case.get("setup", []):
            target = safe_path(workspace, setup["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(decode_bytes(setup, "content", roots))
            target.chmod(setup.get("mode", 0o600))
        working_dir = workspace if not case.get("working_dir") else safe_path(workspace, replace(case["working_dir"], roots))
        args = [replace(value, roots) for value in case.get("args", [])]
        stdin_value = decode_bytes(case, "stdin", roots)
        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        process = cast(subprocess.Popen[bytes], subprocess.Popen(
            [str(binary), *args],
            cwd=working_dir,
            env=isolated_env(
                roots,
                case.get("env", {}),
                case.get("clock", "2026-01-01T00:00:00Z"),
                case.get("seed", "1"),
            ),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs,
        ))
        timed_out = False
        try:
            stdout, stderr = process.communicate(stdin_value, timeout=case.get("timeout_ms", 10000) / 1000)
        except subprocess.TimeoutExpired:
            timed_out = True
            terminate_tree(process)
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired as error:
                process.kill()
                raise RuntimeError("process tree did not terminate within two seconds") from error
        if len(stdout) > MAX_STREAM or len(stderr) > MAX_STREAM:
            raise RuntimeError("captured stream exceeds 8 MiB")
        code = process.returncode or 0
        signal_name = ""
        if code < 0:
            signal_name = signal.Signals(-code).name
        result = Result(
            exit_code=code, signal_name=signal_name, timed_out=timed_out,
            stdout=stdout, stderr=stderr, files=manifest(root),
            sqlite=sqlite_snapshots(root, case.get("sqlite_snapshots", [])),
            http_transcript=read_json_observation(root, case.get("http_transcript_path")),
            process_argv=read_json_observation(root, case.get("process_argv_path")),
        )
        # TempDirectory cleanup is part of the harness contract and happens here.
        return result


def normalized_stream(value: bytes, mode: str) -> Any:
    if mode == "ignore":
        return None
    if mode == "json":
        return json.loads(value)
    if mode == "console_text":
        return value.replace(b"\r\n", b"\n")
    if mode == "bytes":
        return value
    raise ValueError(f"unknown stream comparison mode {mode!r}")


def compare(case: dict[str, Any], left: Result, right: Result) -> None:
    checks = (
        ("timeout", left.timed_out, right.timed_out),
        ("exit code", left.exit_code, right.exit_code),
        ("signal", left.signal_name, right.signal_name),
        ("stdout", normalized_stream(left.stdout, case.get("stdout_mode", "bytes")), normalized_stream(right.stdout, case.get("stdout_mode", "bytes"))),
        ("stderr", normalized_stream(left.stderr, case.get("stderr_mode", "bytes")), normalized_stream(right.stderr, case.get("stderr_mode", "bytes"))),
        ("filesystem", left.files if case.get("compare_files", False) else None, right.files if case.get("compare_files", False) else None),
        ("sqlite", left.sqlite, right.sqlite),
        ("HTTP transcript", left.http_transcript, right.http_transcript),
        ("process argv", left.process_argv, right.process_argv),
    )
    for label, lhs, rhs in checks:
        if lhs != rhs:
            left_hash = hashlib.sha256(repr(lhs).encode()).hexdigest()
            right_hash = hashlib.sha256(repr(rhs).encode()).hexdigest()
            raise AssertionError(f"{label} mismatch: left_sha256={left_hash} right_sha256={right_hash}")


def reject_identical_implementations(left: Path, right: Path) -> None:
    left = left.resolve()
    right = right.resolve()
    try:
        if os.path.samefile(left, right):
            raise ValueError("normal parity mode requires distinct Go and Rust executables")
    except FileNotFoundError:
        pass
    if hashlib.sha256(left.read_bytes()).digest() == hashlib.sha256(right.read_bytes()).digest():
        raise ValueError("normal parity mode rejects byte-identical executables; use --self-test for deliberate same-binary checks")


def build_probe(target: Path, oracle: Path) -> None:
    source = (HELPER / "go.mod").read_text()
    marker = "replace github.com/danieljustus/symaira-corekit => ../../.."
    modfile = target.with_suffix(".mod")
    modfile.write_text(source.replace(marker, f"replace github.com/danieljustus/symaira-corekit => {oracle.as_posix()}"))
    shutil.copy2(HELPER / "go.sum", target.with_suffix(".sum"))
    env = os.environ.copy()
    env.update({"CGO_ENABLED": "0", "GOTOOLCHAIN": "go1.26.6"})
    subprocess.run(["go", "build", "-trimpath", "-modfile", str(modfile), "-o", str(target), "./cmd/probe"], cwd=HELPER, env=env, check=True)


def extract_oracle(target: Path) -> None:
    process = subprocess.Popen(
        ["git", "archive", "--format=tar", "f3d3eb79b9b1f31b4f973d2ed518a8292cedf588"],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                destination = (target / member.name).resolve()
                if target.resolve() not in destination.parents and destination != target.resolve():
                    raise RuntimeError(f"oracle archive path escapes target: {member.name}")
                archive.extract(member, target, filter="data")
    finally:
        process.stdout.close()
    stderr = process.stderr.read() if process.stderr else b""
    if process.wait() != 0:
        raise RuntimeError(f"create oracle archive failed: {stderr.decode('utf-8', 'replace')}")


def process_exists(pid: int) -> bool:
    if os.name == "nt":
        result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def self_test() -> None:
    suite = json.loads(CASE_FILE.read_text())
    case = suite["cases"][0]
    with tempfile.TemporaryDirectory(prefix="corekit-oracle-selftest-") as raw:
        temp = Path(raw)
        oracle = temp / "oracle"
        oracle.mkdir()
        extract_oracle(oracle)
        probe = temp / ("probe.exe" if os.name == "nt" else "probe")
        build_probe(probe, oracle)
        left = run_case(probe, case)
        right = run_case(probe, case)
        compare(case, left, right)
        try:
            reject_identical_implementations(probe, probe)
        except ValueError:
            pass
        else:
            raise AssertionError("normal parity mode accepted an identical executable")
        changed_output = json.loads(right.stdout)
        changed_output["version_text"] = "deliberately-mutated"
        mutated = Result(**{**right.__dict__, "stdout": json.dumps(changed_output).encode()})
        try:
            compare(case, left, mutated)
        except AssertionError:
            pass
        else:
            raise AssertionError("deliberate output mutation was not detected")

        bad = dict(case)
        bad["env"] = {"HOME": "/real-home"}
        try:
            run_case(probe, bad)
        except ValueError:
            pass
        else:
            raise AssertionError("reserved HOME override was accepted")

        binary_case = {
            "args": [str(Path(__file__).resolve()), "--harness-helper", "echo"],
            "stdin_base64": "AP8NCg==",
            "setup": [{"path": "binary.dat", "content_base64": "AP8NCg==", "mode": 0o600}],
            "compare_files": True,
        }
        binary_left = run_case(Path(sys.executable), binary_case)
        binary_right = run_case(Path(sys.executable), binary_case)
        compare(binary_case, binary_left, binary_right)
        if binary_left.stdout != b"\x00\xff\r\n":
            raise AssertionError("base64 stdin was not preserved byte-for-byte")
        windows_json = decode_bytes(
            {"stdin_json": {"path": "${WORKSPACE}/fixture"}},
            "stdin",
            {"${WORKSPACE}": r"C:\port\workspace"},
        )
        if json.loads(windows_json)["path"] != r"C:\port\workspace/fixture":
            raise AssertionError("JSON path replacement did not preserve Windows backslashes")

        pid_file = temp / "descendant.pid"
        helper_case = {
            "args": [str(Path(__file__).resolve()), "--harness-helper", "child"],
            "env": {"PORT_PID_FILE": str(pid_file)}, "timeout_ms": 5000, "stderr_mode": "ignore",
        }
        timed = run_case(Path(sys.executable), helper_case)
        if not timed.timed_out:
            raise AssertionError("descendant cleanup case did not time out")
        pid = int(pid_file.read_text())
        for _ in range(20):
            if not process_exists(pid):
                break
            time.sleep(0.05)
        else:
            raise AssertionError(f"descendant process {pid} survived timeout cleanup")
    print("PASS Go↔Go equality, identical-binary rejection, byte fixtures, isolation and process-tree cleanup")


def helper(mode: str) -> None:
    if mode == "echo":
        sys.stdout.buffer.write(sys.stdin.buffer.read())
        return
    if mode == "hang":
        time.sleep(30)
        return
    if mode == "child":
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--harness-helper", "hang"])
        Path(os.environ["PORT_PID_FILE"]).write_text(str(child.pid))
        child.wait()
        return
    raise ValueError(mode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--harness-helper", choices=("echo", "hang", "child"))
    parser.add_argument("--case", type=Path)
    parser.add_argument("--left", type=Path)
    parser.add_argument("--right", type=Path)
    args = parser.parse_args()
    try:
        if args.harness_helper:
            helper(args.harness_helper)
        elif args.self_test:
            self_test()
        elif args.case and args.left and args.right:
            reject_identical_implementations(args.left, args.right)
            case_document = json.loads(args.case.read_text(encoding="utf-8"))
            if "cases" in case_document:
                cases = case_document["cases"]
                if not isinstance(cases, list) or len(cases) != 1:
                    raise ValueError("suite input must contain exactly one case")
                case = cases[0]
            else:
                case = case_document
            compare(case, run_case(args.left, case), run_case(args.right, case))
            print(f"PASS {case.get('id', args.case.name)}")
        else:
            parser.error("use --self-test or --case/--left/--right")
        return 0
    except (OSError, ValueError, RuntimeError, AssertionError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
