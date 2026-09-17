#!/usr/bin/env python3
"""Run and validate the frozen SQL-006 80-build consumer cost gate."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import plistlib
import signal
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = Path(__file__).with_name("sql006_cost_contract.json")
LIMIT = 1.1
COREKIT_URL = "https://github.com/danieljustus/symaira-corekit"


def fail(message: str) -> None:
    raise ValueError(message)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def load_contract() -> dict[str, Any]:
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or value.get("gate_id") != "SQL-006-80-BUILD":
        fail("invalid SQL-006 contract")
    if value.get("limit") != LIMIT or value.get("samples_per_cell") != 10:
        fail("SQL-006 contract limits changed")
    if len(value.get("consumers", [])) != 2 or value.get("modes") != ["clean", "warm"]:
        fail("SQL-006 contract matrix changed")
    return value


CONTRACT = load_contract()
STORAGE_ROOT = Path(CONTRACT["runtime"]["storage_root"]).resolve()
WORKSPACE = STORAGE_ROOT / "Repos"


def run(command: list[str], cwd: Path, env: dict[str, str], timeout: float = 1800) -> subprocess.CompletedProcess[bytes]:
    temp_root = env.get("TMPDIR")
    if not temp_root:
        fail("TMPDIR must be supplied for process capture")
    Path(temp_root).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=temp_root) as stdout, tempfile.TemporaryFile(dir=temp_root) as stderr:
        kwargs: dict[str, Any] = {"cwd": cwd, "env": env, "stdout": stdout, "stderr": stderr}
        if os.name != "nt":
            kwargs["start_new_session"] = True
        process = subprocess.Popen(command, **kwargs)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=10)
            raise TimeoutError(f"command timed out: {' '.join(command)}") from error
        stdout.seek(0)
        stderr.seek(0)
        out, err = stdout.read(), stderr.read()
    if process.returncode:
        fail(f"command failed ({process.returncode}): {' '.join(command)}\n{err.decode(errors='replace')[-4000:]}")
    return subprocess.CompletedProcess(command, process.returncode, out, err)


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        fail(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def origin_slug(value: str) -> str:
    remote = value.strip().rstrip("/")
    if remote.endswith(".git"):
        remote = remote[:-4]
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if remote.startswith(prefix):
            return remote.removeprefix(prefix)
    fail(f"unsupported consumer origin: {value}")


def consumer_checkout(item: dict[str, Any]) -> Path:
    checkout = under(WORKSPACE / item["checkout"], STORAGE_ROOT, f"{item['name']} checkout")
    if not checkout.is_dir() or checkout.is_symlink():
        fail(f"{item['name']}: checkout is unavailable or symlinked")
    if origin_slug(git("remote", "get-url", "origin", cwd=checkout)) != item["repository"]:
        fail(f"{item['name']}: origin mismatch")
    return checkout


def git_archive(checkout: Path, revision: str) -> bytes:
    result = subprocess.run(
        ["git", "archive", "--format=tar", revision], cwd=checkout,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        fail(f"cannot archive {checkout} at {revision}: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def hydrate_source(checkout: Path, revision: str, destination: Path) -> str:
    """Give source-bound consumer tests private, immutable Git history."""
    git("init", "--quiet", cwd=destination)
    git("remote", "add", "origin", str(checkout), cwd=destination)
    git("fetch", "--quiet", "--tags", "origin", cwd=destination)
    git("fetch", "--quiet", "origin", revision, cwd=destination)
    git("checkout", "--quiet", "--force", "--detach", revision, cwd=destination)
    head = git("rev-parse", "HEAD", cwd=destination)
    if head != revision or git("status", "--porcelain=v1", "--untracked-files=all", cwd=destination):
        fail("private source archive did not hydrate to the exact clean revision")
    return head


def expected_git_source(revision: str) -> str:
    return f"git+{COREKIT_URL}?rev={revision}#{revision}"


def named_dependency(value: Any, name: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        candidate = value.get(name)
        if isinstance(candidate, dict):
            return candidate
        for child in value.values():
            found = named_dependency(child, name)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = named_dependency(child, name)
            if found is not None:
                return found
    return None


def source_pins(source: Path, expected: str) -> dict[str, str]:
    manifest = tomllib.loads((source / "Cargo.toml").read_text(encoding="utf-8"))
    direct = named_dependency(manifest, "symaira-core-sqlite")
    if direct is None or direct.get("git") != COREKIT_URL or direct.get("rev") != expected:
        fail("Cargo.toml does not directly pin symaira-core-sqlite to the expected CoreKit revision")
    lock = tomllib.loads((source / "Cargo.lock").read_text(encoding="utf-8"))
    packages = lock.get("package")
    if not isinstance(packages, list):
        fail("Cargo.lock has no package list")
    found = {entry.get("name"): entry for entry in packages if isinstance(entry, dict) and entry.get("name") in {"symaira-core-sqlite", "symaira-core-fs"}}
    if set(found) != {"symaira-core-sqlite", "symaira-core-fs"}:
        fail("Cargo.lock lacks the CoreKit SQLite/FS packages")
    expected_source = expected_git_source(expected)
    if any(entry.get("source") != expected_source for entry in found.values()):
        fail("Cargo.lock CoreKit source/revision mismatch")
    dependencies = found["symaira-core-sqlite"].get("dependencies")
    if not isinstance(dependencies, list) or not any(isinstance(value, str) and value.split(" ", 1)[0] == "symaira-core-fs" for value in dependencies):
        fail("Cargo.lock does not bind symaira-core-fs beneath symaira-core-sqlite")
    return {"direct": expected, "symaira-core-sqlite": expected_source, "symaira-core-fs": expected_source}


def under(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve(strict=False)
    base = root.resolve(strict=False)
    try:
        resolved.relative_to(base)
    except ValueError as error:
        fail(f"{label} escapes its required root: {path}")
    return resolved


def disk_info(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["diskutil", "info", "-plist", str(path)], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        fail(f"diskutil cannot inspect {path}: {result.stderr.decode(errors='replace').strip()}")
    value = plistlib.loads(result.stdout)
    if not isinstance(value, dict):
        fail(f"diskutil returned invalid metadata for {path}")
    return value


def external_status() -> dict[str, Any]:
    helper = Path("/Users/daniel/.local/bin/dev-external")
    result = subprocess.run([str(helper), "--status"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        fail(f"dev-external --status failed: {result.stderr.decode(errors='replace').strip()}")
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or value.get("mounted") is not True:
        fail("dev-external does not confirm the NVMe mount")
    return value


def secure_runtime() -> tuple[Path, Path, Path, Path, Path, dict[str, Any]]:
    runtime_value = os.environ.get("NVME_RUNTIME")
    storage_value = os.environ.get("NVME_STORAGE")
    expected = CONTRACT["runtime"]
    if runtime_value != expected["runtime_mount"] or storage_value != expected["storage_root"]:
        fail("NVME_RUNTIME/NVME_STORAGE must match the frozen secure-runtime contract")
    runtime = Path(runtime_value)
    storage = Path(storage_value)
    if not runtime.is_dir() or not storage.is_dir():
        fail("secure runtime or NVMe storage is unavailable")
    runtime_stat = runtime.stat()
    if runtime_stat.st_uid != os.getuid() or runtime_stat.st_mode & 0o077:
        fail("secure runtime must not be group/other accessible")
    backing = under(storage / "BuildTargets" / "SymairaSecureRuntime.sparsebundle", storage, "secure runtime backing file")
    if not backing.exists():
        fail("secure runtime backing file is not on the frozen NVMe storage")
    if under(runtime, Path("/Volumes"), "secure runtime") != runtime.resolve():
        fail("secure runtime must be mounted directly below /Volumes")
    runtime_disk = disk_info(runtime)
    try:
        storage_mount = Path("/Volumes") / storage.relative_to("/Volumes").parts[0]
    except ValueError as error:
        raise ValueError("frozen NVMe storage is not mounted beneath /Volumes") from error
    storage_disk = disk_info(storage_mount)
    if runtime_disk.get("MountPoint") != str(runtime.resolve()) or runtime_disk.get("Internal") is not False or runtime_disk.get("GlobalPermissionsEnabled") is not True:
        fail("secure runtime mount/owners preflight failed")
    if storage_disk.get("Internal") is not False:
        fail("secure runtime backing storage is not external")
    free_bytes = runtime_disk.get("APFSContainerFree")
    if not isinstance(free_bytes, int) or free_bytes <= 0:
        fail("secure runtime has no free capacity")
    rustup_home = runtime / "runtime-bootstrap" / "rustup"
    toolchain_bin = rustup_home / "toolchains" / expected["toolchain"] / "bin"
    if not rustup_home.is_dir() or not (toolchain_bin / "cargo").is_file() or not (toolchain_bin / "rustc").is_file():
        fail("preprovisioned secure-runtime RUSTUP_HOME/toolchain is missing")
    under(rustup_home, runtime, "RUSTUP_HOME")
    go_bin = runtime / "runtime-bootstrap" / "go-home" / "sdk" / f"go{expected['go_toolchain']}" / "bin" / "go"
    if not go_bin.is_file():
        fail("preprovisioned secure-runtime Go oracle toolchain is missing")
    under(go_bin, runtime, "Go toolchain")
    return runtime.resolve(), storage.resolve(), rustup_home.resolve(), toolchain_bin.resolve(), go_bin.resolve(), {
        "dev_external": external_status(),
        "runtime_disk": {"mount_point": runtime_disk.get("MountPoint"), "owners_enabled": runtime_disk.get("GlobalPermissionsEnabled"), "internal": runtime_disk.get("Internal"), "free_bytes": free_bytes},
        "storage_disk": {"mount_point": storage_disk.get("MountPoint"), "internal": storage_disk.get("Internal")},
    }


def short_temp_root(runtime: Path, identity: Path) -> Path:
    # Unix-domain sockets have a short pathname limit; this remains private
    # and external while avoiding a deeply nested per-run path.
    return runtime / "t" / sha_bytes(str(identity).encode())[:12]


def isolated_env(root: Path, cargo_home: Path, target: Path, rustup_home: Path, toolchain_bin: Path, go_bin: Path) -> dict[str, str]:
    if os.environ.get("RUSTC_WRAPPER"):
        fail("RUSTC_WRAPPER must be unset for the SQL-006 gate")
    runtime = Path(CONTRACT["runtime"]["runtime_mount"])
    temp_root = short_temp_root(runtime, root)
    roots = {
        "HOME": root / "home", "USERPROFILE": root / "home",
        "XDG_CONFIG_HOME": root / "xdg" / "config", "XDG_CACHE_HOME": root / "xdg" / "cache",
        "XDG_DATA_HOME": root / "xdg" / "data", "XDG_STATE_HOME": root / "xdg" / "state",
        "TMPDIR": temp_root, "TMP": temp_root, "TEMP": temp_root,
        "CARGO_HOME": cargo_home, "CARGO_TARGET_DIR": target,
        "GOCACHE": root / "go-cache", "GOMODCACHE": root / "go-mod-cache", "GOPATH": root / "go",
    }
    for name, path in roots.items():
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
        under(path, runtime if name in {"TMPDIR", "TMP", "TEMP", "CARGO_HOME", "CARGO_TARGET_DIR"} else root, name)
    if not rustup_home.is_dir() or not (toolchain_bin / "cargo").is_file() or not (toolchain_bin / "rustc").is_file() or not go_bin.is_file():
        fail("external Rust/Go toolchain is not preprovisioned")
    under(rustup_home, runtime, "RUSTUP_HOME")
    under(toolchain_bin, rustup_home, "Rust toolchain")
    under(go_bin, runtime, "Go toolchain")
    home_sdk = roots["HOME"] / "sdk"
    go_sdk_root = go_bin.parent.parent.parent
    if home_sdk.exists() or home_sdk.is_symlink():
        if home_sdk.resolve() != go_sdk_root.resolve():
            fail("HOME/sdk does not point to the external Go toolchain")
    else:
        home_sdk.symlink_to(go_sdk_root, target_is_directory=True)
    under(home_sdk, runtime, "HOME/sdk")
    env = {key: str(value) for key, value in roots.items()}
    env["RUSTUP_HOME"] = str(rustup_home)
    env.update({
        "PATH": str(toolchain_bin) + os.pathsep + str(go_bin.parent) + os.pathsep + os.environ.get("PATH", ""),
        "RUSTC": str(toolchain_bin / "rustc"),
        "RUSTUP_TOOLCHAIN": CONTRACT["runtime"]["toolchain"],
        "GOROOT": str(go_bin.parent.parent),
        "LANG": "C", "LC_ALL": "C", "TZ": "UTC", "CARGO_NET_OFFLINE": "true",
    })
    return env


def archive_consumer(item: dict[str, Any], revision: str, run_root: Path) -> dict[str, Any]:
    checkout = consumer_checkout(item)
    git("cat-file", "-e", f"{revision}^{{commit}}", cwd=checkout)
    raw = git_archive(checkout, revision)
    destination = run_root / "archives" / item["name"] / ("baseline" if revision == item["baseline_commit"] else "candidate")
    destination.mkdir(parents=True)
    archive_path = run_root / "archives" / f"{item['name']}-{revision}.tar"
    archive_path.write_bytes(raw)
    with tarfile.open(fileobj=__import__("io").BytesIO(raw), mode="r:") as archive:
        archive.extractall(destination, filter="data")
    for name in ("Cargo.toml", "Cargo.lock"):
        if not (destination / name).is_file():
            fail(f"{item['name']}: archived {name} is missing")
    hydrated_head = hydrate_source(checkout, revision, destination)
    return {"consumer": item["name"], "revision": revision, "archive": str(archive_path), "archive_sha256": sha_bytes(raw), "manifest_sha256": sha_file(destination / "Cargo.toml"), "lock_sha256": sha_file(destination / "Cargo.lock"), "hydrated_head": hydrated_head, "source": str(destination)}


def metadata(source: Path, env: dict[str, str]) -> dict[str, Any]:
    result = run(["cargo", "metadata", "--locked", "--offline", "--format-version", "1"], source, env, timeout=300)
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or not isinstance(value.get("packages"), list):
        fail("Cargo metadata is malformed")
    return value


def verify_pin(item: dict[str, Any], source: Path, env: dict[str, str], expected: str) -> dict[str, Any]:
    pins = source_pins(source, expected)
    value = metadata(source, env)
    found: dict[str, str] = {}
    for package in value["packages"]:
        name = package.get("name")
        if name in {"symaira-core-sqlite", "symaira-core-fs"}:
            source_value = package.get("source", "")
            if source_value != expected_git_source(expected):
                fail(f"{item['name']}: {name} pin differs from {expected}")
            found[name] = source_value
    if set(found) != {"symaira-core-sqlite", "symaira-core-fs"}:
        fail(f"{item['name']}: CoreKit SQLite/FS packages missing from metadata")
    return {"sha256": sha_bytes(canonical(value)), "document": value, "packages": found, "pins": pins}


def command_record(command: list[str], cwd: Path, env: dict[str, str], label: str, timeout: float = 1800) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter_ns()
    result = run(command, cwd, env, timeout)
    elapsed = (time.perf_counter_ns() - start) / 1_000_000
    return {"label": label, "argv": command, "env": {key: env.get(key, "") for key in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "TMPDIR", "CARGO_HOME", "CARGO_TARGET_DIR", "RUSTUP_HOME", "RUSTC", "RUSTUP_TOOLCHAIN", "GOROOT", "GOCACHE", "GOMODCACHE", "GOPATH", "CARGO_NET_OFFLINE", "RUSTC_WRAPPER")}, "exit_code": result.returncode, "started_at": started, "ended_at": datetime.now(timezone.utc).isoformat(), "elapsed_ms": elapsed, "stdout_sha256": sha_bytes(result.stdout), "stderr_sha256": sha_bytes(result.stderr)}


def canary(binary: Path, cwd: Path, env: dict[str, str], item: dict[str, Any]) -> dict[str, Any]:
    command = [str(binary), *CONTRACT["canary_command"]]
    result = run(command, cwd, env, timeout=30)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        fail(f"{item['name']}: invalid version JSON")
    if not isinstance(payload, dict) or payload.get("tool") != item["canary_tool"] or "version" not in payload or "schema_version" not in payload:
        fail(f"{item['name']}: invalid version canary")
    return {"argv": CONTRACT["canary_command"], "exit_code": result.returncode, "stdout_base64": base64.b64encode(result.stdout).decode(), "stdout_sha256": sha_bytes(result.stdout), "stderr": result.stderr.decode(errors="replace"), "semantic": payload}


def build_probe(item: dict[str, Any], revision: str, source: Path, env_root: Path, cargo_home: Path, target: Path, rustup: Path, toolchain_bin: Path, go_bin: Path, label: str) -> dict[str, Any]:
    env = isolated_env(env_root, cargo_home, target, rustup, toolchain_bin, go_bin)
    command = ["cargo", "build", "--release", "--manifest-path", "Cargo.toml", "-p", item["binary_package"], "--bin", item["binary"], "--locked", "--frozen"]
    record = command_record(command, source, env, label)
    binary = target / "release" / item["binary"]
    if not binary.is_file():
        fail(f"{item['name']}: release artifact is missing")
    record.update({"revision": revision, "target": str(target), "cargo_home": str(cargo_home), "artifact": {"path": str(binary), "size": binary.stat().st_size, "sha256": sha_file(binary)}, "canary": canary(binary, source, env, item)})
    return record


def cell(item: dict[str, Any], mode: str, revisions: dict[str, dict[str, Any]], roots: dict[str, Path], run_root: Path, rustup: Path, toolchain_bin: Path, go_bin: Path) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    orders = ["baseline-first"] * 5 + ["candidate-first"] * 5
    for index, order in enumerate(orders):
        sides = ["baseline", "candidate"] if order == "baseline-first" else ["candidate", "baseline"]
        probes: dict[str, Any] = {}
        for side in sides:
            info = revisions[side]
            cargo_home = roots[side + "_cargo"]
            if mode == "clean":
                target = run_root / "target" / item["name"] / side / f"clean-{index}"
            else:
                # clean-0 is the first successful clean probe for each side;
                # warm probes reuse it without an uncounted priming build.
                target = run_root / "target" / item["name"] / side / "clean-0"
            probes[side] = build_probe(item, info["revision"], Path(info["source"]), run_root / "process" / item["name"] / mode / str(index) / side, cargo_home, target, rustup, toolchain_bin, go_bin, f"{mode}-{index}-{side}")
        pairs.append({"index": index, "order": order, "baseline_ms": probes["baseline"]["elapsed_ms"], "candidate_ms": probes["candidate"]["elapsed_ms"], "ratio": probes["candidate"]["elapsed_ms"] / probes["baseline"]["elapsed_ms"], "probes": probes})
    ratios = [pair["ratio"] for pair in pairs]
    sizes = {side: [pair["probes"][side]["artifact"]["size"] for pair in pairs] for side in ("baseline", "candidate")}
    summary = {"time_ratio_median": statistics.median(ratios), "time_ratio_p95": sorted(ratios)[8], "time_ratio_min": min(ratios), "time_ratio_max": max(ratios), "artifact_size_baseline_median": statistics.median(sizes["baseline"]), "artifact_size_candidate_median": statistics.median(sizes["candidate"]), "artifact_size_ratio": statistics.median(sizes["candidate"]) / statistics.median(sizes["baseline"])}
    return {"consumer": item["name"], "mode": mode, "pairs": pairs, "summary": summary}


def validate_report(report: dict[str, Any], report_path: Path | None = None, allow_test_runtime: bool = False) -> None:
    if report.get("schema_version") != 1 or report.get("gate_id") != "SQL-006-80-BUILD" or report.get("status") not in {"passed", "failed", "blocked"}:
        fail("SQL-006 report has an invalid status or schema")
    if report.get("contract_sha256") != sha_file(CONTRACT_PATH):
        fail("contract hash mismatch")
    if not allow_test_runtime and (report.get("runner_sha256") != sha_file(Path(__file__)) or report.get("validator_sha256") != sha_file(Path(__file__))):
        fail("runner/validator hash mismatch")
    expected = {(item["name"], mode): item for item in CONTRACT["consumers"] for mode in CONTRACT["modes"]}
    cells = report.get("cells")
    if not isinstance(cells, list) or len(cells) != 4 or {(cell.get("consumer"), cell.get("mode")) for cell in cells} != set(expected):
        fail("cell matrix mismatch")
    counts = report.get("counts", {})
    if counts.get("expected") != 80 or counts.get("observed") != 80:
        fail("SQL-006 requires exactly 80 counted probes")
    runtime = Path(report.get("provenance", {}).get("nvme_runtime", ""))
    run_root = Path(report.get("run_root", ""))
    if not runtime.is_absolute() or not run_root.is_absolute():
        fail("report paths must be absolute")
    if not allow_test_runtime:
        if runtime != Path(CONTRACT["runtime"]["runtime_mount"]).resolve():
            fail("report runtime differs from the frozen secure runtime")
        if Path(report.get("provenance", {}).get("nvme_storage", "")).resolve() != Path(CONTRACT["runtime"]["storage_root"]).resolve():
            fail("report storage differs from the frozen NVMe storage")
        expected_toolchain = Path(CONTRACT["runtime"]["runtime_mount"]) / "runtime-bootstrap" / "rustup" / "toolchains" / CONTRACT["runtime"]["toolchain"] / "bin"
        if Path(report.get("provenance", {}).get("toolchain_bin", "")).resolve() != expected_toolchain.resolve():
            fail("report toolchain differs from the frozen secure-runtime toolchain")
        expected_go = Path(CONTRACT["runtime"]["runtime_mount"]) / "runtime-bootstrap" / "go-home" / "sdk" / f"go{CONTRACT['runtime']['go_toolchain']}" / "bin" / "go"
        if Path(report.get("provenance", {}).get("go_bin", "")).resolve() != expected_go.resolve():
            fail("report Go oracle differs from the frozen secure-runtime toolchain")
    under(run_root, runtime, "run root")
    cache_root = under(Path(report.get("cache_root", "")), runtime, "cache root")
    short_temp_parent = (runtime / "t").resolve(strict=False)
    if os.name == "nt":
        if not allow_test_runtime:
            fail("SQL-006 private runtime requires POSIX permission checks")
    elif run_root.stat().st_mode & 0o077 or cache_root.stat().st_mode & 0o077:
        fail("run/cache roots are not private")
    archives = report.get("archives")
    if not isinstance(archives, list) or len(archives) != 4:
        fail("archive provenance is incomplete")
    expected_archives = {(item["name"], revision) for item in CONTRACT["consumers"] for revision in (item["baseline_commit"], item["candidate_commit"])}
    observed_archives = {(archive.get("consumer"), archive.get("revision")) for archive in archives}
    if observed_archives != expected_archives:
        fail("archive matrix mismatch")
    for archive in archives:
        item = next((value for value in CONTRACT["consumers"] if value["name"] == archive.get("consumer")), None)
        if item is None or archive.get("revision") not in {item["baseline_commit"], item["candidate_commit"]}:
            fail("archive consumer/revision mismatch")
        archive_path = under(Path(archive.get("archive", "")), run_root, "archive")
        source = under(Path(archive.get("source", "")), run_root, "archive source")
        if not archive_path.is_file() or sha_file(archive_path) != archive.get("archive_sha256"):
            fail("archive hash mismatch")
        if not allow_test_runtime and sha_bytes(git_archive(consumer_checkout(item), archive["revision"])) != archive.get("archive_sha256"):
            fail("archive is not bound to the recorded consumer commit")
        if not allow_test_runtime:
            if archive.get("hydrated_head") != archive["revision"]:
                fail("archive hydration revision mismatch")
            if git("rev-parse", "HEAD", cwd=source) != archive["revision"] or git("status", "--porcelain=v1", "--untracked-files=all", cwd=source):
                fail("archive source is not an exact clean hydrated checkout")
            if sha_bytes(git_archive(source, archive["revision"])) != archive.get("archive_sha256"):
                fail("archive source does not reproduce the recorded archive")
        for name, key in (("Cargo.toml", "manifest_sha256"), ("Cargo.lock", "lock_sha256")):
            if not (source / name).is_file() or sha_file(source / name) != archive.get(key):
                fail("archive manifest/lock hash mismatch")
        expected_pin = item["baseline_corekit"] if archive["revision"] == item["baseline_commit"] else item["candidate_corekit"]
        pins = source_pins(source, expected_pin)
        metadata_value = archive.get("metadata", {})
        document = metadata_value.get("document")
        if not isinstance(document, dict) or sha_bytes(canonical(document)) != metadata_value.get("sha256"):
            fail("archive metadata hash mismatch")
        packages = metadata_value.get("packages", {})
        if metadata_value.get("pins") != pins or packages != {"symaira-core-sqlite": expected_git_source(expected_pin), "symaira-core-fs": expected_git_source(expected_pin)}:
            fail("archive CoreKit metadata pin mismatch")
    preflights = report.get("value_preflights")
    expected_preflights = [(item["name"], command) for item in CONTRACT["consumers"] for command in CONTRACT["value_commands"][item["name"]]]
    if not isinstance(preflights, list) or len(preflights) != 4:
        fail("value preflight evidence is incomplete")
    for record, (consumer, command) in zip(preflights, expected_preflights):
        if record.get("label") != f"{consumer}-value-{CONTRACT['value_commands'][consumer].index(command)}" or record.get("argv") != command:
            fail("value preflight command mismatch")
        if record.get("env", {}).get("CARGO_NET_OFFLINE") != "true":
            fail("value preflight must be offline")
        temp_root = under(Path(record.get("env", {}).get("TMPDIR", "")), runtime, "value preflight TMPDIR")
        if temp_root.parent != short_temp_parent:
            fail("value preflight TMPDIR is not the short secure-runtime path")
        if not isinstance(record.get("exit_code"), int):
            fail("value preflight exit evidence is malformed")
    if report.get("status") == "passed" and any(item.get("exit_code") != 0 for item in preflights):
        fail("passed report contains a failed value preflight")
    seen = 0
    thresholds = []
    for entry in cells:
        item = expected[(entry["consumer"], entry["mode"])]
        pairs = entry.get("pairs")
        if not isinstance(pairs, list) or len(pairs) != 10:
            fail(f"{entry['consumer']}/{entry['mode']}: expected 10 pairs")
        if sum(pair.get("order") == "baseline-first" for pair in pairs) != 5 or sum(pair.get("order") == "candidate-first" for pair in pairs) != 5:
            fail(f"{entry['consumer']}/{entry['mode']}: pair order mismatch")
        ratios: list[float] = []
        sizes: dict[str, list[float]] = {"baseline": [], "candidate": []}
        for index, pair in enumerate(pairs):
            if pair.get("index") != index:
                fail("pair index mismatch")
            probes = pair.get("probes", {})
            if set(probes) != {"baseline", "candidate"}:
                fail("pair sides mismatch")
            for side in ("baseline", "candidate"):
                probe = probes[side]
                expected_revision = item["baseline_commit"] if side == "baseline" else item["candidate_commit"]
                if probe.get("exit_code") != 0 or probe.get("revision") != expected_revision:
                    fail("probe provenance/exit mismatch")
                expected_command = ["cargo", "build", "--release", "--manifest-path", "Cargo.toml", "-p", item["binary_package"], "--bin", item["binary"], "--locked", "--frozen"]
                toolchain_bin = runtime / "runtime-bootstrap" / "rustup" / "toolchains" / CONTRACT["runtime"]["toolchain"] / "bin"
                go_bin = runtime / "runtime-bootstrap" / "go-home" / "sdk" / f"go{CONTRACT['runtime']['go_toolchain']}" / "bin" / "go"
                expected_env = {"RUSTUP_HOME": str(toolchain_bin.parent.parent.parent), "RUSTC": str(toolchain_bin / "rustc"), "RUSTUP_TOOLCHAIN": CONTRACT["runtime"]["toolchain"], "GOROOT": str(go_bin.parent.parent), "CARGO_NET_OFFLINE": "true", "RUSTC_WRAPPER": ""}
                if probe.get("argv") != expected_command or any(probe.get("env", {}).get(key) != value for key, value in expected_env.items()):
                    fail("timed build command/environment mismatch")
                target = under(Path(probe["target"]), run_root, "target")
                cargo_home = under(Path(probe["cargo_home"]), runtime, "Cargo home")
                temp_root = under(Path(probe.get("env", {}).get("TMPDIR", "")), runtime, "TMPDIR")
                for key in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "GOCACHE", "GOMODCACHE", "GOPATH"):
                    under(Path(probe.get("env", {}).get(key, "")), run_root, key)
                if temp_root.parent != short_temp_parent:
                    fail("timed build TMPDIR is not the short secure-runtime path")
                if (under(Path(probe.get("env", {}).get("CARGO_TARGET_DIR", "")), run_root, "CARGO_TARGET_DIR") != target
                        or under(Path(probe.get("env", {}).get("CARGO_HOME", "")), runtime, "CARGO_HOME") != cargo_home):
                    fail("timed build paths differ from recorded environment")
                if entry["mode"] == "clean":
                    if str(target).find("clean-") < 0:
                        fail("clean probe target is not per-sample")
                else:
                    if target.name != "clean-0":
                        fail("warm probe must reuse the first clean target")
                artifact = probe.get("artifact", {})
                path = under(Path(artifact.get("path", "")), run_root, "artifact")
                if not path.is_file() or path.stat().st_size != artifact.get("size") or sha_file(path) != artifact.get("sha256"):
                    fail("artifact evidence mismatch")
                canary_value = probe.get("canary", {})
                if canary_value.get("argv") != CONTRACT["canary_command"] or canary_value.get("stderr") != "":
                    fail("canary command evidence mismatch")
                raw = base64.b64decode(canary_value.get("stdout_base64", ""), validate=True)
                if sha_bytes(raw) != canary_value.get("stdout_sha256") or canary_value.get("exit_code") != 0:
                    fail("canary evidence mismatch")
                payload = json.loads(raw)
                if payload.get("tool") != item["canary_tool"] or payload != canary_value.get("semantic"):
                    fail("canary semantic mismatch")
                sizes[side].append(float(artifact["size"]))
            if not math.isclose(float(pair.get("baseline_ms")), float(probes["baseline"].get("elapsed_ms")), rel_tol=1e-12):
                fail("baseline pair time is not the raw probe time")
            if not math.isclose(float(pair.get("candidate_ms")), float(probes["candidate"].get("elapsed_ms")), rel_tol=1e-12):
                fail("candidate pair time is not the raw probe time")
            ratio = pair["candidate_ms"] / pair["baseline_ms"]
            if not math.isclose(ratio, pair["ratio"], rel_tol=1e-12):
                fail("stale paired timing ratio")
            ratios.append(ratio)
            seen += 2
        summary = entry.get("summary", {})
        expected_summary = {"time_ratio_median": statistics.median(ratios), "time_ratio_p95": sorted(ratios)[8], "time_ratio_min": min(ratios), "time_ratio_max": max(ratios), "artifact_size_baseline_median": statistics.median(sizes["baseline"]), "artifact_size_candidate_median": statistics.median(sizes["candidate"]), "artifact_size_ratio": statistics.median(sizes["candidate"]) / statistics.median(sizes["baseline"])}
        for key, value in expected_summary.items():
            if not math.isclose(float(summary.get(key)), value, rel_tol=1e-12):
                fail(f"stale summary: {entry['consumer']}/{entry['mode']}/{key}")
        thresholds.append({"consumer": entry["consumer"], "metric": "time", "mode": entry["mode"], "ratio": expected_summary["time_ratio_median"], "passed": expected_summary["time_ratio_median"] <= LIMIT})
        if entry["mode"] == "clean":
            thresholds.append({"consumer": entry["consumer"], "metric": "artifact_size", "ratio": expected_summary["artifact_size_ratio"], "passed": expected_summary["artifact_size_ratio"] <= LIMIT})
    if seen != 80:
        fail("observed probe count mismatch")
    if len(thresholds) != 6:
        fail("six independent SQL-006 limits are not green")
    if report.get("thresholds") != thresholds:
        fail("threshold evidence mismatch")
    if report.get("status") == "passed" and any(not item["passed"] for item in thresholds):
        fail("passed report contains a failed SQL-006 limit")
    if report_path is not None and not under(report_path, runtime, "report"):
        fail("report is outside secure runtime")


def preflight(item: dict[str, Any], source: Path, env: dict[str, str]) -> list[dict[str, Any]]:
    results = []
    for index, command in enumerate(CONTRACT["value_commands"][item["name"]]):
        results.append(command_record(command, source, env, f"{item['name']}-value-{index}", timeout=1800))
    return results


def run_gate(output: Path) -> int:
    runtime, storage, rustup, toolchain_bin, go_bin, runtime_provenance = secure_runtime()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate_pins = {item["candidate_corekit"] for item in CONTRACT["consumers"]}
    if len(candidate_pins) != 1:
        fail("SQL-006 contract does not have one candidate CoreKit revision")
    run_id = f"{timestamp}-{candidate_pins.pop()[:7]}"
    run_root = runtime / CONTRACT["runtime"]["run_relative"] / run_id
    cache_root = runtime / CONTRACT["runtime"]["cache_relative"] / run_id
    run_root.mkdir(parents=True, mode=0o700)
    cache_root.mkdir(parents=True, mode=0o700)
    run_root.chmod(0o700)
    cache_root.chmod(0o700)
    output = under(output, runtime, "report")
    output.parent.mkdir(parents=True, exist_ok=True)
    (cache_root / "cargo").mkdir(parents=True)
    archives: list[dict[str, Any]] = []
    prepared: dict[str, dict[str, dict[str, Any]]] = {}
    preflights: list[dict[str, Any]] = []
    for item in CONTRACT["consumers"]:
        prepared[item["name"]] = {}
        for side, key in (("baseline", "baseline_commit"), ("candidate", "candidate_commit")):
            record = archive_consumer(item, item[key], run_root)
            source = Path(record["source"])
            cargo_home = cache_root / "cargo" / item["name"] / side
            env = isolated_env(run_root / "preflight" / item["name"] / side, cargo_home, run_root / "preflight-target" / item["name"] / side, rustup, toolchain_bin, go_bin)
            fetch_env = {**env, "CARGO_NET_OFFLINE": "false"}
            fetch = command_record(["cargo", "fetch", "--locked"], source, fetch_env, "cargo-fetch", timeout=1800)
            record["fetch"] = fetch
            record["metadata"] = verify_pin(item, source, env, item["baseline_corekit"] if side == "baseline" else item["candidate_corekit"])
            prepared[item["name"]][side] = {**record, "revision": item[key], "cargo_home": str(cargo_home)}
            archives.append(record)
        candidate = prepared[item["name"]]["candidate"]
        env = isolated_env(run_root / "value" / item["name"], Path(candidate["cargo_home"]), run_root / "value-target" / item["name"], rustup, toolchain_bin, go_bin)
        preflights.extend(preflight(item, Path(candidate["source"]), env))
    cells = []
    for item in CONTRACT["consumers"]:
        revisions = prepared[item["name"]]
        roots = {"baseline_cargo": Path(revisions["baseline"]["cargo_home"]), "candidate_cargo": Path(revisions["candidate"]["cargo_home"])}
        for mode in CONTRACT["modes"]:
            cells.append(cell(item, mode, revisions, roots, run_root, rustup, toolchain_bin, go_bin))
    thresholds = []
    for entry in cells:
        thresholds.append({"consumer": entry["consumer"], "metric": "time", "mode": entry["mode"], "ratio": entry["summary"]["time_ratio_median"], "passed": entry["summary"]["time_ratio_median"] <= LIMIT})
        if entry["mode"] == "clean":
            thresholds.append({"consumer": entry["consumer"], "metric": "artifact_size", "ratio": entry["summary"]["artifact_size_ratio"], "passed": entry["summary"]["artifact_size_ratio"] <= LIMIT})
    toolchain_env = isolated_env(run_root / "toolchain", cache_root / "cargo" / "toolchain", run_root / "toolchain-target", rustup, toolchain_bin, go_bin)
    report = {"schema_version": 1, "gate_id": CONTRACT["gate_id"], "status": "passed" if all(entry["passed"] for entry in thresholds) else "failed", "captured_at": datetime.now(timezone.utc).isoformat(), "contract_sha256": sha_file(CONTRACT_PATH), "runner_sha256": sha_file(Path(__file__)), "validator_sha256": sha_file(Path(__file__)), "run_root": str(run_root), "cache_root": str(cache_root), "provenance": {"nvme_runtime": str(runtime), "nvme_storage": str(storage), "toolchain_bin": str(toolchain_bin), "go_bin": str(go_bin), "runtime": runtime_provenance, "toolchains": {"rustc": run(["rustc", "--version"], run_root, toolchain_env, 30).stdout.decode().strip(), "cargo": run(["cargo", "--version"], run_root, toolchain_env, 30).stdout.decode().strip(), "go": run(["go", "version"], run_root, toolchain_env, 30).stdout.decode().strip()}}, "archives": archives, "value_preflights": preflights, "cells": cells, "counts": {"expected": 80, "observed": 80}, "thresholds": thresholds}
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validate_report(report, output)
    return 0 if report["status"] == "passed" else 1


def synthetic_report(root: Path) -> dict[str, Any]:
    runtime = root / "runtime"
    runtime.mkdir(mode=0o700)
    runtime.chmod(0o700)
    cache_root = runtime / "cache"
    cache_root.mkdir(mode=0o700)
    cache_root.chmod(0o700)
    toolchain_bin = runtime / "runtime-bootstrap" / "rustup" / "toolchains" / CONTRACT["runtime"]["toolchain"] / "bin"
    toolchain_bin.mkdir(parents=True)
    go_bin = runtime / "runtime-bootstrap" / "go-home" / "sdk" / f"go{CONTRACT['runtime']['go_toolchain']}" / "bin" / "go"
    cells = []
    for item in CONTRACT["consumers"]:
        for mode in CONTRACT["modes"]:
            pairs = []
            for index in range(10):
                probes = {}
                for side, revision in (("baseline", item["baseline_commit"]), ("candidate", item["candidate_commit"])):
                    artifact = runtime / f"{item['name']}-{mode}-{index}-{side}"
                    artifact.write_bytes(b"artifact-" + side.encode())
                    payload = json.dumps({"tool": item["canary_tool"], "version": "0.0.0", "schema_version": 1}, separators=(",", ":")).encode()
                    target = runtime / "target" / item["name"] / side / (f"clean-{index}" if mode == "clean" else "clean-0")
                    cargo_home = cache_root / item["name"] / side
                    process_root = runtime / "process" / item["name"] / mode / str(index) / side
                    probes[side] = {"exit_code": 0, "revision": revision, "argv": ["cargo", "build", "--release", "--manifest-path", "Cargo.toml", "-p", item["binary_package"], "--bin", item["binary"], "--locked", "--frozen"], "env": {"HOME": str(process_root / "home"), "USERPROFILE": str(process_root / "home"), "XDG_CONFIG_HOME": str(process_root / "xdg" / "config"), "XDG_CACHE_HOME": str(process_root / "xdg" / "cache"), "XDG_DATA_HOME": str(process_root / "xdg" / "data"), "XDG_STATE_HOME": str(process_root / "xdg" / "state"), "TMPDIR": str(runtime / "t" / f"{item['name']}-{mode}-{index}-{side}"), "CARGO_HOME": str(cargo_home), "CARGO_TARGET_DIR": str(target), "RUSTUP_HOME": str(toolchain_bin.parent.parent.parent), "RUSTC": str(toolchain_bin / "rustc"), "RUSTUP_TOOLCHAIN": CONTRACT["runtime"]["toolchain"], "GOROOT": str(go_bin.parent.parent), "GOCACHE": str(process_root / "go-cache"), "GOMODCACHE": str(process_root / "go-mod-cache"), "GOPATH": str(process_root / "go"), "CARGO_NET_OFFLINE": "true", "RUSTC_WRAPPER": ""}, "target": str(target), "cargo_home": str(cargo_home), "elapsed_ms": 10.0 if side == "baseline" else 10.5, "artifact": {"path": str(artifact), "size": artifact.stat().st_size, "sha256": sha_file(artifact)}, "canary": {"argv": CONTRACT["canary_command"], "exit_code": 0, "stdout_base64": base64.b64encode(payload).decode(), "stdout_sha256": sha_bytes(payload), "stderr": "", "semantic": json.loads(payload)}}
                pairs.append({"index": index, "order": "baseline-first" if index < 5 else "candidate-first", "baseline_ms": 10.0, "candidate_ms": 10.5, "ratio": 1.05, "probes": probes})
            cells.append({"consumer": item["name"], "mode": mode, "pairs": pairs, "summary": {"time_ratio_median": 1.05, "time_ratio_p95": 1.05, "time_ratio_min": 1.05, "time_ratio_max": 1.05, "artifact_size_baseline_median": 17.0, "artifact_size_candidate_median": 18.0, "artifact_size_ratio": 18 / 17}})
    thresholds = []
    for item in CONTRACT["consumers"]:
        for mode in CONTRACT["modes"]:
            thresholds.append({"consumer": item["name"], "metric": "time", "mode": mode, "ratio": 1.05, "passed": True})
            if mode == "clean":
                thresholds.append({"consumer": item["name"], "metric": "artifact_size", "ratio": 18 / 17, "passed": True})
    archives = []
    for item in CONTRACT["consumers"]:
        for side, key, pin in (("baseline", "baseline_commit", item["baseline_corekit"]), ("candidate", "candidate_commit", item["candidate_corekit"])):
            source = runtime / f"source-{item['name']}-{side}"
            source.mkdir()
            source_url = expected_git_source(pin)
            (source / "Cargo.toml").write_text(f"[dependencies]\nsymaira-core-sqlite = {{ git = \"{COREKIT_URL}\", rev = \"{pin}\" }}\n", encoding="utf-8")
            (source / "Cargo.lock").write_text(f"version = 4\n\n[[package]]\nname = \"symaira-core-fs\"\nversion = \"0.0.0\"\nsource = \"{source_url}\"\n\n[[package]]\nname = \"symaira-core-sqlite\"\nversion = \"0.0.0\"\nsource = \"{source_url}\"\ndependencies = [\"symaira-core-fs\"]\n", encoding="utf-8")
            archive = runtime / f"archive-{item['name']}-{side}.tar"
            archive.write_bytes(f"{item['name']}-{side}".encode())
            document = {"packages": [{"name": name, "source": source_url} for name in ("symaira-core-sqlite", "symaira-core-fs")]}
            archives.append({"consumer": item["name"], "revision": item[key], "archive": str(archive), "archive_sha256": sha_file(archive), "source": str(source), "manifest_sha256": sha_file(source / "Cargo.toml"), "lock_sha256": sha_file(source / "Cargo.lock"), "metadata": {"sha256": sha_bytes(canonical(document)), "document": document, "packages": {"symaira-core-sqlite": source_url, "symaira-core-fs": source_url}, "pins": source_pins(source, pin)}})
    preflights = []
    for item in CONTRACT["consumers"]:
        for index, command in enumerate(CONTRACT["value_commands"][item["name"]]):
            preflights.append({"label": f"{item['name']}-value-{index}", "argv": command, "env": {"TMPDIR": str(runtime / "t" / f"{item['name']}-value-{index}"), "CARGO_NET_OFFLINE": "true"}, "exit_code": 0})
    return {"schema_version": 1, "gate_id": CONTRACT["gate_id"], "status": "passed", "contract_sha256": sha_file(CONTRACT_PATH), "runner_sha256": sha_file(Path(__file__)), "validator_sha256": sha_file(Path(__file__)), "run_root": str(runtime), "cache_root": str(cache_root), "provenance": {"nvme_runtime": str(runtime), "nvme_storage": str(runtime), "toolchain_bin": str(toolchain_bin)}, "archives": archives, "value_preflights": preflights, "cells": cells, "counts": {"expected": 80, "observed": 80}, "thresholds": thresholds}


def self_test() -> int:
    import copy
    with tempfile.TemporaryDirectory(prefix="sql006-cost-selftest-", dir=os.environ.get("TMPDIR")) as raw:
        report = synthetic_report(Path(raw))
        validate_report(report, allow_test_runtime=True)
        controls = []
        mutations = [
            ("wrong pin", lambda value: value["cells"][0]["pairs"][0]["probes"]["baseline"].__setitem__("revision", "0" * 40)),
            ("wrong count", lambda value: value["cells"][0]["pairs"].pop()),
            ("raw time", lambda value: value["cells"][0]["pairs"][0].__setitem__("candidate_ms", 12.0)),
            ("artifact hash", lambda value: value["cells"][0]["pairs"][0]["probes"]["baseline"]["artifact"].__setitem__("sha256", "0" * 64)),
            ("canary", lambda value: value["cells"][0]["pairs"][0]["probes"]["baseline"]["canary"].__setitem__("stdout_base64", base64.b64encode(b"{}").decode())),
            ("outside runtime", lambda value: value["cells"][0]["pairs"][0]["probes"]["baseline"].__setitem__("target", "/tmp/sql006-target")),
        ]
        for label, mutate in mutations:
            candidate = copy.deepcopy(report)
            mutate(candidate)
            try:
                validate_report(candidate, allow_test_runtime=True)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                controls.append(label)
        assert controls == [label for label, _ in mutations], controls
    print("PASS SQL-006 cost-gate negative controls: " + ", ".join(controls))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if sum((args.run, args.check, args.self_test)) != 1:
        parser.error("choose exactly one of --run, --check or --self-test")
    if args.self_test:
        return self_test()
    if args.report is None:
        parser.error("--report is required")
    if args.check:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        validate_report(report, args.report)
        print(json.dumps({"status": report["status"], "report": str(args.report)}, sort_keys=True))
        return 0 if report["status"] == "passed" else 1
    return run_gate(args.report)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, TimeoutError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(f"FAIL SQL-006 cost gate: {error}", file=sys.stderr)
        raise SystemExit(1)
