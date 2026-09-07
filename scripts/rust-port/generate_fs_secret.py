#!/usr/bin/env python3
"""Generate RUST-003 corpus from a pinned, executable Go oracle.

The output is deterministic: host target labels are deliberately normalized;
behavioural rows are never hand-authored. ``--check`` regenerates in a fresh
oracle checkout and rejects stale or manipulated bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/rust-port/go-oracle"
OUT = ROOT / "testdata/rust-port/fixtures/fs-secret/corpus.json"
ORACLE = "f3d3eb79b9b1f31b4f973d2ed518a8292cedf588"
IDS = [*(f"FS-{n:03}" for n in range(1, 8)), *(f"SEC-{n:03}" for n in range(1, 7))]
SOURCE_FILES = ("fsutil/pathutil.go", "fsutil/atomicwrite.go", "fsutil/safewrite.go", "secretref/secretref.go", "secretref/symvault.go")


def run(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> bytes:
    completed = subprocess.run(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode("utf-8", "replace"))
    return completed.stdout


def source_digest() -> str:
    digest = hashlib.sha256()
    for name in SOURCE_FILES:
        data = run(["git", "show", f"{ORACLE}:{name}"], ROOT)
        digest.update(name.encode() + b"\0" + data)
    return digest.hexdigest()


def build_oracle(root: Path) -> dict:
    oracle = root / "oracle"
    oracle.mkdir()
    archive = subprocess.Popen(["git", "archive", "--format=tar", ORACLE], cwd=ROOT, stdout=subprocess.PIPE)
    assert archive.stdout is not None
    with tarfile.open(fileobj=archive.stdout, mode="r|") as tar:
        tar.extractall(oracle, filter="data")
    if archive.wait() != 0:
        raise RuntimeError("git archive failed")
    modfile = root / "oracle.mod"
    modfile.write_text((HELPER / "go.mod").read_text().replace("../../..", oracle.as_posix()), encoding="utf-8")
    shutil.copy2(HELPER / "go.sum", root / "oracle.sum")
    binary = root / ("fssecret.exe" if os.name == "nt" else "fssecret")
    env = os.environ.copy()
    env.update({"CGO_ENABLED": "0", "GOTOOLCHAIN": "go1.26.6"})
    run(["go", "build", "-trimpath", "-modfile", str(modfile), "-o", str(binary), "./cmd/fssecret"], HELPER, env)
    return json.loads(run([str(binary)], ROOT, env))


def normalize_probe(probe: dict, target: str | None = None) -> dict:
    probe = json.loads(json.dumps(probe))
    if target is None:
        probe.pop("native_target", None)
    else:
        probe["native_target"] = target
    for identifier in ("SEC-005", "SEC-006"):
        if identifier in probe["cases"]:
            probe["cases"][identifier]["platform"] = target or "${TARGET_OS}"
    return probe


def generate(target: str | None = None) -> dict:
    if target is not None:
        actual = {"darwin": "darwin", "linux": "linux", "windows": "win32"}[target]
        if sys.platform != actual:
            raise SystemExit(f"refusing to label {sys.platform} as native {target}")
    with tempfile.TemporaryDirectory(prefix="rust003-oracle-") as raw:
        probe = normalize_probe(build_oracle(Path(raw)), target)
    result = {
        "schema_version": 2,
        "oracle": {
            "commit": ORACLE,
            "source_sha256": source_digest(),
            "generator": "scripts/rust-port/generate_fs_secret.py",
            "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        "native_targets": ["darwin-amd64", "darwin-arm64", "linux-amd64", "linux-arm64", "windows-amd64", "windows-arm64"],
        "contract_ids": IDS,
        "probe": probe,
    }
    if target is not None:
        result["native_target"] = target
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--target", choices=["darwin", "linux", "windows"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or (ROOT / f"testdata/rust-port/fixtures/fs-secret/corpus-{args.target}.json" if args.target else OUT)
    generated = json.dumps(generate(args.target), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        actual = output.read_text(encoding="utf-8")
        if actual != generated:
            raise SystemExit("FAIL RUST-003 corpus is stale or manipulated; regenerate deliberately")
        print(f"PASS RUST-003 generated corpus ({len(IDS)} production-backed rows)")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(generated, encoding="utf-8")
        print(f"WROTE {output} ({len(IDS)} production-backed rows, oracle {ORACLE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
