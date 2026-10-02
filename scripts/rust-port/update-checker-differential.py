#!/usr/bin/env python3
"""Regenerate REAL public Go Checker observations and replay against Rust.

Errors are compared verbatim, as in the response harness. This corpus uses
portable release/status errors; it does not normalize JSON decoder messages or
claim the existing request harness's native TLS/timeout classifications anew.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "rust/symaira-core-update/Cargo.toml"
TARGET = ROOT / "target"
FIXTURE = ROOT / "testdata/rust-port/fixtures/update/checker.json"
ORACLE = ROOT / "scripts/rust-port/update-checker-oracle/main.go"
SOURCE = ROOT / "updatecheck/updatecheck.go"


def run(command, env, capture=False):
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=capture, check=False)
    if result.returncode:
        raise RuntimeError(f"exit {result.returncode}: {' '.join(map(str, command))}\n{result.stdout or ''}\n{result.stderr or ''}")
    return result.stdout if capture else None


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(path, directory, injected=False):
    env = dict(os.environ, CARGO_TARGET_DIR=str(TARGET), UPDATE_CHECKER_FIXTURE=str(path),
               HOME=str(directory / "home"), USERPROFILE=str(directory / "home"), XDG_CACHE_HOME=str(directory / "cache"), TMPDIR=str(directory / "tmp"))
    for name in ("home", "cache", "tmp"):
        (directory / name).mkdir(parents=True, exist_ok=True)
    # rustup resolves toolchains before HOME isolation; preserve its existing roots.
    env.setdefault("RUSTUP_HOME", str(Path.home() / ".rustup"))
    env.setdefault("CARGO_HOME", str(Path.home() / ".cargo"))
    command = ["cargo", "test", "--offline", "--locked", "--manifest-path", str(MANIFEST), "--test", "checker"]
    if injected:
        command += ["public_checker_injected_corpus_matches_go", "--", "--exact", "--nocapture"]
    else:
        command += ["--", "--nocapture"]
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    expected_count = 1 if injected else 5
    if result.returncode == 0 and f"test result: ok. {expected_count} passed; 0 failed; 0 ignored;" not in result.stdout:
        raise RuntimeError("expected nonzero intended Checker tests:\n" + result.stdout)
    return result, env


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args()
    candidate_env = dict(os.environ, CARGO_TARGET_DIR=str(TARGET))
    metadata = json.loads(run(["cargo", "metadata", "--offline", "--locked", "--no-deps", "--format-version", "1", "--manifest-path", str(MANIFEST)], candidate_env, True))
    if Path(metadata["workspace_root"]).resolve() != ROOT or Path(metadata["target_directory"]).resolve() != TARGET:
        raise RuntimeError("cargo paths escaped registered candidate")
    # Resolve the real compiler and module cache BEFORE disposable HOME isolation.
    sdk = Path.home() / "sdk/go1.26.6/bin/go"
    launcher = os.environ.get("UPDATE_CHECKER_GO") or (str(sdk) if sdk.is_file() else shutil.which("go"))
    original_go_env = dict(os.environ, GOTOOLCHAIN="go1.26.6")
    goroot = run([launcher, "env", "GOROOT"], original_go_env, True).strip()
    modules = run([launcher, "env", "GOMODCACHE"], original_go_env, True).strip()
    compiler = str(Path(goroot) / "bin/go")
    version = run([compiler, "version"], dict(os.environ, GOTOOLCHAIN="local"), True).strip()
    if not version.startswith("go version go1.26.6 "):
        raise RuntimeError("oracle requires go1.26.6: " + version)
    with tempfile.TemporaryDirectory(prefix="checker-gate-", dir=ROOT) as temp:
        temp = Path(temp)
        env = dict(os.environ, GOTOOLCHAIN="local", CGO_ENABLED="0", GOCACHE=str(TARGET / "checker-go-cache"),
                   GOMODCACHE=modules, GOPROXY="off", GOSUMDB="off")
        binary = temp / "oracle"
        run([compiler, "build", "-o", str(binary), "./scripts/rust-port/update-checker-oracle"], env)
        for name in ("home", "cache", "tmp"):
            (temp / name).mkdir()
        env.update(HOME=str(temp / "home"), USERPROFILE=str(temp / "home"), XDG_CACHE_HOME=str(temp / "cache"), TMPDIR=str(temp / "tmp"))
        observations = json.loads(run([str(binary)], env, True))
        if len(observations["cases"]) != 21 or any(not c["results"] for c in observations["cases"]):
            raise RuntimeError("incomplete Go corpus")
        observed = {"go_source_sha256": digest(SOURCE), "oracle_sha256": digest(ORACLE), "observations": observations}
        if args.write:
            args.fixture.write_text(json.dumps(observed, indent=2) + "\n")
            print("PASS wrote 21 real public Go Checker scenarios")
            return
        committed = json.loads(args.fixture.read_text())
        if observed != committed:
            raise RuntimeError("fresh public Go observations disagree with fixture (no rewrite in --check)")
        injected_result, rust_env = replay(args.fixture, temp / "injected", injected=True)
        if injected_result.returncode:
            raise RuntimeError(injected_result.stdout)
        print("PASS 21 public Go scenarios replayed with injected transport")
        mutated = json.loads(json.dumps(committed))
        mutated["observations"]["cases"][0]["results"][0]["release"]["Body"] += "-mutated"
        mutation = temp / "mutated.json"
        mutation.write_text(json.dumps(mutated))
        negative, _ = replay(mutation, temp / "negative", injected=True)
        if negative.returncode == 0 or "scenario metadata-newer" not in negative.stdout:
            raise RuntimeError("fixture mutation was not rejected by intended assertion:\n" + negative.stdout)
        print("PASS actual fixture mutation rejection")
        for xdg, key in (("relative-cache", "relative_xdg_path"), ("", "empty_xdg_path")):
            fallback_env = dict(rust_env, XDG_CACHE_HOME=xdg,
                                UPDATE_CHECKER_FALLBACK_PATH=str(Path(rust_env["HOME"]) / observations[key]))
            output = run(["cargo", "test", "--offline", "--locked", "--manifest-path", str(MANIFEST), "--test", "checker", "default_path_matches_go_home_fallback", "--", "--exact"], fallback_env, True)
            if "test result: ok. 1 passed; 0 failed; 0 ignored;" not in output:
                raise RuntimeError("HOME fallback test did not execute")
        print("PASS absolute/relative/empty XDG and HOME fallback")
        result, rust_env = replay(args.fixture, temp / "rust")
        if result.returncode:
            raise RuntimeError(result.stdout)
        print("PASS 21 real public Go Checker scenarios; five Rust tests executed")



if __name__ == "__main__":
    main()
