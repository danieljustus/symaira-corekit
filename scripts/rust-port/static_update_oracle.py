#!/usr/bin/env python3
"""Capture immutable Go update observations and replay static native slices."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "testdata/rust-port/fixtures/update/static-v1"
INDEX = FIXTURE_ROOT / "index.json"
GO_VERSION_REQUIRED = "go1.26.6"

LANES = {
    "version": {
        "command": ["go", "run", "./scripts/rust-port/update-oracle"],
        "oracle_path": "scripts/rust-port/update-oracle/main.go",
        "package_paths": ["updatecheck"],
        "runner_path": "scripts/rust-port/update-version-differential.py",
        "rust_path": "rust/symaira-core-update/tests/parity.rs",
        "historical_fixture": "testdata/rust-port/fixtures/update/stable-versions.json",
        "count": 30,
        "case_prefix": "stable-version",
        "rust_target": "parity",
        "rust_test": "stable_release_decisions_match_public_go_checker",
        "fixture_env": "UPDATE_VERSION_FIXTURE",
        "positive_tests": 1,
        "case_id_path": "cases[].id",
    },
    "response": {
        "command": ["go", "run", "./scripts/rust-port/update-response-oracle"],
        "oracle_path": "scripts/rust-port/update-response-oracle/main.go",
        "package_paths": ["updatecheck"],
        "runner_path": "scripts/rust-port/update-response-differential.py",
        "rust_path": "rust/symaira-core-update/tests/response.rs",
        "historical_fixture": "testdata/rust-port/fixtures/update/responses.json",
        "count": 9,
        "rust_target": "response",
        "rust_test": "release_response_outcomes_match_go_checker",
        "fixture_env": "RESPONSE_FIXTURE",
        "positive_tests": 1,
        "case_id_path": "cases[].id",
    },
    "install-method": {
        "command": ["go", "run", "./scripts/rust-port/install-method-oracle"],
        "oracle_path": "scripts/rust-port/install-method-oracle/main.go",
        "package_paths": ["updatecheck/installmethod"],
        "runner_path": "scripts/rust-port/install-method-differential.py",
        "rust_path": "rust/symaira-core-update/tests/install_method.rs",
        "historical_fixture": "testdata/rust-port/fixtures/update/install-methods.json",
        "count": 15,
        "rust_target": "install_method",
        "rust_test": "install_method_observations_match_go_api",
        "fixture_env": "INSTALL_METHOD_FIXTURE",
        "positive_tests": 1,
        "case_id_path": "cases[].id",
    },
    "extract": {
        "command": ["go", "run", "./scripts/rust-port/update-extract-oracle"],
        "oracle_path": "scripts/rust-port/update-extract-oracle/main.go",
        "package_paths": ["updatecheck/extract"],
        "runner_path": "scripts/rust-port/update-extract-differential.py",
        "rust_path": "rust/symaira-core-update/tests/extract.rs",
        "historical_fixture": "testdata/rust-port/fixtures/update/extract.json",
        "count": 12,
        "rust_target": "extract",
        "rust_test": "extraction_matches_go_archives_and_filesystem_observations",
        "fixture_env": "EXTRACT_FIXTURE",
        "positive_tests": 2,
        "case_id_path": "cases[].id",
    },
    "swap": {
        "command": ["go", "test", "-count=1", "-run", "^TestAtomicSwapOracle$", "./updatecheck/updateapply"],
        "oracle_path": "updatecheck/updateapply/atomic_swap_oracle_test.go",
        "package_paths": ["updatecheck/updateapply"],
        "runner_path": "scripts/rust-port/update-swap-differential.py",
        "rust_path": "rust/symaira-core-update/tests/swap.rs",
        "historical_fixture": "testdata/rust-port/fixtures/update/swap.json",
        "count": 8,
        "expected_case_ids": [
            "missing-source",
            "validation-rollback",
            "validation-first-install",
            "preexisting-backup",
            "validation-rollback-failed",
            "validation-remove-failed",
            "validation-remove-failed-existing",
            "backup-cleanup-failed",
        ],
        "rust_target": "swap",
        "rust_test": "atomic_swap_failure_and_rollback_match_go",
        "fixture_env": "UPDATE_SWAP_FIXTURE",
        "positive_tests": 1,
        "case_id_path": "cases[].input.id",
    },
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _within_root(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError(f"path must be inside assigned worktree: {path}")
    return resolved


def _native_target() -> tuple[str, str]:
    system = platform.system().lower()
    goos = {"darwin": "darwin", "linux": "linux", "windows": "windows"}.get(system)
    machine = platform.machine().lower()
    goarch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64", "amd64": "amd64"}.get(machine)
    if not goos or not goarch:
        raise ValueError(f"unsupported native Go target: {system}/{machine}")
    return goos, goarch


def fixture_path(lane: str, *, root: Path = ROOT, target: tuple[str, str] | None = None) -> Path:
    if lane not in LANES:
        raise ValueError(f"unsupported static update lane: {lane}")
    goos, goarch = target or _native_target()
    return root / "testdata/rust-port/fixtures/update/static-v1" / f"{goos}-{goarch}" / f"{lane}.json"


def _case_ids(lane: str, payload: dict) -> list[str]:
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"{lane} capture must contain a cases array")
    if lane == "swap":
        return [str(case.get("input", {}).get("id", "")) for case in cases]
    return [str(case.get("id", "")) for case in cases]


def _case_fingerprints(lane: str, payload: dict) -> list[str]:
    return [sha256(canonical_json(case)) for case in payload["cases"]]


def _source_paths(lane: str) -> list[str]:
    spec = LANES[lane]
    paths = ["go.mod", "go.sum", spec["runner_path"], spec["oracle_path"]]
    for package_path in ("updatecheck", "fsutil"):
        directory = ROOT / package_path
        paths.extend(
            path.relative_to(ROOT).as_posix()
            for path in sorted(directory.rglob("*.go"))
            if path.is_file() and (lane == "swap" or not path.name.endswith("_test.go"))
        )
    return sorted(set(paths))


def _capture_inputs(lane: str) -> dict[str, str]:
    result = {}
    for relative in _source_paths(lane):
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(f"missing Go oracle input during explicit capture: {relative}")
        result[relative] = sha256(path.read_bytes())
    return result


def _git_state() -> tuple[str, list[str]]:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    paths = []
    for line in status.splitlines():
        value = line[3:] if len(line) > 3 else ""
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.append(value)
    return head, sorted(paths)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_go_identity(env: dict[str, str], evidence: Path) -> tuple[str, str, str, dict]:
    version = subprocess.run(["go", "version"], cwd=ROOT, env=env, capture_output=True, check=False)
    (evidence / "go-version.stdout.bin").write_bytes(version.stdout)
    (evidence / "go-version.stderr.bin").write_bytes(version.stderr)
    if version.returncode != 0:
        raise RuntimeError(f"go version failed with {version.returncode}; raw output retained in {evidence}")
    version_text = version.stdout.decode("utf-8", "replace").strip()
    goenv = subprocess.run(["go", "env", "GOOS", "GOARCH", "GOMODCACHE"], cwd=ROOT, env=env, capture_output=True, check=False)
    (evidence / "go-env.stdout.bin").write_bytes(goenv.stdout)
    (evidence / "go-env.stderr.bin").write_bytes(goenv.stderr)
    if goenv.returncode != 0:
        raise RuntimeError(f"go env failed with {goenv.returncode}; raw output retained in {evidence}")
    values = goenv.stdout.decode("utf-8", "replace").splitlines()
    if len(values) != 3:
        raise RuntimeError(f"unexpected go env identity output; raw output retained in {evidence}")
    goos, goarch, gomodcache = values
    expected = f"go version {GO_VERSION_REQUIRED} {goos}/{goarch}"
    if version_text != expected:
        raise RuntimeError(f"pinned Go identity mismatch: got {version_text!r}, expected {expected!r}")
    if (goos, goarch) != _native_target():
        raise RuntimeError(f"Go execution is not native: got {goos}/{goarch}, expected {_native_target()[0]}/{_native_target()[1]}")
    if not Path(gomodcache).is_dir():
        raise RuntimeError(f"existing Go module cache is unavailable: {gomodcache}")
    return version_text, goos, goarch, {"gomodcache": gomodcache, "goenv_sha256": sha256(goenv.stdout)}


def _stage_go_source(lane: str, scratch: Path) -> Path:
    module_root = scratch / "go-root"
    module_root.mkdir(parents=True)
    shutil.copy2(ROOT / "go.mod", module_root / "go.mod")
    shutil.copy2(ROOT / "go.sum", module_root / "go.sum")
    shutil.copytree(ROOT / "updatecheck", module_root / "updatecheck")
    shutil.copytree(ROOT / "fsutil", module_root / "fsutil")
    oracle_dir = Path(LANES[lane]["oracle_path"]).parent
    if str(oracle_dir).startswith("updatecheck/"):
        return module_root
    shutil.copytree(ROOT / oracle_dir, module_root / oracle_dir)
    return module_root


def _run_bounded(command: list[str], env: dict[str, str], cwd: Path, evidence: Path) -> dict:
    stdout_path = evidence / "stdout.bin"
    stderr_path = evidence / "stderr.bin"
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=(os.name != "nt"),
            creationflags=creationflags,
        )
        timed_out = False
        try:
            code = proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name != "nt":
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            else:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    proc.kill()
                proc.wait(timeout=5)
            code = proc.returncode
    stdout = stdout_path.read_bytes()
    stderr = stderr_path.read_bytes()
    return {
        "argv": command,
        "cwd": "isolated-go-root",
        "exit_code": code,
        "timed_out": timed_out,
        "stdout": {"path": stdout_path.name, "bytes": len(stdout), "sha256": sha256(stdout)},
        "stderr": {"path": stderr_path.name, "bytes": len(stderr), "sha256": sha256(stderr)},
    }


def capture_go(lane: str, artifacts_dir: Path) -> tuple[dict, dict, str]:
    if os.environ.get("GO_ORACLE") != "1":
        raise RuntimeError("fresh Go execution requires explicit GO_ORACLE=1")
    if lane not in LANES:
        raise ValueError(f"no Go capture producer exists for lane {lane}")
    raw_parent = _within_root(artifacts_dir)
    raw_parent.mkdir(parents=True, exist_ok=True)
    run_id = f"{lane}-{uuid.uuid4().hex[:12]}"
    evidence = raw_parent / run_id
    evidence.mkdir()
    evidence_id = evidence.relative_to(ROOT).as_posix()
    scratch = ROOT / "target/static-update-go-work" / run_id
    scratch.mkdir(parents=True, exist_ok=False)
    tmpdir = ROOT / "target/static-update-tmp"
    gocache = ROOT / "target/static-update-go-cache"
    tmpdir.mkdir(parents=True, exist_ok=True)
    gocache.mkdir(parents=True, exist_ok=True)
    base_env = dict(os.environ)
    base_env.update({
        "GOTOOLCHAIN": GO_VERSION_REQUIRED,
        "GOPROXY": "off",
        "GOSUMDB": "off",
        "GOFLAGS": "-mod=readonly",
        "CGO_ENABLED": "0",
        "GOCACHE": str(gocache),
        "TMPDIR": str(tmpdir),
    })
    version_text, goos, goarch, go_environment = _read_go_identity(base_env, evidence)
    source_commit, dirty_paths = _git_state()
    inputs_before = _capture_inputs(lane)
    historical_path = ROOT / LANES[lane]["historical_fixture"]
    historical = {"path": historical_path.relative_to(ROOT).as_posix(), "sha256": sha256(historical_path.read_bytes())}
    spec = LANES[lane]
    module_root = _stage_go_source(lane, scratch)
    env = dict(base_env)
    env["GOMODCACHE"] = go_environment["gomodcache"]
    command = list(spec["command"])
    observation_file = None
    if lane == "swap":
        observation_file = evidence / "observation.json"
        env["COREKIT_SWAP_ORACLE_OUT"] = str(observation_file)
    command_record = _run_bounded(command, env, module_root, evidence)
    raw_stdout = (evidence / "stdout.bin").read_bytes()
    raw_stderr = (evidence / "stderr.bin").read_bytes()
    if command_record["timed_out"] or command_record["exit_code"] != 0:
        _write_json(evidence / "run.json", {"lane": lane, "command": command_record, "version": version_text, "target": {"goos": goos, "goarch": goarch}, "source_commit": source_commit, "dirty_paths": dirty_paths, "source_sha256": inputs_before, "historical_fixture": historical})
        raise RuntimeError(f"Go {lane} oracle failed (exit={command_record['exit_code']}, timed_out={command_record['timed_out']}); raw logs retained at {evidence_id}")
    observation_bytes = observation_file.read_bytes() if observation_file else raw_stdout
    (evidence / "observation.bin").write_bytes(observation_bytes)
    raw_observation = {
        "evidence_id": evidence_id,
        "stdout_sha256": sha256(raw_stdout),
        "stderr_sha256": sha256(raw_stderr),
        "observation_sha256": sha256(observation_bytes),
        "observation_bytes": len(observation_bytes),
        "exit_code": command_record["exit_code"],
        "timed_out": command_record["timed_out"],
    }
    run_base = {
        "lane": lane,
        "command": command_record,
        "go": {"version": version_text, "goos": goos, "goarch": goarch},
        "source_commit": source_commit,
        "working_tree_clean": not bool(dirty_paths),
        "dirty_paths": dirty_paths,
        "source_sha256": inputs_before,
        "historical_fixture": historical,
        "raw": raw_observation,
    }
    raw_payload = json.loads(observation_bytes)
    if lane == "version":
        if not isinstance(raw_payload, list):
            _write_json(evidence / "run.json", {**run_base, "observation_error": "version oracle output must be a JSON array"})
            raise ValueError("version oracle output must be a JSON array")
        cases = [dict(case, id=f"stable-version-{i + 1:03d}") for i, case in enumerate(raw_payload)]
    elif isinstance(raw_payload, list):
        cases = raw_payload
    elif isinstance(raw_payload, dict):
        cases = raw_payload.get("cases")
    else:
        cases = None
    if not isinstance(cases, list):
        _write_json(evidence / "run.json", {**run_base, "observation_error": f"Go {lane} oracle output must contain a cases array"})
        raise ValueError(f"Go {lane} oracle output must contain a cases array")
    ids = _case_ids(lane, {"cases": cases})
    inventory = {"expected_count": spec["count"], "executed_count": len(cases), "executed_ids": ids}
    if len(cases) != spec["count"]:
        _write_json(evidence / "run.json", {**run_base, "case_inventory": inventory})
        raise ValueError(f"Go {lane} oracle executed {len(cases)} cases; expected {spec['count']}")
    if any(not item for item in ids) or len(set(ids)) != len(ids):
        _write_json(evidence / "run.json", {**run_base, "case_inventory": inventory, "observation_error": "case IDs are missing or duplicated"})
        raise ValueError(f"Go {lane} oracle case IDs are missing or duplicated")
    expected_ids = spec.get("expected_case_ids")
    if expected_ids is not None and ids != expected_ids:
        inventory["required_ids"] = expected_ids
        _write_json(evidence / "run.json", {**run_base, "case_inventory": inventory, "observation_error": "case ID inventory differs"})
        raise ValueError(f"Go {lane} oracle case ID inventory differs: executed={ids}; required={expected_ids}")
    input_archives = []
    if lane == "extract":
        source_copy = module_root / "scripts/rust-port/update-extract-oracle/testdata"
        for case in cases:
            archive = source_copy / Path(case["archive"]).name
            data = archive.read_bytes()
            raw_file = evidence / "inputs" / f"{case['id']}{archive.suffix or '.bin'}"
            raw_file.parent.mkdir(parents=True, exist_ok=True)
            raw_file.write_bytes(data)
            input_archives.append({
                "case_id": case["id"],
                "source_path": case["archive"],
                "evidence_path": raw_file.relative_to(ROOT).as_posix(),
                "bytes": len(data),
                "sha256": sha256(data),
            })
    inputs_after = _capture_inputs(lane)
    if inputs_after != inputs_before:
        raise RuntimeError(f"Go source inputs changed during capture; raw output retained at {evidence_id}")
    harness_files = {
        "scripts/rust-port/static_update_oracle.py": sha256(Path(__file__).read_bytes()),
        "scripts/rust-port/update_static_runner.py": sha256((ROOT / "scripts/rust-port/update_static_runner.py").read_bytes()),
        spec["runner_path"]: sha256((ROOT / spec["runner_path"]).read_bytes()),
        spec["rust_path"]: sha256((ROOT / spec["rust_path"]).read_bytes()),
        "rust/symaira-core-update/tests/common/static_update.rs": sha256((ROOT / "rust/symaira-core-update/tests/common/static_update.rs").read_bytes()),
    }
    capture = {
        "capture_id": f"issue368-static-update-{run_id}",
        "capture_mode": "fresh-pinned-go-execution-additive-v1",
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source_commit": source_commit,
        "working_tree_clean": not bool(dirty_paths),
        "dirty_paths": dirty_paths,
        "go": {"version": version_text, "goos": goos, "goarch": goarch},
        "source_sha256": inputs_before,
        "source_manifest_sha256": sha256(canonical_json(inputs_before)),
        "harness_sha256": harness_files,
        "historical_fixture": historical,
        "case_count": len(cases),
        "case_ids": ids,
        "case_fingerprints_sha256": [sha256(canonical_json(case)) for case in cases],
        "input_archives": input_archives,
        "raw": {
            "evidence_id": evidence_id,
            "stdout_sha256": sha256(raw_stdout),
            "stderr_sha256": sha256(raw_stderr),
            "observation_sha256": sha256(observation_bytes),
            "observation_bytes": len(observation_bytes),
            "exit_code": command_record["exit_code"],
            "timed_out": command_record["timed_out"],
        },
        "command": command,
    }
    record = {"lane": lane, "schema_version": 1, "target": {"goos": goos, "goarch": goarch}, "capture": capture, "cases": cases}
    _write_json(evidence / "run.json", {"lane": lane, "command": command_record, "capture": capture})
    shutil.rmtree(scratch)
    return record, capture, evidence_id


def _case_input_fields(record: dict, target_dir: Path) -> None:
    if record["lane"] != "extract":
        return
    raw_by_id = {item["case_id"]: item for item in record["capture"]["input_archives"]}
    for case in record["cases"]:
        raw = raw_by_id[case["id"]]
        raw_path = _within_root(ROOT / raw["evidence_path"])
        data = raw_path.read_bytes()
        if len(data) != raw["bytes"] or sha256(data) != raw["sha256"]:
            raise ValueError(f"extract input archive evidence is corrupt for {case['id']}")
        filename = f"{case['id']}{Path(raw['source_path']).suffix or '.bin'}"
        archive_path = target_dir / "inputs" / filename
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        if archive_path.exists():
            raise FileExistsError(f"refusing to overwrite static archive input: {archive_path}")
        archive_path.write_bytes(data)
        case["input_archive_path"] = archive_path.relative_to(ROOT).as_posix()
        case["input_archive_sha256"] = raw["sha256"]
        raw["static_path"] = case["input_archive_path"]


def register(candidate: Path) -> dict:
    candidate = _within_root(candidate)
    record = json.loads(candidate.read_text(encoding="utf-8"))
    lane = record.get("lane")
    if lane not in LANES or record.get("schema_version") != 1:
        raise ValueError("candidate lane or schema_version is invalid")
    if not record["capture"].get("capture_id", "").startswith("issue368-static-update-"):
        raise ValueError("candidate does not carry fresh capture provenance")
    target = record["target"]
    expected_target = _native_target()
    if (target.get("goos"), target.get("goarch")) != expected_target:
        raise ValueError(f"candidate is not native {expected_target[0]}/{expected_target[1]}")
    dest = fixture_path(lane, target=expected_target)
    index = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {"schema_version": 1, "captures": {}}
    if lane in index["captures"] or dest.exists():
        raise FileExistsError(f"refusing to replace existing {lane} capture")
    evidence_root = _within_root(ROOT / record["capture"]["raw"]["evidence_id"])
    if not evidence_root.is_dir():
        raise FileNotFoundError(f"raw capture evidence is missing: {record['capture']['raw']['evidence_id']}")
    _case_input_fields(record, dest.parent)
    ids = _case_ids(lane, record)
    expected_ids = LANES[lane].get("expected_case_ids")
    if len(ids) != LANES[lane]["count"] or len(set(ids)) != len(ids) or (expected_ids is not None and ids != expected_ids):
        raise ValueError(f"candidate {lane} case inventory is invalid")
    record["capture"]["case_ids"] = ids
    record["capture"]["case_count"] = len(ids)
    record["capture"]["case_fingerprints_sha256"] = _case_fingerprints(lane, record)
    body = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError(f"refusing to overwrite {dest}")
    dest.write_bytes(body)
    summary = {
        "path": dest.relative_to(ROOT).as_posix(),
        "sha256": sha256(body),
        "target": target,
        "case_count": len(ids),
        "case_ids": ids,
        "source_commit": record["capture"]["source_commit"],
        "working_tree_clean": record["capture"]["working_tree_clean"],
        "raw_evidence_id": record["capture"]["raw"]["evidence_id"],
    }
    index["captures"][lane] = summary
    _write_json(INDEX, index)
    return summary


def validate_capture(lane: str, path: Path | None = None, *, root: Path = ROOT) -> dict:
    if lane not in LANES:
        raise ValueError(f"unsupported static update lane: {lane}")
    expected_target = _native_target()
    expected_path = fixture_path(lane, root=root, target=expected_target)
    selected = path or expected_path
    if selected.resolve() != expected_path.resolve():
        raise ValueError(f"capture path is not the native {expected_target[0]}/{expected_target[1]} slice")
    if not selected.is_file():
        raise ValueError(f"missing native {lane} Go capture for {expected_target[0]}/{expected_target[1]}: {selected}")
    index_path = root / "testdata/rust-port/fixtures/update/static-v1/index.json"
    if not index_path.is_file():
        raise ValueError(f"static update capture index missing: {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if type(index.get("schema_version")) is not int or index["schema_version"] != 1:
        raise ValueError("unsupported static update index schema")
    entry = index.get("captures", {}).get(lane)
    if not isinstance(entry, dict):
        raise ValueError(f"static update index has no {lane} capture")
    raw = selected.read_bytes()
    digest = sha256(raw)
    if entry.get("path") != selected.relative_to(root).as_posix() or entry.get("sha256") != digest:
        raise ValueError(f"static {lane} capture digest or path mismatch")
    record = json.loads(raw)
    if record.get("schema_version") != 1 or record.get("lane") != lane:
        raise ValueError(f"static {lane} capture identity mismatch")
    target = record.get("target")
    if not isinstance(target, dict) or (target.get("goos"), target.get("goarch")) != expected_target:
        raise ValueError(f"native platform identity mismatch for {lane}")
    capture = record.get("capture")
    if not isinstance(capture, dict) or capture.get("capture_mode") != "fresh-pinned-go-execution-additive-v1":
        raise ValueError(f"static {lane} capture provenance is absent")
    if type(capture.get("working_tree_clean")) is not bool:
        raise ValueError(f"static {lane} capture must record a boolean working_tree_clean value")
    if capture["working_tree_clean"] == bool(capture.get("dirty_paths")):
        raise ValueError(f"static {lane} clean/dirty provenance is inconsistent")
    go = capture.get("go")
    if not isinstance(go, dict) or go.get("version") != f"go version {GO_VERSION_REQUIRED} {expected_target[0]}/{expected_target[1]}":
        raise ValueError(f"static {lane} Go version or native identity mismatch")
    cases = record.get("cases")
    ids = _case_ids(lane, record)
    if not isinstance(cases, list) or len(cases) != LANES[lane]["count"] or len(ids) != len(cases) or len(set(ids)) != len(ids):
        raise ValueError(f"static {lane} case inventory is incomplete or duplicated")
    expected_ids = LANES[lane].get("expected_case_ids")
    if expected_ids is not None and ids != expected_ids:
        raise ValueError(f"static {lane} case IDs do not match the required inventory")
    if capture.get("case_count") != len(cases) or capture.get("case_ids") != ids:
        raise ValueError(f"static {lane} capture case IDs mismatch")
    if capture.get("case_fingerprints_sha256") != _case_fingerprints(lane, record):
        raise ValueError(f"static {lane} case fingerprint mismatch")
    source_map = capture.get("source_sha256")
    if not isinstance(source_map, dict) or not source_map:
        raise ValueError(f"static {lane} capture has no source identity")
    for name, checksum in source_map.items():
        if not isinstance(name, str) or not isinstance(checksum, str) or len(checksum) != 64:
            raise ValueError(f"static {lane} source digest is malformed")
    raw_meta = capture.get("raw")
    if not isinstance(raw_meta, dict) or raw_meta.get("exit_code") != 0 or raw_meta.get("timed_out") is not False:
        raise ValueError(f"static {lane} raw Go command did not complete successfully")
    for key in ("stdout_sha256", "stderr_sha256", "observation_sha256"):
        value = raw_meta.get(key)
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"static {lane} raw output digest is missing: {key}")
    for item in capture.get("input_archives", []):
        if not isinstance(item, dict) or item.get("case_id") not in ids:
            raise ValueError(f"static {lane} input archive inventory is invalid")
        relative = item.get("static_path")
        if not isinstance(relative, str):
            raise ValueError(f"static {lane} required native input is absent for {item.get('case_id')}")
        input_path = (root / relative).resolve()
        if not input_path.is_relative_to(root.resolve()) or not input_path.is_file():
            raise ValueError(f"static {lane} input escapes or is missing: {relative}")
        input_bytes = input_path.read_bytes()
        if len(input_bytes) != item.get("bytes") or sha256(input_bytes) != item.get("sha256"):
            raise ValueError(f"static {lane} input archive digest mismatch: {relative}")
    if entry.get("case_count") != len(cases) or entry.get("case_ids") != ids or entry.get("target") != target:
        raise ValueError(f"static {lane} index inventory mismatch")
    return record


def semantic_cases(record: dict) -> list[dict]:
    result = json.loads(json.dumps(record["cases"]))
    for case in result:
        case.pop("input_archive_path", None)
        case.pop("input_archive_sha256", None)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--lane", choices=sorted(LANES), required=True)
    capture_parser.add_argument("--output", type=Path, required=True)
    capture_parser.add_argument("--artifacts-dir", type=Path, required=True)
    register_parser = subparsers.add_parser("register")
    register_parser.add_argument("--candidate", type=Path, required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--lane", choices=sorted(LANES), required=True)
    args = parser.parse_args()
    if args.action == "capture":
        if os.environ.get("GO_ORACLE") != "1":
            parser.error("capture requires explicit GO_ORACLE=1")
        output = _within_root(args.output)
        if output.exists():
            raise FileExistsError(f"refusing to overwrite capture candidate: {output}")
        record, capture, evidence_id = capture_go(args.lane, args.artifacts_dir)
        _write_json(output, record)
        print(f"CAPTURE {args.lane} {capture['case_count']} {record['target']['goos']}/{record['target']['goarch']} candidate={output.relative_to(ROOT)} evidence={evidence_id}")
        return 0
    if args.action == "register":
        if os.environ.get("GO_ORACLE") != "1":
            parser.error("register requires explicit GO_ORACLE=1")
        result = register(args.candidate)
        print(f"REGISTERED {args.candidate} {result['case_count']} {result['target']['goos']}/{result['target']['goarch']} {result['sha256']}")
        return 0
    record = validate_capture(args.lane)
    print(f"PASS frozen Go {args.lane} capture: {record['capture']['case_count']} cases ({record['target']['goos']}/{record['target']['goarch']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
