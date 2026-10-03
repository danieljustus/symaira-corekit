#!/usr/bin/env python3
"""Run Go-free update-oracle replays and explicit assertion mutation controls."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "rust/symaira-core-update/Cargo.toml"
TARGET_DIR = ROOT / "target"
TEMP_ROOT = TARGET_DIR / "static-update-tmp"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import static_update_oracle as oracle  # noqa: E402


def _run_rust(lane: str, fixture: Path, *, expected_tests: int | None = None) -> subprocess.CompletedProcess:
    spec = oracle.LANES[lane]
    target = spec["positive_tests"] if expected_tests is None else expected_tests
    env = dict(os.environ)
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    env[spec["fixture_env"]] = str(fixture)
    env["CARGO_TARGET_DIR"] = str(TARGET_DIR)
    env["CARGO_NET_OFFLINE"] = "true"
    env["TMPDIR"] = str(TEMP_ROOT)
    command = ["cargo", "test", "--manifest-path", str(MANIFEST), "--test", spec["rust_target"]]
    if lane != "extract":
        command.append(spec["rust_test"])
    command.extend(["--", "--nocapture"])
    if lane != "extract":
        command.append("--exact")
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=300,
        check=False,
    )
    summary = f"test result: ok. {target} passed; 0 failed; 0 ignored;"
    if result.returncode != 0 or summary not in result.stdout:
        raise RuntimeError(f"Rust {lane} replay failed or did not run exactly {target} intended tests:\n{result.stdout}")
    return result


def _mutations(lane: str, source: dict) -> list[tuple[dict, str]]:
    if lane == "version":
        changed = json.loads(json.dumps(source))
        case = next(case for case in changed["cases"] if case["available"] and not case["invalid_latest"])
        case["available"] = False
        return [(changed, f"{case['id']} available")]
    if lane == "response":
        changed = json.loads(json.dumps(source))
        changed["cases"][0]["result"] = {"code": "mutated-response"}
        return [(changed, f"case {changed['cases'][0]['id']}")]
    if lane == "install-method":
        changed = json.loads(json.dumps(source))
        changed["cases"][0]["method"] = "mutated-fixture"
        return [(changed, changed["cases"][0]["id"])]
    if lane == "extract":
        changed = json.loads(json.dumps(source))
        changed["cases"][0]["files"][0]["content"] = "mutated"
        return [(changed, f"{changed['cases'][0]['id']} content")]
    if lane == "swap":
        mutations = []
        changed = json.loads(json.dumps(source))
        missing = next(case for case in changed["cases"] if case["input"]["id"] == "missing-source")
        missing["observation"]["target_content"] = "corrupted fixture"
        mutations.append((changed, "missing-source observation"))
        changed = json.loads(json.dumps(source))
        rollback = next(case for case in changed["cases"] if case["input"]["id"] == "validation-rollback-failed")
        rollback["observation"]["error_prefix"] = "wrong rollback error family"
        mutations.append((changed, "validation-rollback-failed error family"))
        changed = json.loads(json.dumps(source))
        cleanup = next(case for case in changed["cases"] if case["input"]["id"] == "backup-cleanup-failed")
        cleanup["observation"]["backup_exists"] = not cleanup["observation"]["backup_exists"]
        mutations.append((changed, "backup-cleanup-failed observation"))
        return mutations
    raise ValueError(f"no expected-observation mutation exists for {lane}")


def _reject_expected_mutation(lane: str, mutated: dict, expected_marker: str) -> None:
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"static-update-{lane}-negative-", dir=TEMP_ROOT) as directory:
        path = Path(directory) / "mutated.json"
        path.write_text(json.dumps(mutated, ensure_ascii=False), encoding="utf-8")
        spec = oracle.LANES[lane]
        env = dict(os.environ)
        env[spec["fixture_env"]] = str(path)
        env["CARGO_TARGET_DIR"] = str(TARGET_DIR)
        env["CARGO_NET_OFFLINE"] = "true"
        env["TMPDIR"] = str(TEMP_ROOT)
        command = [
            "cargo", "test", "--manifest-path", str(MANIFEST), "--test", spec["rust_target"],
            spec["rust_test"], "--", "--exact", "--nocapture",
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
            check=False,
        )
    if result.returncode == 0 or "test result: FAILED" not in result.stdout or expected_marker not in result.stdout:
        raise RuntimeError(f"{lane} expected-observation mutation missed its intended Rust assertion ({expected_marker}):\n{result.stdout}")


def main_for_lane(lane: str, argv: list[str] | None = None) -> int:
    if lane not in oracle.LANES:
        raise ValueError(f"no static update runner for lane {lane}")
    spec = oracle.LANES[lane]
    parser = argparse.ArgumentParser(description=f"Go-free replay of static Go {lane} observations through Rust.")
    parser.add_argument("--check", action="store_true", help="check frozen observations and run Rust (default)")
    parser.add_argument("--negative-control", action="store_true", help="also mutate expected data and require the intended Rust assertion to fail")
    parser.add_argument("--fixture", type=Path, help="diagnostic fixture override; not accepted as a trusted capture")
    parser.add_argument("--write", action="store_true", help="deprecated; requires --capture-output and GO_ORACLE=1")
    parser.add_argument("--capture-output", type=Path, help="write a new Go capture candidate without replacing a trusted fixture")
    parser.add_argument("--artifacts-dir", type=Path, help="required raw-evidence directory for explicit Go execution")
    args = parser.parse_args(argv)
    if args.write and args.capture_output is None:
        parser.error("--write cannot overwrite historical observations; use --capture-output <new-path> with GO_ORACLE=1")
    if args.capture_output is not None:
        if os.environ.get("GO_ORACLE") != "1" or args.artifacts_dir is None:
            parser.error("--capture-output requires GO_ORACLE=1 and --artifacts-dir")
        output = args.capture_output.resolve()
        if not output.is_relative_to(ROOT):
            parser.error("capture candidates must be inside the assigned worktree")
        if output.exists():
            raise FileExistsError(f"refusing to overwrite candidate: {output}")
        fresh, capture, evidence_id = oracle.capture_go(lane, args.artifacts_dir)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(fresh, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"CAPTURE {lane} {capture['case_count']} {fresh['target']['goos']}/{fresh['target']['goarch']} candidate={output.relative_to(ROOT)} evidence={evidence_id}")
        return 0

    default_path = oracle.fixture_path(lane)
    if args.fixture is None:
        frozen_path = default_path
        frozen = oracle.validate_capture(lane, frozen_path)
    else:
        frozen_path = args.fixture.resolve()
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
        if frozen.get("lane") != lane or len(frozen.get("cases", [])) != spec["count"]:
            raise ValueError(f"diagnostic {lane} fixture has the wrong lane or case count")
    if os.environ.get("GO_ORACLE") == "1":
        if args.artifacts_dir is None:
            parser.error("GO_ORACLE=1 requires --artifacts-dir so raw success/failure evidence is retained")
        fresh, _, _ = oracle.capture_go(lane, args.artifacts_dir)
        if oracle.semantic_cases(fresh) != oracle.semantic_cases(frozen):
            raise ValueError(f"fresh pinned Go {lane} observations disagree with the frozen capture")
    _run_rust(lane, frozen_path)
    mutation_count = 0
    if args.negative_control or lane in ("version", "swap"):
        controls = _mutations(lane, frozen)
        for mutated, marker in controls:
            _reject_expected_mutation(lane, mutated, marker)
        mutation_count = len(controls)
    print(f"PASS frozen Go {lane} oracle: {spec['count']} observations; Rust tests={spec['positive_tests']}; mutation_controls={mutation_count}")
    return 0
