#!/usr/bin/env python3
"""Shared Go-free replay and mutation controls for static update lanes."""

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

LANE_CONFIG = {
    "response": {"test": "response", "count": 1, "filter": None, "env": "RESPONSE_FIXTURE"},
    "install-method": {"test": "install_method", "count": 1, "filter": None, "env": "INSTALL_METHOD_FIXTURE"},
    "extract": {"test": "extract", "count": 2, "filter": None, "env": "EXTRACT_FIXTURE"},
    "swap": {"test": "swap", "count": 1, "filter": None, "env": "UPDATE_SWAP_FIXTURE"},
    "checker": {"test": "checker", "count": 5, "filter": None, "env": "UPDATE_CHECKER_FIXTURE"},
}


def _data(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key != "capture"}


def _rust(lane: str, fixture: Path, filter_name: str | None = None) -> subprocess.CompletedProcess:
    spec = LANE_CONFIG[lane]
    env = dict(os.environ)
    env[spec["env"]] = str(fixture)
    env["CARGO_TARGET_DIR"] = str(ROOT / "target")
    command = ["cargo", "test", "--manifest-path", str(MANIFEST), "--test", spec["test"], "--locked"]
    if filter_name:
        command.append(filter_name)
    command.extend(["--", "--nocapture"])
    if filter_name:
        command.append("--exact")
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _require_positive(lane: str, result: subprocess.CompletedProcess) -> None:
    count = LANE_CONFIG[lane]["count"]
    expected = f"test result: ok. {count} passed; 0 failed; 0 ignored;"
    if result.returncode != 0 or expected not in result.stdout:
        raise RuntimeError(f"Rust {lane} replay failed or did not execute all {count} intended tests:\n{result.stdout}")


def _mutations(lane: str, source: dict) -> list[tuple[dict, str, str]]:
    mutations = []
    if lane == "response":
        changed = json.loads(json.dumps(source))
        changed["cases"][0]["result"] = {"code": "mutated-response"}
        mutations.append((changed, "case available-assets", "response"))
    elif lane == "install-method":
        changed = json.loads(json.dumps(source))
        changed["cases"][0]["method"] = "mutated-fixture"
        mutations.append((changed, "empty", "install method"))
    elif lane == "extract":
        changed = json.loads(json.dumps(source))
        changed["cases"][0]["files"][0]["content"] = "mutated"
        mutations.append((changed, "tar-success content", "extraction content"))
    elif lane == "swap":
        changed = json.loads(json.dumps(source))
        missing = next(case for case in changed["cases"] if case["input"]["id"] == "missing-source")
        missing["observation"]["target_content"] = "corrupted fixture"
        mutations.append((changed, "missing-source observation", "swap filesystem state"))
        changed = json.loads(json.dumps(source))
        rollback = next(case for case in changed["cases"] if case["input"]["id"] == "validation-rollback-failed")
        rollback["observation"]["error_prefix"] = "wrong rollback error family"
        mutations.append((changed, "validation-rollback-failed error family", "swap rollback error"))
        changed = json.loads(json.dumps(source))
        cleanup = next(case for case in changed["cases"] if case["input"]["id"] == "backup-cleanup-failed")
        cleanup["observation"]["backup_exists"] = False
        mutations.append((changed, "backup-cleanup-failed observation", "swap cleanup state"))
    elif lane == "checker":
        changed = json.loads(json.dumps(source))
        changed["observations"]["cases"][0]["results"][0]["release"]["Body"] += "-mutated"
        mutations.append((changed, "scenario metadata-newer", "checker public observation"))
    return mutations


def _require_rejection(lane: str, fixture: dict, expected_marker: str, label: str) -> None:
    with tempfile.TemporaryDirectory(prefix=f"static-update-{lane}-negative-") as directory:
        path = Path(directory) / "mutated.json"
        path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
        filter_name = "public_checker_injected_corpus_matches_go" if lane == "checker" else None
        result = _rust(lane, path, filter_name)
    if result.returncode == 0 or "test result: FAILED" not in result.stdout or expected_marker not in result.stdout:
        raise RuntimeError(f"{lane} mutation was not rejected by the intended Rust assertion ({label}):\n{result.stdout}")


def main_for_lane(lane: str, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Replay frozen Go {lane} observations against actual Rust production tests.")
    parser.add_argument("--check", action="store_true", help="check frozen observations and execute Rust (the default)")
    parser.add_argument("--negative-control", action="store_true", help="run intended Rust observation mutation controls (included by default)")
    parser.add_argument("--write", action="store_true", help="deprecated alias requiring --capture-output and GO_ORACLE=1")
    parser.add_argument("--capture-output", type=Path, help="capture a new additive candidate; existing files are never overwritten")
    parser.add_argument("--artifacts-dir", type=Path, help="required raw Go output directory for recapture")
    args = parser.parse_args(argv)
    if args.write and args.capture_output is None:
        parser.error("--write cannot replace historical fixtures; use --capture-output <new-path> with GO_ORACLE=1")
    if args.capture_output is not None:
        if args.artifacts_dir is None or os.environ.get("GO_ORACLE") != "1":
            parser.error("--capture-output requires --artifacts-dir and GO_ORACLE=1")
        candidate, capture, evidence = oracle.capture_go(lane, args.artifacts_dir)
        output = args.capture_output.resolve()
        if output.exists():
            raise FileExistsError(f"refusing to overwrite capture candidate: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(candidate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"CAPTURE {lane} {capture['case_count']} {capture['go']['goos']}/{capture['go']['goarch']} candidate={output} evidence={evidence}")
        return 0

    frozen_path = oracle.fixture_path(lane)
    frozen = oracle.validate_capture(lane, frozen_path)
    if os.environ.get("GO_ORACLE") == "1":
        if args.artifacts_dir is None:
            parser.error("GO_ORACLE=1 requires --artifacts-dir so raw success/failure evidence is retained")
        fresh, _, _ = oracle.capture_go(lane, args.artifacts_dir)
        if _data(fresh) != _data(frozen):
            raise ValueError(f"fresh pinned Go {lane} observations disagree with the frozen capture")
    positive = _rust(lane, frozen_path)
    _require_positive(lane, positive)
    controls = _mutations(lane, frozen)
    if not controls:
        raise RuntimeError(f"no intended mutation controls are defined for {lane}")
    for mutated, marker, label in controls:
        _require_rejection(lane, mutated, marker, label)
    test_count = LANE_CONFIG[lane]["count"]
    print(f"PASS frozen Go {lane} oracle: {oracle.LANES[lane]['count']} observations; Rust tests={test_count}; intended mutation controls={len(controls)}")
    return 0
