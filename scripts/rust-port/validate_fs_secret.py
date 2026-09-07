#!/usr/bin/env python3
"""Validate RUST-003 provenance, generated coverage, and crate policy."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORACLE = "f3d3eb79b9b1f31b4f973d2ed518a8292cedf588"
IDS = [*(f"FS-{n:03}" for n in range(1, 8)), *(f"SEC-{n:03}" for n in range(1, 7))]
SOURCE_FILES = ("fsutil/pathutil.go", "fsutil/atomicwrite.go", "fsutil/safewrite.go", "secretref/secretref.go", "secretref/symvault.go")


def source_digest() -> str:
    digest = hashlib.sha256()
    for name in SOURCE_FILES:
        data = subprocess.run(["git", "show", f"{ORACLE}:{name}"], cwd=ROOT, check=True, stdout=subprocess.PIPE).stdout
        digest.update(name.encode() + b"\0" + data)
    return digest.hexdigest()


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["darwin", "linux", "windows"])
    parser.add_argument("--corpus", type=Path)
    args = parser.parse_args()
    path = args.corpus or (ROOT / f"testdata/rust-port/fixtures/fs-secret/corpus-{args.target}.json" if args.target else ROOT / "testdata/rust-port/fixtures/fs-secret/corpus.json")
    corpus = json.loads(path.read_text(encoding="utf-8"))
    if args.target is not None:
        if corpus.get("native_target") != args.target or corpus.get("probe", {}).get("native_target") != args.target:
            raise SystemExit("FAIL native fixture target provenance")
    oracle = corpus.get("oracle", {})
    if oracle.get("commit") != ORACLE:
        raise SystemExit("FAIL corpus oracle provenance")
    if oracle.get("source_sha256") != source_digest():
        raise SystemExit("FAIL corpus production-source digest")
    generator = ROOT / "scripts/rust-port/generate_fs_secret.py"
    check_command = [sys.executable, str(generator), "--check"]
    if args.target is not None:
        check_command.extend(["--target", args.target, "--output", str(path)])
    generated = subprocess.run(
        check_command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if generated.returncode:
        raise SystemExit("FAIL corpus bytes are stale or manipulated")
    if oracle.get("generator") != "scripts/rust-port/generate_fs_secret.py":
        raise SystemExit("FAIL corpus generator provenance")
    if oracle.get("generator_sha256") != hashlib.sha256(generator.read_bytes()).hexdigest():
        raise SystemExit("FAIL corpus generator digest")
    if corpus.get("contract_ids") != IDS:
        raise SystemExit("FAIL corpus contract coverage")
    probe = corpus.get("probe", {})
    if probe.get("oracle_commit") != ORACLE or sorted(probe.get("cases", {})) != sorted(IDS):
        raise SystemExit("FAIL corpus executable probe coverage")
    for identifier in IDS:
        case = probe["cases"][identifier]
        if not case.get("outcomes"):
            raise SystemExit(f"FAIL {identifier} has no observable outcomes")
    contract = (ROOT / "contracts/secret_refs.json").read_bytes()
    crate_contract = (ROOT / "rust/symaira-core-secretref/contracts/secret_refs.json").read_bytes()
    if contract != crate_contract:
        raise SystemExit("FAIL secret_refs.json drift")
    for crate in ("symaira-core-fs", "symaira-core-secretref"):
        manifest = (ROOT / "rust" / crate / "Cargo.toml").read_text(encoding="utf-8")
        if "publish = false" not in manifest:
            raise SystemExit(f"FAIL {crate} must remain independent publish=false")
    print(f"PASS RUST-003 provenance and coverage ({len(IDS)} production-backed rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
