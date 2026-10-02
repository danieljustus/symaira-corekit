#!/usr/bin/env python3
"""Execute FS-001-RUST-STRICT-v1 against fresh pinned public Go observations."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from generate_fs_secret import ORACLE, ROOT, build_oracle, source_digest


def command(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result


def main() -> None:
    env = os.environ.copy()
    env.update(GOTOOLCHAIN="go1.26.6", CGO_ENABLED="0")
    modules = command(["go", "env", "GOMODCACHE"], env).stdout.strip()
    env.update(CARGO_HOME=env.get("CARGO_HOME", str(Path.home() / ".cargo")),
               RUSTUP_HOME=env.get("RUSTUP_HOME", str(Path.home() / ".rustup")))
    target = ROOT / "target"
    target.mkdir(exist_ok=True)
    env["CARGO_TARGET_DIR"] = str(target)
    with tempfile.TemporaryDirectory(prefix="fs path controls ", dir=target) as raw:
        directory = Path(raw)
        for name in ("home", "cache", "tmp", "go-cache"):
            (directory / name).mkdir()
        env.update(HOME=str(directory / "home"), USERPROFILE=str(directory / "home"),
                   XDG_CACHE_HOME=str(directory / "cache"), TMPDIR=str(directory / "tmp"),
                   TMP=str(directory / "tmp"), TEMP=str(directory / "tmp"),
                   GOTMPDIR=str(directory / "tmp"), GOCACHE=str(directory / "go-cache"), GOMODCACHE=modules)
        os.environ.update(env)
        build_oracle(directory)
        binary = directory / ("fssecret.exe" if os.name == "nt" else "fssecret")
        observed = json.loads(command([str(binary), "--path-controls"], env).stdout)
        keys = ["0000", "001f", "0020", "007e", "007f", "0080", "0085", "009f", "00a0"]
        if sorted(observed) != keys or any(type(value) is not bool for value in observed.values()):
            raise RuntimeError("protocol-invalid public Go recording")
        metadata = json.loads(command(["cargo", "metadata", "--offline", "--locked", "--no-deps", "--format-version", "1", "--manifest-path", str(ROOT / "Cargo.toml")], env).stdout)
        if Path(metadata["workspace_root"]).resolve() != ROOT.resolve() or Path(metadata["target_directory"]).resolve() != target.resolve():
            raise RuntimeError("candidate execution root mismatch")
        test = ["cargo", "test", "--locked", "--manifest-path", str(ROOT / "Cargo.toml"), "-p", "symaira-core-fs", "--test", "parity", "fs001_strict_v1_replays_go_controls", "--", "--exact", "--ignored", "--nocapture"]
        env["RUST_FS_GO_PATH_CONTROLS"] = "\n".join(f"{key}\t{str(observed[key]).lower()}" for key in keys)
        replay = command(test, env)
        if "test result: ok. 1 passed; 0 failed; 0 ignored;" not in replay.stdout:
            raise RuntimeError("Rust did not execute the live Go replay")
        mutated = dict(observed)
        mutated["007f"] = not mutated["007f"]
        env["RUST_FS_GO_PATH_CONTROLS"] = "\n".join(f"{key}\t{str(mutated[key]).lower()}" for key in keys)
        negative = subprocess.run(test, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
        if not negative.returncode or "Go must actually accept the versioned control case" not in negative.stdout + negative.stderr:
            raise RuntimeError("actual mutation was not rejected at the contract boundary")
        report = {"schema_version": 1, "contract": "FS-001-RUST-STRICT-v1", "oracle_commit": ORACLE,
                  "go_source_sha256": source_digest(), "helper_sha256": hashlib.sha256((ROOT / "scripts/rust-port/go-oracle/cmd/fssecret/main.go").read_bytes()).hexdigest(),
                  "head_sha": command(["git", "rev-parse", "HEAD"], env).stdout.strip(),
                  "go": observed, "rust_command": test, "rust_exit_code": replay.returncode,
                  "rust_stdout": replay.stdout, "mutated_key": "007f", "negative_exit_code": negative.returncode}
        (target / "fs-path-control-native.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("PASS FS-001-RUST-STRICT-v1: nine actual public Go cases, Rust replay and real mutation rejection")


if __name__ == "__main__":
    main()
