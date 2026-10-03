#!/usr/bin/env python3
"""Execute every native functional contract with Go absent, then Go denied."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from bounded_oracle_process import run_checked

ROOT = Path(__file__).resolve().parents[2]
COUNTS = {"request": 13, "cache": 7, "persistence": 7, "cosign": 13, "apply": 17, "cancellation": 16}


def path_without_go(original, directory):
    """Hide only Go executables, preserving shared system-bin prerequisites."""
    paths = []
    for index, name in enumerate(original.split(os.pathsep)):
        if not name:
            continue
        root = Path(name)
        if not any((root / executable).is_file() for executable in ("go", "go.exe")):
            paths.append(name)
            continue
        view = directory / f"bin-{index}"
        view.mkdir()
        for executable in root.iterdir():
            lower = executable.name.lower()
            if lower in {"go", "go.exe", "gofmt", "gofmt.exe", "gccgo", "gccgo.exe"} or re.fullmatch(r"go1\.[0-9.]+(?:\.exe)?", lower):
                continue
            if executable.is_file():
                # Preserve the installed tool's bytes and resource location.
                # Removing /usr/bin wholesale would also remove Make and cc.
                (view / executable.name).symlink_to(executable.resolve())
        paths.append(str(view))
    return os.pathsep.join(paths)


def main():
    head = os.environ["FROZEN_CONTRACTS_HEAD"]
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("aggregate requires an immutable execution head")
    actual = run_checked(["git", "rev-parse", "HEAD"], cwd=ROOT, env=dict(os.environ), timeout=30, check=True).stdout.decode().strip()
    if actual != head:
        raise ValueError("aggregate checkout differs from requested immutable head")
    artifacts = Path(os.environ["RUNNER_TEMP"]) / "frozen-contracts-native"
    artifacts.mkdir()
    denied = artifacts / "go-denial"
    denied.mkdir()
    marker = artifacts / "forbidden-go-called"
    source = denied / "blocked.rs"
    source.write_text('fn main() { std::fs::write(' + json.dumps(marker.as_posix()) + ', b"invoked").unwrap(); std::process::exit(97); }\n')
    binary = denied / ("go.exe" if os.name == "nt" else "go")
    run_checked(["rustc", "--edition=2024", "--crate-name", "aggregate_go_denial", str(source), "-o", str(binary)], cwd=ROOT, env=dict(os.environ), timeout=60, artifact_dir=artifacts / "denial-build", check=True)
    control = run_checked([str(binary), "version"], cwd=ROOT, env=dict(os.environ), timeout=15, artifact_dir=artifacts / "denial-control")
    if control.returncode != 97 or marker.read_bytes() != b"invoked":
        raise ValueError("compiled native Go-denial control failed")
    marker.unlink()
    # PATH views link installed system tools. Keep them outside the evidence
    # upload, which would otherwise dereference and archive entire system bins.
    with tempfile.TemporaryDirectory(prefix="corekit-go-filtered-path-") as directory:
        absent_path = path_without_go(os.environ["PATH"], Path(directory))
        if shutil.which("go", path=absent_path) is not None:
            raise ValueError("Go remains discoverable in aggregate PATH")
        execute_phases(head, artifacts, denied, marker, absent_path)


def execute_phases(head, artifacts, denied, marker, absent_path):
    original_home = Path.home()
    phases = []
    for phase in ("absent", "denied"):
        with tempfile.TemporaryDirectory(prefix=f"rust-contracts-{phase}-") as name:
            private = Path(name)
            env = dict(os.environ, PATH=(str(denied) + os.pathsep if phase == "denied" else "") + absent_path,
                       CARGO_NET_OFFLINE="true", CARGO_TARGET_DIR=str(ROOT / "target"), RUSTUP_AUTO_INSTALL="0",
                       GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off", GOENV="off", GOWORK="off")
            env.pop("GO_ORACLE", None)
            env.pop("GOROOT", None)
            env.pop("DEV_EXTERNAL", None)
            for variable, suffix in (("HOME", "home"), ("USERPROFILE", "home"), ("XDG_CACHE_HOME", "cache"), ("XDG_CONFIG_HOME", "config"), ("APPDATA", "config"), ("XDG_DATA_HOME", "data"), ("LOCALAPPDATA", "data"), ("XDG_STATE_HOME", "state"), ("TMPDIR", "tmp"), ("TMP", "tmp"), ("TEMP", "tmp")):
                path = private / suffix
                path.mkdir(mode=0o700, exist_ok=True)
                env[variable] = str(path)
            for variable, suffix in (("CARGO_HOME", ".cargo"), ("RUSTUP_HOME", ".rustup")):
                env[variable] = os.environ.get(variable, str(original_home / suffix))
            old = os.umask(0o022) if os.name == "posix" else None
            try:
                result = run_checked(["make", "rust-contracts"], cwd=ROOT, env=env, timeout=1800, artifact_dir=artifacts / phase, merge_stderr=True)
                if result.returncode:
                    raise RuntimeError(f"Go-{phase} aggregate failed with exit {result.returncode}:\n" + result.stdout.decode(errors="replace")[-4096:])
            finally:
                if old is not None:
                    os.umask(old)
            if marker.exists():
                raise ValueError("aggregate attempted to execute Go")
            reports = {lane: json.loads((ROOT / "target/frozen-update" / f"{lane}-report.json").read_bytes()) for lane in COUNTS}
            if any(report["status"] != "PASS" or report["case_count"] != COUNTS[lane] or report["actual_rust_executed"] is not True for lane, report in reports.items()):
                raise ValueError("aggregate has missing or zero-case update evidence")
            text = result.stdout.decode(errors="replace")
            if "PASS real Rust Cosign: valid signature accepted" not in text or "PASS signed release asset fetched, verified, extracted" not in text:
                raise ValueError("aggregate lacks real signed-release acceptance")
            documents = []
            for line in text.splitlines():
                if line.startswith("{"):
                    try:
                        documents.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            families = [row for row in documents if row.get("family") in {"foundation", "llm"}]
            if len(families) != 2 or {row["family"] for row in families} != {"foundation", "llm"} or any(row["status"] != "PASS" or row["fixture_mutation_rejected"] is not True or row["rust_tests"] == 0 for row in families):
                raise ValueError("aggregate lacks complete Foundation/LLM execution and mutations")
            fs = [row for row in documents if "fs_sec_case_count" in row]
            if len(fs) != 1 or fs[0]["status"] != "PASS" or fs[0]["fs_sec_case_count"] != 13 or fs[0]["path_control_count"] != 9 or fs[0]["rust_named_test_passes"] != 1 or len(fs[0]["mutations"]) != 2:
                raise ValueError("aggregate lacks actual FS rows, controls or named mutation gates")
            shutil.copytree(Path(fs[0]["artifacts_dir"]), artifacts / (phase + "-fs-raw"))
            for name, count in (("mcp", 46), ("mcpcfg", 24)):
                if f"PASS {name}-differential ({count} executed Rust cases; frozen Go expected;" not in text:
                    raise ValueError("aggregate lacks complete " + name + " process corpus")
            sqlite = json.loads((ROOT / "target/sqlite-frozen-replay.json").read_bytes())
            if sqlite["status"] != "PASS" or sqlite["case_count"] != 6 or sqlite["semantic_mutation_rejected"] is not True:
                raise ValueError("aggregate lacks original SQLite cases and actual semantic mutation")
            phases.append({"mode": phase, "exit_code": result.returncode, "update_cases": {lane: report["case_count"] for lane, report in reports.items()},
                           "families": families, "fs_cases": 13, "fs_controls": 9, "mcp_cases": 46, "mcpcfg_cases": 24,
                           "sqlite_cases": 6, "sqlite_checked_fields": sqlite["checked_fields"], "raw_stdout_sha256": hashlib.sha256(result.stdout).hexdigest()})
    shutil.copytree(ROOT / "target/frozen-update", artifacts / "update-raw")
    for name in ("sqlite-frozen-replay.json", "sqlite-frozen-replay.rust.raw"):
        shutil.copy2(ROOT / "target" / name, artifacts / name)
    report = {"status": "PASS", "execution_head": head, "go_absent_from_path": True, "native_go_denial_control": True,
              "forbidden_go_called": False, "phases": phases}
    (artifacts / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
