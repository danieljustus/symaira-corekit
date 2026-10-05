#!/usr/bin/env python3
"""Replay original source-bound native SQLite Go captures with Rust only."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time

from frozen_sqlite_anchors import CAPTURES

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/rust-port/sqlite"
sys.path.insert(0, str(HELPER))
import candidate
import diff
import generate
import typed_contract


def native_target():
    goos = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}[platform.system()]
    goarch = {"arm64": "arm64", "aarch64": "arm64", "amd64": "amd64", "x86_64": "amd64"}[platform.machine().lower()]
    return goos + "-" + goarch


def read_capture(target, alternate=None):
    registration = CAPTURES[target]
    path = ROOT / registration["report"] if alternate is None else alternate
    if path.is_symlink() or not path.is_file():
        raise ValueError("frozen SQLite report must be a regular file")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != registration["report_sha256"]:
        raise ValueError("frozen SQLite report does not match the fixed reviewed anchor")
    record = json.loads(raw)
    manifest_path = ROOT / registration["manifest"]
    manifest_raw = manifest_path.read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != registration["manifest_sha256"]:
        raise ValueError("original SQLite capture manifest bytes changed")
    manifest = json.loads(manifest_raw)
    manifest_digest = hashlib.sha256(manifest_raw).hexdigest()
    generate.validate(record["go"])
    diff.validate_oracle_provenance(record["go"])
    state = record["go"]["cases"][0]["state"]
    if state["native_goos"] + "-" + state["native_goarch"] != target:
        raise ValueError("frozen SQLite Go capture native identity mismatch")
    verdict = typed_contract.apply(record["go"], record["rust"],
                                   diff.evaluate(record["go"], record["rust"], manifest, manifest_digest))
    if verdict != record["verdict"] or verdict["status"] != "passed":
        raise ValueError("original native SQLite verdict cannot be reconstructed")
    return raw, record


def isolated_rust_env(root):
    env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE") if key in os.environ}
    env.update(LC_ALL="C", LANG="C", TZ="UTC")
    for key, name in {"HOME": "home", "USERPROFILE": "home", "APPDATA": "config", "LOCALAPPDATA": "data",
                      "XDG_CONFIG_HOME": "config", "XDG_DATA_HOME": "data", "XDG_CACHE_HOME": "cache",
                      "XDG_STATE_HOME": "state", "TMPDIR": "tmp", "TMP": "tmp", "TEMP": "tmp"}.items():
        directory = root / name
        directory.mkdir(mode=0o700, exist_ok=True)
        env[key] = str(directory)
    return env


def rust_capture(manifest):
    candidate.validate_base(manifest)
    before = candidate.snapshot()
    if candidate.enforced(before) != candidate.enforced(manifest["source_hashes"]):
        raise ValueError("SQLite candidate source differs from the accepted frozen manifest")
    target = (ROOT / "target").resolve()
    env = dict(os.environ, CARGO_TARGET_DIR=str(target), CARGO_NET_OFFLINE="true")
    metadata = json.loads(generate.run(["cargo", "metadata", "--offline", "--locked", "--no-deps", "--format-version", "1"], cwd=ROOT, env=env))
    package = next(p for p in metadata["packages"] if p["name"] == "symaira-core-sqlite")
    if Path(metadata["workspace_root"]).resolve() != ROOT or Path(package["manifest_path"]).resolve() != ROOT / "rust/symaira-core-sqlite/Cargo.toml":
        raise ValueError("Cargo selected a different SQLite candidate")
    generate.run(["cargo", "build", "--offline", "--locked", "-p", "symaira-core-sqlite", "--example", "sqlite-observe"], cwd=ROOT, env=env, timeout=300)
    binary = target / "debug/examples" / ("sqlite-observe.exe" if os.name == "nt" else "sqlite-observe")
    with tempfile.TemporaryDirectory(prefix="sqlite-frozen-rust-") as directory:
        sandbox = Path(directory)
        data = sandbox / "databases"
        data.mkdir(mode=0o700)
        start = int(time.time())
        raw = generate.run([str(binary), str(data), str(HELPER)], cwd=data, env=isolated_rust_env(sandbox), timeout=30)
        report = generate.normalize_temp_root(json.loads(raw), data)
        report["capture_interval"] = [start, int(time.time())]
    if candidate.snapshot() != before:
        raise ValueError("SQLite source changed during Rust execution")
    report.update(source_hashes=before, candidate_base=manifest["base"],
                  candidate_revision=generate.run(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
                  binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    return report, raw


def replay(output):
    target = native_target()
    raw_fixture, record = read_capture(target)
    manifest, manifest_digest = candidate.load()
    rust, raw_rust = rust_capture(manifest)
    rust["candidate_manifest_sha256"] = manifest_digest
    verdict = typed_contract.apply(record["go"], rust, diff.evaluate(record["go"], rust, manifest, manifest_digest))
    if verdict["status"] != "passed" or verdict["case_ids"] != generate.EXPECTED_IDS:
        raise ValueError("actual Rust differs from frozen native SQLite Go observations")
    mutated = copy.deepcopy(record["go"])
    mutated["cases"][0]["state"]["ping"] = not mutated["cases"][0]["state"]["ping"]
    negative = typed_contract.apply(mutated, rust, diff.evaluate(mutated, rust, manifest, manifest_digest))
    if negative["status"] == "passed" or not any(d["path"] == "SQL-001/ping" for d in negative["differences"]):
        raise ValueError("actual Rust comparison accepted mutated SQLite ping")
    if read_capture(target)[0] != raw_fixture:
        raise ValueError("original SQLite fixture changed during replay")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".rust.raw").write_bytes(raw_rust)
    report = {"status": "PASS", "native_target": target, "execution_head": rust["candidate_revision"],
              "case_count": 6, "checked_fields": len(verdict["checked_fields"]), "semantic_mutation_rejected": True,
              "fixture_sha256": hashlib.sha256(raw_fixture).hexdigest(), "verdict": verdict, "rust": rust}
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "native_target", "execution_head", "case_count", "checked_fields", "semantic_mutation_rejected")}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--fixture", type=Path, help="exercise the fixed-anchor boundary with an alternate raw file")
    parser.add_argument("--output", type=Path, default=ROOT / "target/sqlite-frozen-replay.json")
    args = parser.parse_args()
    if args.verify_only or args.fixture:
        read_capture(native_target(), args.fixture)
        print("PASS source-bound frozen native SQLite capture and reconstructed original verdict")
    else:
        replay(args.output)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(f"FAIL frozen SQLite replay: {error}", file=sys.stderr)
        raise SystemExit(1)
