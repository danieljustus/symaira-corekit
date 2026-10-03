#!/usr/bin/env python3
"""Run frozen Make gates with executable native tool denial controls."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from bounded_oracle_process import run_checked

ROOT = Path(__file__).resolve().parents[2]


def main():
    head = os.environ["FROZEN_CORE_HEAD"]
    import re
    if not re.fullmatch("[0-9a-f]{40}", head):
        raise ValueError("missing exact native execution head")
    artifacts = Path(os.environ["RUNNER_TEMP"]) / "frozen-core-native"
    artifacts.mkdir()
    marker = artifacts / "forbidden-tool-called"
    denied = artifacts / "denied-tools"
    denied.mkdir()
    source = denied / "blocked.rs"
    source.write_text('fn main() { std::fs::write(' + json.dumps(marker.as_posix()) + ', b"invoked").unwrap(); std::process::exit(97); }\n')
    binary = denied / ("blocked.exe" if os.name == "nt" else "blocked")
    run_checked(["rustc", "--edition=2024", "--crate-name", "blocked_frozen", str(source), "-o", str(binary)],
                cwd=ROOT, env=dict(os.environ), timeout=120, artifact_dir=artifacts / "build-denial", check=True)
    for name in ("go", "git"):
        executable = denied / (name + (".exe" if os.name == "nt" else ""))
        shutil.copy2(binary, executable)
        result = run_checked([str(executable), "--version"], cwd=ROOT, env=dict(os.environ), timeout=30,
                             artifact_dir=artifacts / (name + "-positive-control"), check=False)
        if result.returncode != 97 or marker.read_bytes() != b"invoked":
            raise ValueError("native executable denial control failed")
        marker.unlink()
    with tempfile.TemporaryDirectory(prefix="frozen-core-native-") as scratch:
        env = dict(os.environ, PATH=str(denied) + os.pathsep + os.environ["PATH"], CARGO_NET_OFFLINE="true",
                   RUSTUP_AUTO_INSTALL="0", TMPDIR=scratch, TMP=scratch, TEMP=scratch, PYTHONDONTWRITEBYTECODE="1")
        env.pop("GO_ORACLE", None)
        gate = run_checked(["make", "rust-foundation-contract", "rust-llm-contract"], cwd=ROOT, env=env,
                           timeout=600, artifact_dir=artifacts / "make-default-gates", check=True)
    if marker.exists():
        raise ValueError("default frozen Make gate invoked Go or Git")
    reports = [json.loads(line) for line in gate.stdout.splitlines() if line.startswith(b'{"contract_groups"')]
    if {row["family"] for row in reports} != {"foundation", "llm"} or len(reports) != 2:
        raise ValueError("missing native family replay report")
    if any(row["status"] != "PASS" or row["fixture_mutation_rejected"] is not True for row in reports):
        raise ValueError("native corpus replay/mutation checks failed")
    # SQLite retains Git ancestry/source checks. Deny only Go for this gate;
    # the Foundation/LLM boundary above continues to deny both executables.
    go_only = artifacts / "go-denied"
    go_only.mkdir()
    shutil.copy2(binary, go_only / ("go.exe" if os.name == "nt" else "go"))
    with tempfile.TemporaryDirectory(prefix="sqlite-native-frozen-") as scratch:
        env = dict(os.environ, PATH=str(go_only) + os.pathsep + os.environ["PATH"], CARGO_NET_OFFLINE="true",
                   RUSTUP_AUTO_INSTALL="0", TMPDIR=scratch, TMP=scratch, TEMP=scratch, PYTHONDONTWRITEBYTECODE="1")
        env.pop("GO_ORACLE", None)
        run_checked(["make", "rust-sqlite-contract"], cwd=ROOT, env=env, timeout=600,
                    artifact_dir=artifacts / "make-sqlite-default", check=True)
    if marker.exists():
        raise ValueError("default frozen SQLite Make gate invoked Go")
    sqlite = json.loads((ROOT / "target/sqlite-frozen-replay.json").read_bytes())
    if sqlite["status"] != "PASS" or sqlite["case_count"] != 6 or sqlite["semantic_mutation_rejected"] is not True:
        raise ValueError("missing successful native SQLite replay and mutation control")
    report = {"execution_head": head, "go_git_denial_controls": True, "forbidden_tool_called": False,
              "denial_binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "families": reports,
              "sqlite": {key: sqlite[key] for key in ("status", "native_target", "case_count", "checked_fields", "semantic_mutation_rejected")}}
    (artifacts / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    retained = ROOT / "target/frozen-core-replay"
    if retained.is_dir():
        shutil.copytree(retained, artifacts / "rust-raw")
    for name in ("sqlite-frozen-replay.json", "sqlite-frozen-replay.rust.raw"):
        shutil.copy2(ROOT / "target" / name, artifacts / name)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
