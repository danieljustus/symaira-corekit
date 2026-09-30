#!/usr/bin/env python3
"""Record Go update-cache behavior and replay it in the Rust crate."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "testdata/rust-port/fixtures/update/cache.json"
ORACLE = ROOT / "scripts/rust-port/update-cache-oracle/main.go"
SOURCE = ROOT / "updatecheck/updatecheck.go"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observe_go():
    output = subprocess.run(
        ["go", "run", "./scripts/rust-port/update-cache-oracle"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout
    observed = json.loads(output)
    if len(observed["cases"]) != 7:
        raise ValueError("cache oracle did not execute all 7 observations")
    return {
        "go_source_sha256": digest(SOURCE),
        "oracle_sha256": digest(ORACLE),
        **observed,
    }


def compare(observed, fixture_path):
    return observed == json.loads(fixture_path.read_text(encoding="utf-8"))


def observe_go_persistence():
    previous_umask = os.umask(0o022) if os.name == "posix" else None
    try:
        output = subprocess.run(
            ["go", "run", "./scripts/rust-port/update-cache-persistence-oracle"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        ).stdout
    finally:
        if previous_umask is not None:
            os.umask(previous_umask)
    observed = json.loads(output)
    expected = {"normal", "duplicate-tag-casefold", "trailing-json", "atomic-replace"}
    actual = {case["id"] for case in observed["cases"]}
    if actual != expected or len(observed["cases"]) != len(expected):
        raise ValueError(f"Go persistence oracle cases {actual!r}, expected {expected!r}")
    return observed


def run_live_persistence_differential():
    observed = observe_go_persistence()
    with tempfile.TemporaryDirectory(prefix="update-cache-live-") as directory:
        fixture_path = Path(directory) / "go-persistence.json"
        fixture_path.write_text(json.dumps(observed), encoding="utf-8")
        env = os.environ.copy()
        env["COREKIT_UPDATE_CACHE_LIVE"] = str(fixture_path)
        previous_umask = os.umask(0o022) if os.name == "posix" else None
        try:
            subprocess.run(
                ["cargo", "test", "-p", "symaira-core-update", "--test",
                 "cache_persistence", "--locked", "--", "--nocapture"],
                cwd=ROOT, env=env, check=True,
            )
        finally:
            if previous_umask is not None:
                os.umask(previous_umask)
    print("PASS live Go/Rust update-cache persistence differential: 4 observations")


def run_live_persistence_negative_control():
    observed = observe_go_persistence()
    if not observed["cases"][0].get("cache_bytes"):
        raise ValueError("Go persistence oracle has no cache bytes to mutate")

    with tempfile.TemporaryDirectory(prefix="update-cache-live-negative-") as directory:
        fixture_path = Path(directory) / "go-persistence-mutated.json"
        env = os.environ.copy()
        env["COREKIT_UPDATE_CACHE_LIVE"] = str(fixture_path)
        previous_umask = os.umask(0o022) if os.name == "posix" else None
        try:
            command = [
                "cargo", "test", "-p", "symaira-core-update", "--test",
                "cache_persistence", "live_cache_persistence_matches_public_go_checker",
                "--locked", "--", "--exact", "--nocapture",
            ]
            fixture_path.write_text(json.dumps(observed), encoding="utf-8")
            subprocess.run(command, cwd=ROOT, env=env, check=True)
            mutated = copy.deepcopy(observed)
            mutated["cases"][0]["cache_bytes"] += " mutated"
            fixture_path.write_text(json.dumps(mutated), encoding="utf-8")
            result = subprocess.run(
                command, cwd=ROOT, env=env, capture_output=True, text=True,
            )
            if result.returncode == 0:
                raise SystemExit("FAIL Rust accepted mutated live cache_bytes")
            if "timestamp-normalized cache bytes" not in result.stdout + result.stderr:
                raise SystemExit(
                    "FAIL mutated live observation failed for an unrelated reason:\n"
                    + result.stdout + result.stderr
                )
        finally:
            if previous_umask is not None:
                os.umask(previous_umask)
    print("PASS Rust live persistence gate rejects mutated cache_bytes")


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="regenerate fixture from public Go API")
    mode.add_argument("--negative-control", action="store_true", help="prove a mutated fixture is rejected")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args()
    observed = observe_go()
    if args.write:
        args.fixture.parent.mkdir(parents=True, exist_ok=True)
        args.fixture.write_text(json.dumps(observed, indent=2) + "\n", encoding="utf-8")
        print(f"PASS wrote {len(observed['cases'])} Go cache observations")
        return
    if args.negative_control:
        mutated = copy.deepcopy(observed)
        mutated["cases"][0]["requests"] += 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutated.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            if compare(observed, path):
                raise SystemExit("FAIL mutated fixture was accepted")
        print("PASS mutated fixture rejected")
        run_live_persistence_negative_control()
        return
    if not compare(observed, args.fixture):
        print(json.dumps({"observed": observed, "fixture": json.loads(
            args.fixture.read_text(encoding="utf-8"))}, indent=2), file=sys.stderr)
        raise SystemExit("FAIL Go cache oracle disagrees with committed fixture")
    subprocess.run(
        ["cargo", "test", "-p", "symaira-core-update", "--test", "cache", "--locked"],
        cwd=ROOT, check=True,
    )
    print(f"PASS Go/Rust update-cache differential: {len(observed['cases'])} observations")
    run_live_persistence_differential()


if __name__ == "__main__":
    main()
