#!/usr/bin/env python3
"""Compare the native Go oracle with the native Rust probe."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORACLE_DIR = ROOT / "scripts/rust-port/go-oracle"
RUST_BIN = ROOT / "target/debug" / ("rust-fs-secret.exe" if os.name == "nt" else "rust-fs-secret")
ORACLE = "f3d3eb79b9b1f31b4f973d2ed518a8292cedf588"
IDS = [*(f"FS-{n:03}" for n in range(1, 8)), *(f"SEC-{n:03}" for n in range(1, 7))]


def run(args: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> bytes:
    completed = subprocess.run(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode("utf-8", "replace"))
    return completed.stdout


def normalized(value: dict) -> dict:
    value = json.loads(json.dumps(value))
    native_target = str(value.get("native_target", ""))
    value.pop("native_target", None)
    for case in value.get("cases", {}).values():
        if "platform" in case:
            case["platform"] = "${TARGET_OS}"
        if native_target.startswith("windows"):
            # Windows does not expose POSIX permission bits through Rust's
            # metadata API. Mode values are not a portable Windows observable.
            case.pop("mode", None)
            for entry in case.get("files", []):
                entry.pop("mode", None)
    return value


def main() -> int:
    # Always ask Cargo to refresh the probe. Reusing an existing binary can
    # silently compare the Go oracle against stale Rust source.
    run(["cargo", "build", "-q", "--bin", "rust-fs-secret", "--locked"])
    with tempfile.TemporaryDirectory(prefix="rust003-diff-") as raw:
        helper = Path(raw)
        mode_file = helper / "mode"
        argv_file = helper / "argv.json"
        mode_file.write_text("success", encoding="utf-8")
        for name in ("symvault", "security"):
            target = helper / (name + (".exe" if os.name == "nt" else ""))
            shutil.copy2(RUST_BIN, target)
            target.chmod(target.stat().st_mode | stat.S_IXUSR)
        env = os.environ.copy()
        env["PATH"] = str(helper) + os.pathsep + env.get("PATH", "")
        env["RUST003_HELPER_MODE_FILE"] = str(mode_file)
        env["RUST003_HELPER_ARGV"] = str(argv_file)
        rust = normalized(json.loads(run([str(RUST_BIN)], env=env)))
        from generate_fs_secret import build_oracle, normalize_probe
        with tempfile.TemporaryDirectory(prefix="rust003-go-") as oracle_raw:
            target = "windows" if os.name == "nt" else ("darwin" if sys.platform == "darwin" else "linux")
            go = normalized(normalize_probe(build_oracle(Path(oracle_raw)), target))
        expected = {"oracle_commit": ORACLE, "cases": go["cases"]}
        actual = {"oracle_commit": rust["oracle_commit"], "cases": rust["cases"]}
        if actual != expected:
            print(json.dumps({"go": expected, "rust": actual}, indent=2, sort_keys=True))
            raise SystemExit("FAIL Go/Rust normalized observable mismatch")
        if sorted(actual["cases"]) != IDS:
            raise SystemExit("FAIL differential runner did not execute every FS/SEC row")
        print(f"PASS Go/Rust differential ({len(IDS)} complete observable rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
