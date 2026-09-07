#!/usr/bin/env python3
"""Run real paired Go/Rust consumer value measurements for RUST-005.

Every checkout, Cargo home, Go cache, and build target belongs to one
TemporaryDirectory. The script emits summaries plus the raw samples and
semantic output evidence required to independently recalculate every metric.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any, cast

from trust import assert_origin, checkout_for_record, safe_checkout_child, safe_workspace_path

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parents[2]
EVIDENCE = ROOT / "testdata/rust-port/adoption/evidence.json"
CANARIES = ROOT / "testdata/rust-port/cases/consumer-canaries.json"
DEFAULT_REPORT = ROOT / "testdata/rust-port/benchmarks/foundation.json"
COREKIT_REV = "27177f25f551cecefa7bd6c4524abf175b3a75c7"
REGRESSION_GATED_METRICS = (
    "binary_size_bytes",
    "startup_p95_ms",
    "peak_rss_median_bytes",
)


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(command: list[str], cwd: Path, env: dict[str, str], timeout: float = 900) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    if completed.returncode:
        stderr = completed.stderr.decode("utf-8", "replace").strip()
        fail(f"command failed ({completed.returncode}): {' '.join(command)}\n{stderr[-4000:]}")
    return completed


def archive_checkout(source: Path, revision: str, destination: Path, repository: str) -> None:
    """Archive only a trusted checkout with the expected origin."""
    if not source.is_dir():
        fail(f"checkout is not a directory: {source}")
    assert_origin(source, repository)
    destination.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(["git", "-C", str(source), "archive", "--format=tar", revision], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode:
        fail(f"cannot archive {source} at {revision}: {completed.stderr.decode('utf-8', 'replace')}")
    with tarfile.open(fileobj=__import__("io").BytesIO(completed.stdout), mode="r:") as archive:
        archive.extractall(destination, filter="data")


def isolated_env(root: Path, *, cargo_home: Path | None = None, go_cache: Path | None = None, go_mod_cache: Path | None = None, target: Path | None = None) -> dict[str, str]:
    home = root / "home"
    for path in (home, home / ".config", home / ".cache", home / ".local" / "share", home / ".local" / "state", root / "tmp"):
        path.mkdir(parents=True, exist_ok=True)
    env = {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_STATE_HOME": str(home / ".local" / "state"),
        "TMPDIR": str(root / "tmp"),
        "TMP": str(root / "tmp"),
        "TEMP": str(root / "tmp"),
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "NO_COLOR": "1",
        "PATH": os.environ.get("PATH", ""),
        "CGO_ENABLED": "0",
        "GOTOOLCHAIN": "local",
    }
    if cargo_home is not None:
        env["CARGO_HOME"] = str(cargo_home)
    if go_cache is not None:
        env["GOCACHE"] = str(go_cache)
    if go_mod_cache is not None:
        env["GOMODCACHE"] = str(go_mod_cache)
    if target is not None:
        env["CARGO_TARGET_DIR"] = str(target)
    return env


def parse_rss(stderr: bytes) -> int | None:
    text = stderr.decode("utf-8", "replace")
    # macOS /usr/bin/time -l reports bytes; GNU time -v reports KiB.
    for line in text.splitlines():
        if "maximum resident set size" in line:
            match = re.search(r"(\d+)\s+maximum resident set size", line)
            if match:
                return int(match.group(1))
        if "Maximum resident set size" in line and ":" in line:
            return int(line.split(":", 1)[1].strip().split()[0]) * 1024
    return None


def time_report_lines(stderr: bytes) -> list[str]:
    allowed = (
        "\t", "Command being timed:", "User time (seconds):", "System time (seconds):",
        "Percent of CPU this job got:", "Elapsed (wall clock) time:", "Average shared text size:",
        "Average unshared data size:", "Average stack size:", "Average total size:",
        "Maximum resident set size:", "Average resident set size:", "Major (requiring I/O) page faults:",
        "Minor (reclaiming a frame) page faults:", "Voluntary context switches:",
        "Involuntary context switches:", "Swaps:", "File system inputs:", "File system outputs:",
        "Socket messages sent:", "Socket messages received:", "Signals delivered:", "Page size (bytes):",
        "Exit status:", "real ", "user ", "sys ", "maximum resident set size",
    )
    mac_labels = r"(?:maximum resident set size|average shared memory size|average unshared memory size|average unshared data size|average unshared stack size|page reclaims|page faults|swaps|block input operations|block output operations|messages sent|messages received|signals received|voluntary context switches|involuntary context switches|instructions retired|cycles elapsed|peak memory footprint)"
    lines: list[str] = []
    for line in stderr.decode("utf-8", "replace").splitlines():
        if not line or line.startswith(allowed) or re.match(r"^\s*\d+(?:\.\d+)?\s+(?:real|user|sys)\b", line) or re.match(rf"^\s*\d+(?:\.\d+)?\s+{mac_labels}$", line):
            continue
        lines.append(line)
    return lines


def timed_launch(binary: Path, args: list[str], run_root: Path) -> dict[str, Any]:
    env = isolated_env(run_root)
    command = ["/usr/bin/time", "-l" if sys.platform == "darwin" else "-v", str(binary), *args]
    start = time.perf_counter_ns()
    completed = subprocess.run(command, cwd=run_root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
    if completed.returncode:
        fail(f"standalone command failed ({completed.returncode}): {binary} {' '.join(args)}\n{completed.stderr.decode('utf-8', 'replace')}")
    unexpected = time_report_lines(completed.stderr)
    if unexpected:
        fail(f"standalone command wrote unexpected stderr: {' | '.join(unexpected)}")
    rss = parse_rss(completed.stderr)
    if rss is None:
        fail("/usr/bin/time did not report maximum resident set size")
    return {
        "startup_ms": elapsed_ms,
        "rss_bytes": rss,
        "stdout": completed.stdout,
        "stderr": "",
        "exit_code": completed.returncode,
    }


def p95(values: list[float]) -> float:
    if not values:
        fail("cannot calculate p95 from no samples")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def median(values: list[float]) -> float:
    if not values:
        fail("cannot calculate median from no samples")
    return statistics.median(values)


def build_go(
    source: Path,
    output: Path,
    work_root: Path,
    record: dict[str, Any],
    *,
    go_mod_cache: Path | None = None,
) -> str:
    env = isolated_env(
        work_root,
        go_cache=work_root / "go-cache",
        go_mod_cache=go_mod_cache or (work_root / "go-mod-cache"),
    )
    command = ["go", "build", "-p=1", "-trimpath", "-o", str(output)]
    ldflags = record.get("go_ldflags")
    if ldflags is not None:
        if not isinstance(ldflags, str) or not ldflags.startswith("-X main."):
            fail(f"{record.get('repository')}: invalid Go version ldflags")
        command.extend(["-ldflags", ldflags])
    if (source / "cmd" / "symeraseme" / "main.go").is_file():
        command.append("./cmd/symeraseme")
    else:
        command.append(".")
    run(command, source, env)
    output.chmod(output.stat().st_mode | 0o111)
    return "CGO_ENABLED=0 GOTOOLCHAIN=local " + " ".join(command)


def cargo_binary_name(source: Path, record: dict[str, Any]) -> str:
    name = record.get("rust_binary")
    if not isinstance(name, str) or not name:
        fail(f"{record.get('repository')}: missing rust_binary")
    return cast(str, name)


def build_rust(
    source: Path,
    output: Path,
    work_root: Path,
    record: dict[str, Any],
    *,
    cargo_home: Path | None = None,
    target: Path | None = None,
) -> str:
    target = target or (work_root / "cargo-target")
    cargo_home = cargo_home or (work_root / "cargo-home")
    env = isolated_env(work_root, cargo_home=cargo_home, target=target)
    env["CARGO_BUILD_JOBS"] = "1"
    binary_name = cargo_binary_name(source, record)
    command = ["cargo", "build", "--release", "--locked", "--bin", binary_name]
    run(command, source, env, timeout=1800)
    built = target / "release" / (binary_name + (".exe" if os.name == "nt" else ""))
    if not built.is_file():
        fail(f"Rust build did not produce {built}")
    shutil.copy2(built, output)
    output.chmod(output.stat().st_mode | 0o111)
    return "CARGO_TARGET_DIR=<benchmark-target> CARGO_HOME=<benchmark-cargo-home> " + " ".join(command)


def build_distribution(kind: str, source: Path, root: Path, record: dict[str, Any], runs: int) -> dict[str, Any]:
    clean: list[float] = []
    warm: list[float] = []
    shared_mod_cache = root / f"{kind}-mod-cache"
    shared_cargo_home = root / f"{kind}-cargo-home"
    for index in range(runs):
        target = root / f"{kind}-clean-target-{index}"
        output = root / f"{kind}-clean-{index}"
        target.mkdir(parents=True)
        build_root = root / f"{kind}-clean-root-{index}"
        started = time.perf_counter_ns()
        if kind == "go":
            build_go(source, output, build_root, record, go_mod_cache=shared_mod_cache)
        else:
            build_rust(source, output, build_root, record, cargo_home=shared_cargo_home, target=target)
        clean.append((time.perf_counter_ns() - started) / 1_000_000)
        output.unlink(missing_ok=True)
        shutil.rmtree(target, ignore_errors=True)
        shutil.rmtree(build_root, ignore_errors=True)

    warm_root = root / f"{kind}-warm-root"
    warm_target = warm_root / "cargo-target"
    warm_cache = warm_root / "go-cache"
    warm_root.mkdir()
    for index in range(runs):
        output = warm_root / f"warm-{index}"
        started = time.perf_counter_ns()
        if kind == "go":
            env = isolated_env(warm_root, go_cache=warm_cache, go_mod_cache=shared_mod_cache)
            command = ["go", "build", "-p=1", "-trimpath", "-o", str(output), "./cmd/symeraseme" if (source / "cmd/symeraseme").is_dir() else "."]
            ldflags = record.get("go_ldflags")
            if ldflags is not None:
                package = command.pop()
                command.extend(["-ldflags", str(ldflags), package])
            run(command, source, env)
        else:
            env = isolated_env(warm_root, cargo_home=warm_root / "cargo-home", target=warm_target)
            env["CARGO_BUILD_JOBS"] = "1"
            run(["cargo", "build", "--release", "--locked", "--bin", cargo_binary_name(source, record)], source, env, timeout=1800)
        warm.append((time.perf_counter_ns() - started) / 1_000_000)
        output.unlink(missing_ok=True)
    result = {"runs": runs, "clean_ms": {"samples": clean, "median": median(clean), "p95": p95(clean)}, "warm_ms": {"samples": warm, "median": median(warm), "p95": p95(warm)}}
    shutil.rmtree(root, ignore_errors=True)
    return result


def candidate_binary(source: Path, record: dict[str, Any], root: Path, kind: str) -> tuple[Path, str]:
    output = root / f"{kind}-binary"
    if kind == "go":
        return output, build_go(source, output, root / "go-build", record)
    return output, build_rust(source, output, root / "rust-build", record)


def trusted_source(record: dict[str, Any], revisions: list[str], root: Path) -> Path:
    source, _disposable = checkout_for_record(record, revisions, root / "fetch")
    assert_origin(source, str(record["repository"]))
    for field in ("manifest_paths",):
        paths = record.get(field)
        if not isinstance(paths, list) or not paths:
            fail(f"{record['repository']}: {field} must be a non-empty array")
        for relative in paths:
            path = safe_checkout_child(source, relative, f"{record['repository']}.{field}")
            if not path.is_file():
                fail(f"{record['repository']}: {field} path is not a file: {relative}")
    duplicate = record.get("duplicate", {})
    if isinstance(duplicate, dict):
        source_paths = duplicate.get("source_paths", [])
        if not isinstance(source_paths, list):
            fail(f"{record['repository']}: duplicate source_paths must be an array")
        for relative in source_paths:
            path = safe_checkout_child(source, relative, f"{record['repository']}.duplicate.source_paths")
            if not path.is_file():
                fail(f"{record['repository']}: duplicate source path is not a file: {relative}")
    return source


def smoke(record: dict[str, Any], root: Path) -> dict[str, Any]:
    source_root = trusted_source(record, [record["adoption_commit"]], root)
    candidate = root / "candidate"
    archive_checkout(source_root, record["adoption_commit"], candidate, record["repository"])
    artifact, build_command = candidate_binary(candidate, record, root, "rust")
    commands: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    json_payload: dict[str, Any] | None = None
    for args in (["version"], ["version", "--json"]):
        env_root = root / ("smoke-" + "-".join(args).replace("/", "_"))
        env_root.mkdir()
        env = isolated_env(env_root)
        completed = subprocess.run([str(artifact), *args], cwd=env_root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
        if completed.returncode:
            fail(f"smoke failed for {record['repository']}: {artifact} {' '.join(args)}")
        stderr = completed.stderr.decode("utf-8", "replace")
        if stderr:
            fail(f"smoke wrote unexpected stderr for {record['repository']}: {stderr}")
        if args[-1] == "--json":
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError as error:
                fail(f"smoke JSON is invalid for {record['repository']}: {error}")
            if not isinstance(payload, dict) or any(key not in payload for key in ("tool", "version", "schema_version")):
                fail(f"smoke JSON lacks required semantic fields for {record['repository']}: {payload}")
            if record.get("tool") and payload.get("tool") != record["tool"]:
                fail(f"smoke tool mismatch for {record['repository']}: {payload}")
            json_payload = payload
        elif not completed.stdout.decode("utf-8", "replace").strip():
            fail(f"smoke text output is empty for {record['repository']}")
        encoded = base64.b64encode(completed.stdout).decode("ascii")
        results.append({
            "argv": args,
            "exit_code": completed.returncode,
            "stderr": stderr,
            "stdout_base64": encoded,
            "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
            "semantic": json_payload if args[-1] == "--json" else {"text": completed.stdout.decode("utf-8", "replace")},
        })
        commands.append({"argv": [str(artifact), *args]})
    if json_payload is None or results[0]["semantic"]["text"].strip() != f"{json_payload['tool']} {json_payload['version']}":
        fail(f"smoke text/JSON semantic outputs disagree for {record['repository']}")
    return {
        "repository": record["repository"],
        "candidate_commit": record["adoption_commit"],
        "passed": True,
        "artifact_kind": "benchmark-owned",
        "build_command": build_command,
        "commands": commands,
        "results": results,
    }


def semantic_version_output(output: bytes, expected_tool: str | None, label: str) -> dict[str, Any]:
    payload: Any = None
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as error:
        fail(f"{label}: version --json output is invalid: {error}")
    if not isinstance(payload, dict) or any(key not in payload for key in ("tool", "version", "schema_version")):
        fail(f"{label}: version payload lacks required tool/version/schema_version fields")
    if expected_tool and payload.get("tool") != expected_tool:
        fail(f"{label}: tool {payload.get('tool')!r} != expected {expected_tool!r}")
    return payload


def compare_semantics(go_sample: dict[str, Any], rust_sample: dict[str, Any], record: dict[str, Any], index: int) -> None:
    if go_sample["exit_code"] != rust_sample["exit_code"]:
        fail(f"{record['repository']} launch {index}: Go/Rust exit semantics differ")
    go_payload = semantic_version_output(go_sample["stdout"], record.get("tool"), f"{record['repository']} Go launch {index}")
    rust_payload = semantic_version_output(rust_sample["stdout"], record.get("tool"), f"{record['repository']} Rust launch {index}")
    if go_sample["stdout"] != rust_sample["stdout"]:
        fail(f"{record['repository']} launch {index}: Go/Rust stdout bytes differ; no canonicalization is authorized")
    if go_payload != rust_payload:
        fail(f"{record['repository']} launch {index}: Go/Rust semantic payloads differ")


def measure(record: dict[str, Any], runs: int, build_runs: int, root: Path) -> dict[str, Any]:
    source_root = trusted_source(record, [record["pre_adoption_commit"], record["adoption_commit"]], root)
    before = root / "before"
    after = root / "after"
    archive_checkout(source_root, record["pre_adoption_commit"], before, record["repository"])
    archive_checkout(source_root, record["adoption_commit"], after, record["repository"])
    go_binary, go_command = candidate_binary(before, record, root, "go")
    rust_binary, rust_command = candidate_binary(after, record, root, "rust")
    argv = record.get("version_argv", ["version", "--json"])
    if argv != ["version", "--json"]:
        fail(f"{record['repository']}: benchmark workload must be version --json")
    go_samples: list[dict[str, Any]] = []
    rust_samples: list[dict[str, Any]] = []
    go_output_bytes = b""
    rust_output_bytes = b""
    for index in range(runs):
        go_sample = timed_launch(go_binary, argv, root / f"go-run-{index}")
        rust_sample = timed_launch(rust_binary, argv, root / f"rust-run-{index}")
        compare_semantics(go_sample, rust_sample, record, index)
        go_output_bytes = go_sample["stdout"]
        rust_output_bytes = rust_sample["stdout"]
        go_samples.append({"startup_ms": go_sample["startup_ms"], "rss_bytes": go_sample["rss_bytes"], "stdout_sha256": hashlib.sha256(go_sample["stdout"]).hexdigest(), "exit_code": go_sample["exit_code"]})
        rust_samples.append({"startup_ms": rust_sample["startup_ms"], "rss_bytes": rust_sample["rss_bytes"], "stdout_sha256": hashlib.sha256(rust_sample["stdout"]).hexdigest(), "exit_code": rust_sample["exit_code"]})
    shutil.rmtree(root / "go-build", ignore_errors=True)
    shutil.rmtree(root / "rust-build", ignore_errors=True)
    go_build = build_distribution("go", before, root / "go-distribution", record, build_runs)
    rust_build = build_distribution("rust", after, root / "rust-distribution", record, build_runs)
    go_output = base64.b64encode(go_output_bytes).decode("ascii")
    rust_output = base64.b64encode(rust_output_bytes).decode("ascii")
    metrics = {
        "binary_size_bytes": {"baseline": go_binary.stat().st_size, "candidate": rust_binary.stat().st_size},
        "startup_p95_ms": {"baseline": p95([sample["startup_ms"] for sample in go_samples]), "candidate": p95([sample["startup_ms"] for sample in rust_samples])},
        "peak_rss_median_bytes": {"baseline": median([sample["rss_bytes"] for sample in go_samples]), "candidate": median([sample["rss_bytes"] for sample in rust_samples])},
        "clean_build_ms": {"baseline": median(go_build["clean_ms"]["samples"]), "candidate": median(rust_build["clean_ms"]["samples"])},
        "warm_build_ms": {"baseline": median(go_build["warm_ms"]["samples"]), "candidate": median(rust_build["warm_ms"]["samples"])},
    }
    ratios = {name: values["candidate"] / values["baseline"] for name, values in metrics.items()}
    return {
        "repository": record["repository"],
        "baseline_commit": record["pre_adoption_commit"],
        "candidate_commit": record["adoption_commit"],
        "workload": " ".join(argv),
        "runs": runs,
        "build_runs": build_runs,
        "build_commands": {"go": go_command, "rust": rust_command},
        "metrics": metrics,
        "ratios": ratios,
        "regression_gated_metrics": list(REGRESSION_GATED_METRICS),
        "maximum_regression_ratio": max(ratios[name] for name in REGRESSION_GATED_METRICS),
        "raw_samples": {
            "startup_ms": {"baseline": [sample["startup_ms"] for sample in go_samples], "candidate": [sample["startup_ms"] for sample in rust_samples]},
            "rss_bytes": {"baseline": [sample["rss_bytes"] for sample in go_samples], "candidate": [sample["rss_bytes"] for sample in rust_samples]},
            "clean_build_ms": {"baseline": go_build["clean_ms"]["samples"], "candidate": rust_build["clean_ms"]["samples"]},
            "warm_build_ms": {"baseline": go_build["warm_ms"]["samples"], "candidate": rust_build["warm_ms"]["samples"]},
            "launch_output_sha256": {"baseline": [sample["stdout_sha256"] for sample in go_samples], "candidate": [sample["stdout_sha256"] for sample in rust_samples]},
            "launch_exit_codes": {"baseline": [sample["exit_code"] for sample in go_samples], "candidate": [sample["exit_code"] for sample in rust_samples]},
            "launch_stderr": {"baseline": [""] * runs, "candidate": [""] * runs},
        },
        "workload_output": {
            "encoding": "base64",
            "baseline": go_output,
            "candidate": rust_output,
            "baseline_sha256": hashlib.sha256(base64.b64decode(go_output)).hexdigest(),
            "candidate_sha256": hashlib.sha256(base64.b64decode(rust_output)).hexdigest(),
            "comparison": "exact_stdout_bytes",
            "canonicalization_reason": None,
        },
        "raw_samples_retained": True,
        "note": "Startup p95, RSS median, and binary size enforce the 10% PERF-001 ceiling. Clean/warm build distributions are required/reporting under PERF-002 and do not use that ceiling.",
    }


def check_regressions(measurements: list[dict[str, Any]], ceiling: float = 1.1) -> list[str]:
    failures = []
    for measurement in measurements:
        if measurement["maximum_regression_ratio"] > ceiling:
            failures.append(f"{measurement['repository']}: maximum ratio {measurement['maximum_regression_ratio']:.4f} > {ceiling:.4f}")
    return failures


def tool_version(command: list[str]) -> str:
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    return completed.stdout.strip()


def report_label(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _finite_nonnegative(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < 0:
        fail(f"{label}: expected a finite non-negative number")
    return float(value)


def _raw_series(raw: dict[str, Any], name: str, side: str, count: int, label: str) -> list[float]:
    series = raw.get(name)
    if not isinstance(series, dict) or side not in series or not isinstance(series[side], list) or len(series[side]) != count:
        fail(f"{label}: {name}.{side} must contain exactly {count} raw samples")
    return [_finite_nonnegative(value, f"{label} {name}.{side}") for value in series[side]]


def validate_report(
    report: dict[str, Any],
    records: list[dict[str, Any]],
    configured: dict[str, dict[str, Any]],
    runs: int,
    build_runs: int,
) -> None:
    if runs != 50 or build_runs != 10:
        fail("RUST-005 requires exactly 50 launch and 10 clean/warm build samples")
    if report.get("schema_version") != 1 or report.get("suite") != "foundation":
        fail("benchmark report schema or suite mismatch")
    if report.get("status") != "passed" or report.get("failures"):
        fail("benchmark report does not record a passing value gate")
    provenance = report.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("corekit_revision") != COREKIT_REV:
        fail("benchmark report CoreKit provenance mismatch")
    toolchains = provenance.get("toolchains")
    if not isinstance(toolchains, dict) or any(not isinstance(toolchains.get(name), str) or not toolchains[name].strip() for name in ("go", "rustc", "cargo")):
        fail("benchmark report toolchain provenance is incomplete")
    expected_repositories = {record.get("repository") for record in records}
    if len(expected_repositories) != len(records) or any(not isinstance(repo, str) for repo in expected_repositories):
        fail("adoption consumer set must be unique")
    if set(configured) != expected_repositories:
        fail("consumer canary set does not exactly match adoption consumer set")
    measurements_value = report.get("measurements")
    if not isinstance(measurements_value, list) or {item.get("repository") for item in measurements_value if isinstance(item, dict)} != expected_repositories or len(measurements_value) != len(expected_repositories):
        fail("benchmark report consumer set is not exactly the adoption consumer set")
    seen: set[str] = set()
    required_metrics = {"binary_size_bytes", "startup_p95_ms", "peak_rss_median_bytes", "clean_build_ms", "warm_build_ms"}
    measurements = cast(list[dict[str, Any]], measurements_value)
    for measurement in measurements:
        if not isinstance(measurement, dict) or not isinstance(measurement.get("repository"), str):
            fail("benchmark report measurement must identify a consumer")
        repository = measurement["repository"]
        if repository in seen:
            fail(f"{repository}: duplicate benchmark measurement")
        seen.add(repository)
        record = next(record for record in records if record["repository"] == repository)
        canary = configured[repository]
        if measurement.get("baseline_commit") != record.get("pre_adoption_commit") or measurement.get("candidate_commit") != record.get("adoption_commit") or measurement.get("candidate_commit") != canary.get("adoption_commit"):
            fail(f"{repository}: benchmark commit provenance mismatch")
        if measurement.get("runs") != runs or measurement.get("build_runs") != build_runs or measurement.get("raw_samples_retained") is not True:
            fail(f"{repository}: benchmark run count/raw evidence mismatch")
        metrics = measurement.get("metrics")
        raw = measurement.get("raw_samples")
        if not isinstance(metrics, dict) or set(metrics) != required_metrics or not isinstance(raw, dict):
            fail(f"{repository}: required benchmark metrics/raw samples are missing")
        startup_baseline = _raw_series(raw, "startup_ms", "baseline", runs, repository)
        startup_candidate = _raw_series(raw, "startup_ms", "candidate", runs, repository)
        rss_baseline = _raw_series(raw, "rss_bytes", "baseline", runs, repository)
        rss_candidate = _raw_series(raw, "rss_bytes", "candidate", runs, repository)
        clean_baseline = _raw_series(raw, "clean_build_ms", "baseline", build_runs, repository)
        clean_candidate = _raw_series(raw, "clean_build_ms", "candidate", build_runs, repository)
        warm_baseline = _raw_series(raw, "warm_build_ms", "baseline", build_runs, repository)
        warm_candidate = _raw_series(raw, "warm_build_ms", "candidate", build_runs, repository)
        expected_summaries = {
            "startup_p95_ms": (p95(startup_baseline), p95(startup_candidate)),
            "peak_rss_median_bytes": (median(rss_baseline), median(rss_candidate)),
            "clean_build_ms": (median(clean_baseline), median(clean_candidate)),
            "warm_build_ms": (median(warm_baseline), median(warm_candidate)),
        }
        for name, values in metrics.items():
            if not isinstance(values, dict) or "baseline" not in values or "candidate" not in values:
                fail(f"{repository}: malformed metric {name}")
            baseline = _finite_nonnegative(values["baseline"], f"{repository} {name}.baseline")
            candidate = _finite_nonnegative(values["candidate"], f"{repository} {name}.candidate")
            if name in expected_summaries and (not math.isclose(baseline, expected_summaries[name][0], rel_tol=1e-12) or not math.isclose(candidate, expected_summaries[name][1], rel_tol=1e-12)):
                fail(f"{repository}: stale summary for {name}")
            if baseline <= 0:
                fail(f"{repository}: {name} baseline must be positive for ratio validation")
        output = measurement.get("workload_output")
        if not isinstance(output, dict) or output.get("encoding") != "base64" or output.get("comparison") != "exact_stdout_bytes" or output.get("canonicalization_reason") is not None:
            fail(f"{repository}: workload output evidence must authorize exact stdout comparison")
        try:
            baseline_bytes = base64.b64decode(output["baseline"], validate=True)
            candidate_bytes = base64.b64decode(output["candidate"], validate=True)
        except (KeyError, ValueError, TypeError):
            fail(f"{repository}: invalid workload output evidence")
        if baseline_bytes != candidate_bytes or hashlib.sha256(baseline_bytes).hexdigest() != output.get("baseline_sha256") or hashlib.sha256(candidate_bytes).hexdigest() != output.get("candidate_sha256"):
            fail(f"{repository}: workload output bytes/digests do not verify")
        payload = semantic_version_output(baseline_bytes, canary.get("tool"), repository)
        if payload != semantic_version_output(candidate_bytes, canary.get("tool"), f"{repository} candidate"):
            fail(f"{repository}: semantic output evidence differs")
        hashes = raw.get("launch_output_sha256")
        exits = raw.get("launch_exit_codes")
        stderr = raw.get("launch_stderr")
        if not isinstance(hashes, dict) or not isinstance(exits, dict) or not isinstance(stderr, dict):
            fail(f"{repository}: launch semantic raw evidence is missing")
        digest = hashlib.sha256(baseline_bytes).hexdigest()
        for side in ("baseline", "candidate"):
            if hashes.get(side) != [digest] * runs or exits.get(side) != [0] * runs or stderr.get(side) != [""] * runs:
                fail(f"{repository}: launch semantic raw evidence does not match output")
        ratios: dict[str, float] = {}
        for name, values in metrics.items():
            ratios[name] = float(values["candidate"]) / float(values["baseline"])
        recorded_ratios = measurement.get("ratios")
        if not isinstance(recorded_ratios, dict) or set(recorded_ratios) != required_metrics:
            fail(f"{repository}: ratios are incomplete")
        for name, ratio in ratios.items():
            if not math.isclose(_finite_nonnegative(recorded_ratios.get(name), f"{repository} ratio {name}"), ratio, rel_tol=1e-12):
                fail(f"{repository}: stale ratio for {name}")
        if measurement.get("regression_gated_metrics") != list(REGRESSION_GATED_METRICS):
            fail(f"{repository}: regression gate scope mismatch")
        maximum = max(ratios[name] for name in REGRESSION_GATED_METRICS)
        if not math.isclose(_finite_nonnegative(measurement.get("maximum_regression_ratio"), f"{repository} maximum ratio"), maximum, rel_tol=1e-12):
            fail(f"{repository}: stale maximum regression ratio")
    failures = check_regressions(measurements)
    if failures:
        fail("; ".join(failures))

    smokes = report.get("standalone_smokes")
    if not isinstance(smokes, list) or {entry.get("repository") for entry in smokes if isinstance(entry, dict)} != expected_repositories or len(smokes) != len(expected_repositories):
        fail("standalone smoke evidence consumer set is not exact")
    for smoke in smokes:
        if not isinstance(smoke, dict) or smoke.get("passed") is not True:
            fail("standalone smoke evidence is not a passing semantic record")
        repository = smoke.get("repository")
        record = next(record for record in records if record.get("repository") == repository)
        if smoke.get("candidate_commit") != record.get("adoption_commit"):
            fail(f"{repository}: smoke candidate commit mismatch")
        commands = smoke.get("commands")
        results = smoke.get("results")
        if not isinstance(commands, list) or not isinstance(results, list) or len(commands) != 2 or len(results) != 2:
            fail(f"{repository}: smoke text/JSON evidence is incomplete")
        text_output: str | None = None
        json_payload: dict[str, Any] | None = None
        for command, result in zip(commands, results, strict=True):
            argv = command.get("argv") if isinstance(command, dict) else None
            if not isinstance(argv, list) or not argv or not isinstance(argv[0], str) or not Path(argv[0]).is_absolute() or argv[1:] not in (["version"], ["version", "--json"]):
                fail(f"{repository}: smoke command is not an absolute artifact command")
            if not isinstance(result, dict) or result.get("exit_code") != 0 or result.get("stderr") not in ("", None):
                fail(f"{repository}: smoke result exit/stderr evidence failed")
            raw_output = base64.b64decode(result.get("stdout_base64", ""), validate=True)
            if hashlib.sha256(raw_output).hexdigest() != result.get("stdout_sha256"):
                fail(f"{repository}: smoke output digest mismatch")
            if argv[-1] == "--json":
                json_payload = semantic_version_output(raw_output, configured[repository].get("tool"), f"{repository} smoke")
            else:
                text_output = raw_output.decode("utf-8", "replace")
                if not text_output.strip():
                    fail(f"{repository}: smoke text output is empty")
        if json_payload is None or text_output is None or text_output.strip() != f"{json_payload['tool']} {json_payload['version']}":
            fail(f"{repository}: smoke text/JSON semantic outputs disagree")


def self_test() -> int:
    """Exercise report and trust-boundary negative controls without a benchmark."""
    import copy
    payload = b'{"tool":"sample","version":"1.0.0","schema_version":1}'
    text = b"sample 1.0.0\n"
    digest = hashlib.sha256(payload).hexdigest()
    records = [
        {"repository": "owner/one", "pre_adoption_commit": "1" * 40, "adoption_commit": "2" * 40},
        {"repository": "owner/two", "pre_adoption_commit": "3" * 40, "adoption_commit": "4" * 40},
    ]
    configured = {
        record["repository"]: {"repository": record["repository"], "adoption_commit": record["adoption_commit"], "tool": "sample"}
        for record in records
    }
    measurements = []
    smokes = []
    for record in records:
        raw = {
            "startup_ms": {"baseline": [1.0] * 50, "candidate": [1.0] * 50},
            "rss_bytes": {"baseline": [2.0] * 50, "candidate": [2.0] * 50},
            "clean_build_ms": {"baseline": [3.0] * 10, "candidate": [3.0] * 10},
            "warm_build_ms": {"baseline": [4.0] * 10, "candidate": [4.0] * 10},
            "launch_output_sha256": {"baseline": [digest] * 50, "candidate": [digest] * 50},
            "launch_exit_codes": {"baseline": [0] * 50, "candidate": [0] * 50},
            "launch_stderr": {"baseline": [""] * 50, "candidate": [""] * 50},
        }
        metrics = {
            "binary_size_bytes": {"baseline": 100, "candidate": 100},
            "startup_p95_ms": {"baseline": 1.0, "candidate": 1.0},
            "peak_rss_median_bytes": {"baseline": 2.0, "candidate": 2.0},
            "clean_build_ms": {"baseline": 3.0, "candidate": 3.0},
            "warm_build_ms": {"baseline": 4.0, "candidate": 4.0},
        }
        measurements.append({"repository": record["repository"], "baseline_commit": record["pre_adoption_commit"], "candidate_commit": record["adoption_commit"], "runs": 50, "build_runs": 10, "raw_samples_retained": True, "raw_samples": raw, "metrics": metrics, "ratios": {name: 1.0 for name in metrics}, "regression_gated_metrics": list(REGRESSION_GATED_METRICS), "maximum_regression_ratio": 1.0, "workload_output": {"encoding": "base64", "baseline": base64.b64encode(payload).decode(), "candidate": base64.b64encode(payload).decode(), "baseline_sha256": digest, "candidate_sha256": digest, "comparison": "exact_stdout_bytes", "canonicalization_reason": None}})
        smokes.append({"repository": record["repository"], "candidate_commit": record["adoption_commit"], "passed": True, "commands": [{"argv": ["/tmp/artifact", "version"]}, {"argv": ["/tmp/artifact", "version", "--json"]}], "results": [{"exit_code": 0, "stderr": "", "stdout_base64": base64.b64encode(text).decode(), "stdout_sha256": hashlib.sha256(text).hexdigest()}, {"exit_code": 0, "stderr": "", "stdout_base64": base64.b64encode(payload).decode(), "stdout_sha256": digest}]})
    report = {"schema_version": 1, "suite": "foundation", "status": "passed", "failures": [], "provenance": {"corekit_revision": COREKIT_REV, "toolchains": {"go": "go", "rustc": "rustc", "cargo": "cargo"}}, "measurements": measurements, "standalone_smokes": smokes}
    validate_report(report, records, configured, 50, 10)
    controls = []
    for label, mutate in (
        ("duplicate consumer", lambda value: value["measurements"].append(copy.deepcopy(value["measurements"][0]))),
        ("removed build metric", lambda value: value["measurements"][0]["metrics"].pop("clean_build_ms")),
        ("changed raw count", lambda value: value["measurements"][0]["raw_samples"]["startup_ms"]["baseline"].pop()),
        ("fake smoke command", lambda value: value["standalone_smokes"][0]["commands"][0]["argv"].__setitem__(0, "artifact")),
        ("modified report", lambda value: value["measurements"][0]["workload_output"].__setitem__("baseline_sha256", "0" * 64)),
    ):
        tampered = copy.deepcopy(report)
        mutate(tampered)
        try:
            validate_report(tampered, records, configured, 50, 10)
        except (RuntimeError, ValueError):
            controls.append(label)
    assert len(controls) == 5, controls
    with tempfile.TemporaryDirectory(prefix="rust005-trust-selftest-") as raw:
        root = Path(raw)
        try:
            safe_workspace_path("../escape")
        except ValueError:
            pass
        else:
            raise AssertionError("path traversal was accepted")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/wrong/repo.git"], cwd=root, check=True)
        try:
            assert_origin(root, "owner/repo")
        except (RuntimeError, ValueError):
            pass
        else:
            raise AssertionError("origin mismatch was accepted")
    print("PASS benchmark negative controls: " + ", ".join(controls))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["foundation", "consumers"])
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--build-runs", type=int, default=10)
    parser.add_argument("--smoke", action="store_true", help="build exact candidate checkouts and run standalone version commands only")
    parser.add_argument("--check", action="store_true", help="validate the tracked real report without rerunning measurements")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.suite is None:
        parser.error("--suite is required unless --self-test is used")
    if args.runs != 50 or args.build_runs != 10:
        parser.error("RUST-005 requires exactly --runs 50 and --build-runs 10")
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    canaries = json.loads(CANARIES.read_text(encoding="utf-8"))
    records = evidence.get("consumers", [])
    configured = {item["repository"]: item for item in canaries.get("consumers", [])}
    if not isinstance(records, list) or len(records) < 2:
        fail("at least two adoption records are required")
    report_path = args.report or (ROOT / "testdata/rust-port/benchmarks" / (f"{args.suite}-smoke.json" if args.smoke else f"{args.suite}.json"))
    if args.check:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        validate_report(report, records, configured, args.runs, args.build_runs)
        print(json.dumps({"status": "passed", "suite": args.suite, "consumers": len(records), "report": report_label(report_path)}, sort_keys=True))
        return 0
    with tempfile.TemporaryDirectory(prefix="rust005-bench-") as raw:
        root = Path(raw)
        smoke_records = [smoke({**record, **configured[record["repository"]]}, root / record["repository"].replace("/", "-")) for record in records]
        if args.smoke:
            report = {
                "schema_version": 1,
                "suite": args.suite,
                "status": "passed",
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "standalone_smokes": smoke_records,
                "provenance": {"corekit_revision": COREKIT_REV, "source": "local adoption checkouts", "raw_samples_retained": True, "toolchains": {"go": tool_version(["go", "version"]), "rustc": tool_version(["rustc", "--version"]), "cargo": tool_version(["cargo", "--version"])}},
            }
        else:
            measurements = []
            for record in records:
                merged = {**record, **configured[record["repository"]]}
                measurements.append(measure(merged, args.runs, args.build_runs, root / record["repository"].replace("/", "-")))
            failures = check_regressions(measurements)
            security_exception = evidence.get("security_exception")
            exception_approved = isinstance(security_exception, dict) and bool(security_exception.get("issue_url")) and security_exception.get("reviewed") is True
            if failures and exception_approved:
                failures = []
            report = {
                "schema_version": 1,
                "suite": args.suite,
                "status": "failed" if failures else "passed",
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "measurements": measurements,
                "standalone_smokes": smoke_records,
                "provenance": {
                    "corekit_revision": COREKIT_REV,
                    "host": {"os": sys.platform, "machine": os.uname().machine if hasattr(os, "uname") else os.name},
                    "toolchains": {"go": tool_version(["go", "version"]), "rustc": tool_version(["rustc", "--version"]), "cargo": tool_version(["cargo", "--version"])},
                    "raw_samples_retained": False,
                    "cleaned": True,
                    "commands": "bench.py builds archived pre-adoption and adoption commits with benchmark-owned Cargo/Go caches and targets",
                },
                "regression_ceiling": 1.1,
                "security_exception": security_exception,
                "failures": failures,
            }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "suite": args.suite, "consumers": len(records), "report": report_label(report_path)}, sort_keys=True))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(f"FAIL benchmark: {error}", file=sys.stderr)
        raise SystemExit(1)
