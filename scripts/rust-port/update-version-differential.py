#!/usr/bin/env python3
"""Replay the frozen stable-version Go observations through Rust."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "rust/symaira-core-update/Cargo.toml"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import static_update_oracle as oracle  # noqa: E402
from bounded_oracle_process import run_checked  # noqa: E402

LANE = "version"
TEST = "stable_release_decisions_match_public_go_checker"
POSITIVE_RESULT = "test result: ok. 1 passed; 0 failed; 0 ignored;"


def replay(fixture: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, UPDATE_VERSION_FIXTURE=str(fixture.resolve()), CARGO_TARGET_DIR=str(ROOT / "target"))
    command = ["cargo", "test", "--manifest-path", str(MANIFEST), "--test", "parity", TEST, "--locked", "--", "--exact", "--nocapture"]
    result = run_checked(
        command,
        cwd=ROOT,
        env=env,
        timeout=600,
        merge_stderr=True,
        artifact_dir=ROOT / "target/static-update-process",
    )
    return subprocess.CompletedProcess(command, result.returncode, result.stdout.decode("utf-8", "replace"), "")


def require_positive(result: subprocess.CompletedProcess) -> None:
    if result.returncode != 0 or POSITIVE_RESULT not in result.stdout:
        raise RuntimeError("Rust stable-version replay failed or ran zero intended tests:\n" + result.stdout)


def reject_mutation(source: dict) -> None:
    mutated = json.loads(json.dumps(source))
    mutated["cases"][4]["available"] = not mutated["cases"][4]["available"]
    with tempfile.TemporaryDirectory(prefix="upd001-negative-") as directory:
        path = Path(directory) / "mutated.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        result = replay(path)
    marker = "stable-version-005 available"
    if result.returncode == 0 or marker not in result.stdout:
        raise RuntimeError("stable-version expected-observation mutation was not rejected at its Rust assertion:\n" + result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="check frozen observations and run Rust (the default)")
    parser.add_argument("--negative-control", action="store_true", help="also require intended Rust assertion rejection (already included by default)")
    parser.add_argument("--write", action="store_true", help="deprecated alias requiring --capture-output and GO_ORACLE=1")
    parser.add_argument("--capture-output", type=Path, help="write a new additive Go candidate; never overwrites a capture")
    parser.add_argument("--artifacts-dir", type=Path, help="required raw-capture evidence directory for recapture")
    args = parser.parse_args()
    if args.write and args.capture_output is None:
        parser.error("--write cannot replace the historical fixture; use --capture-output <new-path> with GO_ORACLE=1")
    if args.capture_output is not None:
        if args.artifacts_dir is None or os.environ.get("GO_ORACLE") != "1":
            parser.error("--capture-output requires --artifacts-dir and GO_ORACLE=1")
        payload, capture, evidence = oracle.capture_go(LANE, args.artifacts_dir)
        output = args.capture_output.resolve()
        if output.exists():
            raise FileExistsError(f"refusing to overwrite capture candidate: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"CAPTURE {LANE} {capture['case_count']} {capture['go']['goos']}/{capture['go']['goarch']} candidate={output} evidence={evidence}")
        return 0

    path = oracle.fixture_path(LANE)
    expected = oracle.validate_capture(LANE, path)
    if os.environ.get("GO_ORACLE") == "1":
        if args.artifacts_dir is None:
            parser.error("GO_ORACLE=1 requires --artifacts-dir so raw success/failure evidence is retained")
        observed, _, _ = oracle.capture_go(LANE, args.artifacts_dir)
        if {key: value for key, value in observed.items() if key != "capture"} != {key: value for key, value in expected.items() if key != "capture"}:
            raise ValueError("fresh pinned Go stable-version observations disagree with the frozen capture")
    result = replay(path)
    require_positive(result)
    reject_mutation(expected)
    print(f"PASS frozen Go stable-version oracle: {len(expected['cases'])} cases; actual Rust replay and intended mutation rejection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
