#!/usr/bin/env python3
"""Execute a pinned Go SQLite oracle in an isolated, disposable source tree.

Only temporary-root spelling is normalized in diagnostics. Platform-specific
modes are compared on the same native platform, not against a macOS capture.
The isolation controls paths/environment, not malicious code or OS credentials.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "scripts/rust-port/sqlite"
OUT = ROOT / "testdata/rust-port/sqlite/observations.json"
ORACLE_COMMIT = "f3d3eb79b9b1f31b4f973d2ed518a8292cedf588"
TOOLCHAIN = "go1.26.6"
EXPECTED_IDS = [f"SQL-{i:03}" for i in range(1, 7)]
MODULE = "github.com/danieljustus/symaira-corekit"
MAX_OUTPUT = 16 * 1024 * 1024


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(command: list[str], *, cwd: Path, env: dict | None = None,
        timeout: float = 120) -> bytes:
    """Bound execution and reap a process group; never leave pipe readers hung."""
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        options = {"start_new_session": True, "umask": 0o077} if os.name != "nt" else {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout,
                                stderr=stderr, **options)
        expired = False
        try:
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                expired = True
        finally:
            if os.name != "nt":
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif expired:
                # Native Windows execution remains a separate acceptance gate.
                try:
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=10, check=True)
                except (subprocess.SubprocessError, OSError) as exc:
                    proc.kill()
                    proc.wait(timeout=10)
                    raise RuntimeError("Windows process-tree cleanup failed") from exc
            proc.wait(timeout=10)
        if expired:
            raise TimeoutError(f"command exceeded {timeout}s: {command[0]}")
        for stream in (stdout, stderr):
            if stream.tell() > MAX_OUTPUT:
                raise RuntimeError("command output exceeded capture limit")
            stream.seek(0)
        if proc.returncode:
            raise RuntimeError(f"command failed ({proc.returncode}): {command[0]}\n"
                               + stderr.read().decode("utf-8", errors="replace"))
        return stdout.read()


def git_bytes(path: str) -> bytes:
    return run(["git", "show", f"{ORACLE_COMMIT}:{path}"], cwd=ROOT)


def source_snapshot() -> dict[str, bytes]:
    names = run(["git", "ls-tree", "-r", "--name-only", ORACLE_COMMIT,
                 "sqlitekit", "fsutil", "go.mod", "go.sum"], cwd=ROOT).decode().splitlines()
    names = [p for p in names if p in {"go.mod", "go.sum"}
             or (p.endswith(".go") and not p.endswith("_test.go"))]
    if "sqlitekit/sqlitekit.go" not in names or "go.mod" not in names:
        raise RuntimeError("incomplete pinned oracle snapshot")
    return {p: git_bytes(p) for p in sorted(names)}


def helper_snapshot() -> dict[str, bytes]:
    allowed = {".go", ".py", ".sql"}
    files = sorted(p for p in HELPER.rglob("*") if p.is_file()
                   and (p.suffix in allowed or p.name in {"go.mod", "go.sum"})
                   and "__pycache__" not in p.parts)
    result = {}
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(HELPER.resolve()):
            raise RuntimeError("helper source escapes its root")
        result[str(path.relative_to(ROOT)).replace(os.sep, "/")] = path.read_bytes()
    return result


def isolated_env(root: Path) -> dict[str, str]:
    # Cache paths are shared for downloads only; built artifacts remain isolated.
    goenv = json.loads(run(["go", "env", "-json", "GOPATH", "GOMODCACHE"], cwd=ROOT))
    env = {k: os.environ[k] for k in ("PATH", "SystemRoot", "WINDIR", "COMSPEC",
                                    "PATHEXT", "SYSTEMDRIVE") if k in os.environ}
    env.update({"GOTOOLCHAIN": TOOLCHAIN, "GOWORK": "off", "GOENV": "off",
                "GOFLAGS": "-mod=readonly", "CGO_ENABLED": "0", "LC_ALL": "C",
                "LANG": "C", "TZ": "UTC", "GOSUMDB": "sum.golang.org",
                "GOPROXY": "https://proxy.golang.org,direct",
                "GOPATH": goenv["GOPATH"], "GOMODCACHE": goenv["GOMODCACHE"]})
    for key, name in {"HOME": "home", "USERPROFILE": "home", "APPDATA": "config",
                      "LOCALAPPDATA": "data", "XDG_CONFIG_HOME": "config",
                      "XDG_DATA_HOME": "data", "XDG_CACHE_HOME": "cache",
                      "XDG_STATE_HOME": "state", "TMPDIR": "tmp", "TMP": "tmp",
                      "TEMP": "tmp", "GOCACHE": "go-cache"}.items():
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    return env


def json_stream(data: bytes) -> list[dict]:
    text = data.decode()
    decoder = json.JSONDecoder()
    result = []
    while text.strip():
        text = text.lstrip()
        value, end = decoder.raw_decode(text)
        result.append(value)
        text = text[end:]
    return result


def capture() -> dict:
    source = source_snapshot()
    helpers = helper_snapshot()
    with tempfile.TemporaryDirectory(prefix="rust006-oracle-") as name:
        root = Path(name)
        oracle = root / "source"
        for rel, data in {**source, **helpers}.items():
            path = oracle / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        env = isolated_env(root)
        helper = oracle / "scripts/rust-port/sqlite"
        observed_toolchain = run(["go", "env", "GOVERSION"], cwd=helper, env=env).decode().strip()
        if observed_toolchain != TOOLCHAIN:
            raise RuntimeError(f"wrong oracle toolchain: {observed_toolchain}")
        pinned_modules = json_stream(run(["go", "list", "-m", "-json", "all"], cwd=oracle, env=env))
        versions = {m["Path"]: m.get("Version", "") for m in pinned_modules}
        modules = json_stream(run(["go", "list", "-m", "-json", "all"], cwd=helper, env=env))
        dependencies = {}
        for module in modules:
            if module.get("Main"):
                continue
            path = module["Path"]
            if path == MODULE:
                replacement = module.get("Replace", {})
                if Path(replacement.get("Dir", "")).resolve() != oracle.resolve():
                    raise RuntimeError("oracle module replacement escaped pinned source")
            else:
                if "Replace" in module or versions.get(path) != module.get("Version", ""):
                    raise RuntimeError(f"oracle dependency differs from pinned graph: {path}")
                dependencies[path] = {k: module[k] for k in ("Version", "Sum", "GoModSum") if k in module}
        packages = json_stream(run(["go", "list", "-deps", "-json", "."], cwd=helper, env=env))
        for package in packages:
            if package["ImportPath"].startswith(MODULE + "/"):
                if not Path(package["Dir"]).resolve().is_relative_to(oracle.resolve()):
                    raise RuntimeError("oracle package source escaped pinned snapshot")
        binary = root / ("sqlite-oracle.exe" if os.name == "nt" else "sqlite-oracle")
        run(["go", "build", "-trimpath", "-o", str(binary), "."], cwd=helper, env=env, timeout=300)
        started = int(time.time())
        report = json.loads(run([str(binary)], cwd=helper, env=env, timeout=30))
        report["capture_interval"] = [started, int(time.time())]
        validate(report)
        if report["oracle"]["go_version"] != TOOLCHAIN:
            raise RuntimeError("runtime toolchain identity differs")
        report["oracle"].update({"commit": ORACLE_COMMIT,
                                 "source_hashes": {p: sha(b) for p, b in source.items()},
                                 "artifact_hashes": {p: sha(b) for p, b in helpers.items()},
                                 "dependencies": dependencies,
                                 "isolation": {"locale": "C", "timezone": "UTC",
                                               "umask": "0077" if os.name != "nt" else "not-applicable",
                                               "os_sandbox": False}})
    if helper_snapshot() != helpers:
        raise RuntimeError("helper source changed during capture; retry after writers finish")
    return report


def validate(report: dict) -> None:
    cases = report.get("cases")
    if not isinstance(cases, list) or [c.get("id") for c in cases] != EXPECTED_IDS:
        raise ValueError("case IDs/order mismatch")
    if not all(c.get("success") is True for c in cases):
        raise ValueError("unsuccessful oracle case")
    if report.get("oracle", {}).get("go_version") != TOOLCHAIN:
        raise ValueError("wrong runtime toolchain")
    connections = cases[1]["state"]["connections"]
    if len(connections) != 5 or any(c != {"journal_mode": "wal", "foreign_keys": 1,
                                         "busy_timeout": 5000} for c in connections):
        raise ValueError("unexpected connection policy")
    contention = cases[1]["state"]["contention"]
    if any(contention.get(key) is not True for key in ("observed", "blocked", "within_busy_timeout", "reader_succeeded", "tx_exec_succeeded", "rollback_succeeded")):
        raise ValueError("contention not demonstrated")
    expected = {"exec_failure": "failed to execute migration", "insert_failure": "failed to record migration",
                "closed_db": "failed to create schema_migrations table", "missing_directory": "failed to read migrations directory",
                "version_query": "failed to check migration state", "read_file": "failed to read migration"}
    negatives = [n for c in cases for n in c.get("negative", [])]
    if len(negatives) != len(expected) or {n["name"] for n in negatives} != set(expected):
        raise ValueError("negative corpus mismatch")
    for negative in negatives:
        prefix = expected[negative["name"]]
        actual = negative.get("error", "")
        if not actual.startswith(prefix) or ": " not in actual:
            raise ValueError("missing actual error context/cause")
        if negative["name"] in {"exec_failure", "insert_failure"} and negative.get("rolled_back") is not True:
            raise ValueError("rollback not demonstrated")
    if any(cases[4]["state"].get(key) is not True for key in ("rollback_probe_absent", "insert_migration_absent")):
        raise ValueError("rollback state differs")
    for case in cases[2:4]:
        state = case["state"]
        if state["migration_count"] != 2 or state["versions"] != ["001_test", "002_index"]:
            raise ValueError("migration state differs")
        if len(state["schema"]) != 3 or any(not row.get("sql") for row in state["schema"]):
            raise ValueError("missing schema SQL")
        if state.get("large_integer") != 9007199254740993 or state.get("null_value", False) is not None:
            raise ValueError("integer/NULL observations differ")
    repeated = cases[3]["state"]
    for key in ("rows_unchanged", "versions_unchanged", "schema_unchanged", "applied_at_unchanged", "replacement_error_nil"):
        if repeated.get(key) is not True:
            raise ValueError("idempotence not demonstrated")
    if repeated.get("replacement_read_attempts") != 0:
        raise ValueError("applied migration was read again")
    partial = cases[4]["state"]["partial_rerun"]
    for key in ("first_table_unchanged", "first_version_unchanged", "first_data_unchanged", "failed_version_absent", "rerun_succeeded"):
        if partial.get(key) is not True:
            raise ValueError("partial migration preservation failed")
    if cases[5]["state"].get("in_memory_success") is not True:
        raise ValueError("in-memory migration failed")


def compare(expected: dict, actual: dict) -> None:
    validate(expected)
    validate(actual)
    if comparable(expected) != comparable(actual):
        raise ValueError("fixture drift (including source/dependency provenance)")


def comparable(report: dict) -> dict:
    """Compare dynamic SQLite defaults by validated creation-window semantics.

    Only SQL-003/004 applied_at and created_at are dynamic. Preserve every
    other value, including all source identities and idempotence observations.
    Raw timestamps stay in the retained report; no synthetic capture is saved.
    """
    result = copy.deepcopy(report)
    start, end = result.pop("capture_interval")
    if type(start) is not int or type(end) is not int or not 0 <= end - start <= 30:
        raise ValueError("invalid capture interval")
    for case in result["cases"][2:4]:
        state = case["state"]
        timestamps = list(state["applied_at"]) + [r["created_at"] for r in state["data"]]
        if len(state["applied_at"]) != state["migration_count"]:
            raise ValueError("missing application timestamp")
        for value in timestamps:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo != timezone.utc or not start <= parsed.timestamp() <= end:
                raise ValueError("SQLite timestamp outside real capture window")
        state["applied_at"] = ["<validated-creation-time>" for _ in state["applied_at"]]
        for row in state["data"]:
            row["created_at"] = "<validated-creation-time>"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    report = capture()
    comparable(report)
    if args.check:
        compare(json.loads(args.output.read_bytes()), report)
        print("PASS SQLite oracle capture and provenance (6 contract groups; host only)")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        print(f"WROTE {args.output}")


if __name__ == "__main__":
    main()
