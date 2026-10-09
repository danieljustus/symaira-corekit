#!/usr/bin/env python3
"""Run actual Rust update gates against reviewed native Go recordings, without Go."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile

from bounded_oracle_process import run_checked
from frozen_update_anchors import (
    ANCHORS,
    CAPTURE_SOURCE_COMMIT,
    UPDATE_MODULE_COMPATIBILITY_RECEIPT_SHA256,
)
from static_update_oracle import canonical_json, native_goos_arch
from update_fixture_transport import tls_fixture

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "testdata/rust-port/fixtures/update/native-v1"
MODULE_INPUT_PATHS = frozenset(("repository/go.mod", "repository/go.sum"))
COUNTS = {"request": 13, "cache": 7, "persistence": 7, "cosign": 13, "apply": 17, "cancellation": 16}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _module_compatibility_inputs():
    """Return the one reviewed full-byte pair for historical module inputs."""
    path = ROOT / "docs/rust-port/evidence/update-module-compat-v1.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("frozen-update module compatibility receipt is missing or unsafe")
    raw = path.read_bytes()
    if digest(raw) != UPDATE_MODULE_COMPATIBILITY_RECEIPT_SHA256:
        raise ValueError("frozen-update module compatibility receipt bytes differ")
    try:
        receipt = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("frozen-update module compatibility receipt is invalid JSON") from error
    if (
        not isinstance(receipt, dict)
        or type(receipt.get("schema_version")) is not int
        or receipt["schema_version"] != 1
        or receipt.get("profile") != "frozen-update-go-modules-v1"
        or receipt.get("historical_oracle_source_commit") != CAPTURE_SOURCE_COMMIT
        or not isinstance(receipt.get("candidate_capture_revision"), str)
        or re.fullmatch(r"[0-9a-f]{40}", receipt["candidate_capture_revision"]) is None
    ):
        raise ValueError("frozen-update module compatibility receipt identity differs")

    def module_pair(field):
        value = receipt.get(field)
        if not isinstance(value, dict) or set(value) != MODULE_INPUT_PATHS:
            raise ValueError("frozen-update module compatibility pair has an unexpected scope")
        if any(not isinstance(item, str) or re.fullmatch(r"[0-9a-f]{64}", item) is None for item in value.values()):
            raise ValueError("frozen-update module compatibility pair has an invalid digest")
        return value

    historical = module_pair("historical_module_inputs")
    approved = module_pair("approved_module_inputs")
    if historical == approved:
        raise ValueError("frozen-update module compatibility profile is not a module update")
    capture = receipt.get("capture")
    if (
        not isinstance(capture, dict)
        or capture.get("target") != "darwin-arm64"
        or capture.get("go_version") != "go1.26.6"
        or capture.get("capture_mode") != "native-go-update-original-v1"
        or capture.get("external_module_source_paths") != []
    ):
        raise ValueError("frozen-update compatibility capture provenance differs")
    lanes = capture.get("lanes")
    if not isinstance(lanes, list) or len(lanes) != len(COUNTS):
        raise ValueError("frozen-update compatibility capture lane inventory differs")
    by_lane = {row.get("lane"): row for row in lanes if isinstance(row, dict)}
    if set(by_lane) != set(COUNTS) or len(by_lane) != len(lanes):
        raise ValueError("frozen-update compatibility capture lane inventory differs")
    for lane, count in COUNTS.items():
        row = by_lane[lane]
        if (
            row.get("case_count") != count
            or row.get("observations_equal") is not True
            or row.get("stdout_bytes_equal") is not True
            or row.get("external_module_source_paths") != []
            or type(row.get("stderr_bytes_equal")) is not bool
            or type(row.get("source_file_count")) is not int
            or row["source_file_count"] < 100
            or row.get("historical_capture_sha256") != ANCHORS["darwin-arm64"][lane]
        ):
            raise ValueError(f"frozen-update compatibility evidence is incomplete for {lane}")
        for field in (
            "candidate_capture_sha256", "candidate_stdout_sha256", "candidate_stderr_sha256",
            "historical_stdout_sha256", "historical_stderr_sha256", "case_inventory_sha256",
            "source_inventory_sha256",
        ):
            if not isinstance(row.get(field), str) or re.fullmatch(r"[0-9a-f]{64}", row[field]) is None:
                raise ValueError(f"frozen-update compatibility evidence has invalid {lane}/{field}")
        if row["candidate_stdout_sha256"] != row["historical_stdout_sha256"]:
            raise ValueError(f"frozen-update compatibility stdout differs for {lane}")
    return historical, approved


def rust_snapshot():
    paths = set(path for path in (ROOT / "rust").rglob("*") if path.is_file())
    paths.update(ROOT / name for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "Makefile"))
    paths.update(path for path in (ROOT / ".cargo").rglob("*") if path.is_file())
    paths.add(ROOT / "docs/rust-port/evidence/update-module-compat-v1.json")
    paths.update(Path(__file__).with_name(name) for name in (
        "frozen_update_replay.py", "frozen_update_anchors.py", "update_fixture_transport.py",
        "update-owned-verifier.rs", "bounded_oracle_process.py"))
    records = []
    for path in sorted(paths):
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("Rust replay input escapes the candidate checkout")
        records.append({"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path.read_bytes())})
    return records


def read_capture(lane, alternate=None):
    target = "-".join(native_goos_arch())
    expected = ANCHORS.get(target, {}).get(lane)
    if not expected:
        raise ValueError(f"missing reviewed native {target}/{lane} anchor")
    path = FIXTURES / target / f"{lane}.json" if alternate is None else alternate
    if path.is_symlink() or not path.is_file():
        raise ValueError("native update capture must be a regular file")
    raw = path.read_bytes()
    if digest(raw) != expected:
        raise ValueError("native update capture differs from fixed reviewed bytes")
    payload = json.loads(raw)
    record = payload["capture"]
    if record["source_commit"] != CAPTURE_SOURCE_COMMIT or record["working_tree_clean"] is not True or record["dirty_paths"]:
        raise ValueError("native update source identity is not the reviewed clean capture")
    if record["schema_version"] != 1 or record["lane"] != lane or record["capture_mode"] != "native-go-update-original-v1":
        raise ValueError("native update producer identity differs")
    go = record["go"]
    if (go["goos"], go["goarch"]) != native_goos_arch() or go["goversion"] != "go1.26.6" or go["version"] != f"go version go1.26.6 {go['goos']}/{go['goarch']}":
        raise ValueError("native update compiler platform differs")
    if record["raw"]["exit_code"] != 0:
        raise ValueError("original native Go execution failed")
    for stream in ("stdout", "stderr"):
        original = FIXTURES / target / f"{lane}.{stream}"
        if original.is_symlink() or not original.is_file() or digest(original.read_bytes()) != record["raw"][stream + "_sha256"]:
            raise ValueError("original native Go raw stream changed")
    seen = set()
    module_records = {}
    files = record["source_files"] + [record["producer"]]
    for item in files:
        name = item["path"]
        parts = PurePosixPath(name).parts
        if name in seen or not parts or parts[0] not in {"repository", "modules", "toolchain", "generated"} or ".." in parts or "\\" in name or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("invalid native source inventory")
        seen.add(name)
        if parts[0] == "modules":
            raise ValueError("native update closure contains external Go module inputs")
        if parts[0] == "repository":
            source = ROOT.joinpath(*parts[1:])
            if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(ROOT):
                raise ValueError(f"native update repository input changed: {name}")
            if name in MODULE_INPUT_PATHS:
                module_records[name] = item["sha256"]
            elif digest(source.read_bytes()) != item["sha256"]:
                raise ValueError(f"native update repository input changed: {name}")
    if len(seen) < 100 or record["producer"]["path"] != "repository/scripts/rust-port/native_update_capture.py":
        raise ValueError("incomplete native source inventory")
    if set(module_records) != MODULE_INPUT_PATHS:
        raise ValueError("native update historical module input pair is incomplete")
    historical_modules, approved_modules = _module_compatibility_inputs()
    if module_records != historical_modules:
        raise ValueError("native update historical module input pair differs")
    current_modules = {}
    for name in MODULE_INPUT_PATHS:
        source = ROOT.joinpath(*PurePosixPath(name).parts[1:])
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(ROOT):
            raise ValueError(f"native update Go module input is missing or unsafe: {name}")
        current_modules[name] = digest(source.read_bytes())
    if current_modules != approved_modules:
        raise ValueError("current Go module files differ from the approved frozen-update compatibility pair")

    observations = payload["observations"]
    cases = observations if isinstance(observations, list) else observations["cases"]
    ids = [case["input"]["id"] if lane == "apply" else case["id"] for case in cases]
    if len(cases) != COUNTS[lane] or len(set(ids)) != COUNTS[lane] or record["case_count"] != COUNTS[lane] or record["case_ids"] != ids or record["case_fingerprints_sha256"] != [digest(canonical_json(case)) for case in cases]:
        raise ValueError("native update original case inventory differs")
    return raw, observations


def cargo(arguments, env, artifacts, minimum, *, negative_marker=None):
    result = run_checked(["cargo", "test", "--offline", "--locked", "-p", "symaira-core-update", *arguments], cwd=ROOT, env=env, timeout=180, artifact_dir=artifacts, merge_stderr=True)
    output = result.stdout.decode("utf-8", errors="replace")
    if negative_marker:
        if result.returncode == 0 or negative_marker not in output or "test result: FAILED." not in output or "panicked at" not in output:
            raise ValueError(f"mutation was not rejected at {negative_marker}:\n{output[-4096:]}")
        return
    results = re.findall(r"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored;", output)
    if result.returncode or not results or sum(int(row[0]) for row in results) < minimum or any(int(row[1]) for row in results):
        raise ValueError(f"actual nonzero Rust update gate failed:\n{output[-4096:]}")
    if "--exact" in arguments and results != [("1", "0", "0")]:
        raise ValueError("named opt-in Rust gate did not execute exactly once")


def plain_file(directory, lane, observations):
    path = directory / f"{lane}.json"
    path.write_text(json.dumps(observations), encoding="utf-8")
    return path


def replay_lane(lane, observations, directory, env, artifacts):
    fixture = plain_file(directory, lane, observations)
    if lane == "request":
        env["UPDATE_REQUEST_FIXTURE"] = str(fixture)
        with ExitStack() as stack:
            for mode in ("tls", "tls12", "tls13"):
                connection = stack.enter_context(tls_fixture(mode, directory))
                env[f"UPDATE_REQUEST_{mode.upper()}_URL"] = connection["url"]
                if mode != "tls":
                    env[f"UPDATE_REQUEST_{mode.upper()}_CERT"] = connection["cert"]
            cargo(["--lib", "request::tests::tls_protocol_minimum_rejects_1_2", "--", "--ignored", "--exact"], env, artifacts, 1)
            command = ["--test", "request"]
            cargo(command, env, artifacts, 2)
            mutated = copy.deepcopy(observations)
            headers = next(row for row in mutated["cases"] if row["id"] == "request")["headers"]
            headers["User-Agent"] += "-mutated"
            fixture.write_text(json.dumps(mutated), encoding="utf-8")
            cargo(command, env, artifacts, 0, negative_marker=headers["User-Agent"])
    elif lane == "cache":
        # The Rust cache test embeds the unchanged original cache fixture.
        original = json.loads((ROOT / "testdata/rust-port/fixtures/update/cache.json").read_text(encoding="utf-8"))
        if observations != original:
            raise ValueError("native cache recording differs from the Rust embedded original")
        cargo(["--test", "cache"], env, artifacts, 1)
    elif lane == "persistence":
        env["COREKIT_UPDATE_CACHE_LIVE"] = str(fixture)
        command = ["--test", "cache_persistence"]
        cargo(command, env, artifacts, 1)
        mutated = copy.deepcopy(observations)
        if not mutated["cases"][0]["cache_bytes"]:
            raise ValueError("persistence fixture has no bytes for semantic mutation")
        mutated["cases"][0]["cache_bytes"] += " mutated"
        fixture.write_text(json.dumps(mutated), encoding="utf-8")
        cargo(command, env, artifacts, 0, negative_marker="timestamp-normalized cache bytes")
    elif lane == "cosign":
        env["COSIGN_CONTRACT_FIXTURE"] = str(fixture)
        command = ["--test", "cosign_contract"]
        cargo(command, env, artifacts, 1)
        with tls_fixture("tls13", directory) as connection:
            env.update(UPDATE_REQUEST_TLS13_URL=connection["url"], UPDATE_REQUEST_TLS13_CERT=connection["cert"])
            cargo(["--lib", "cosign::network_tests::cosign_artifact_fetch_replays_go_observations", "--", "--ignored", "--exact"], env, artifacts, 1)
        mutated = copy.deepcopy(observations)
        mutated["cases"][0]["result"]["body"] += "-mutated"
        fixture.write_text(json.dumps(mutated), encoding="utf-8")
        cargo(command, env, artifacts, 0, negative_marker="case fetch-signature")
    elif lane == "apply":
        env["UPDATE_APPLY_FIXTURE"] = str(fixture)
        for name in ("apply", "applier"):
            cargo(["--test", name], env, artifacts, 1)
        for case_id, field, changed, marker in (
            ("install", "target_content", "mutated fixture", "install observation"),
            ("blocked-parent", "stage_during_download", True, "blocked-parent observation"),
            ("nested-install", "files", [{"path": "wrong-nested/mytool", "content": "new"}], "nested-install observation"),
            ("zip-extract-blocked", "target_content", "wrong ZIP installation", "zip-extract-blocked observation"),
            ("checksums-shaped-asset", "error_code", "wrong asset acceptance", "checksums-shaped-asset observation"),
            ("malformed-checksums", "stage_during_download", True, "malformed-checksums observation"),
        ):
            mutated = copy.deepcopy(observations)
            row = next(row for row in mutated["cases"] if row["input"]["id"] == case_id)
            if field == "files":
                row["observation"]["files"][0]["path"] = changed[0]["path"]
            else:
                row["observation"][field] = changed
            fixture.write_text(json.dumps(mutated), encoding="utf-8")
            cargo(["--test", "apply"], env, artifacts, 0, negative_marker=marker)
            if case_id == "install":
                cargo(["--test", "applier"], env, artifacts, 0, negative_marker="install target content")
    elif lane == "cancellation":
        env["UPDATE_CANCELLATION_FIXTURE"] = str(fixture)
        command = ["--test", "cancellation"]
        cargo(command, env, artifacts, 2)
        mutated = copy.deepcopy(observations)
        mutated[0]["cancelled"] = not mutated[0]["cancelled"]
        fixture.write_text(json.dumps(mutated), encoding="utf-8")
        cargo(command, env, artifacts, 0, negative_marker="pre-cancellation Go observation mismatch")
        fixture.write_text(json.dumps(observations), encoding="utf-8")
        helper = directory / "helper"
        helper.mkdir(mode=0o700)
        executable = helper / ("cosign.exe" if os.name == "nt" else "cosign")
        run_checked(["rustc", "--edition=2021", str(ROOT / "scripts/rust-port/update-owned-verifier.rs"), "-o", str(executable)], cwd=ROOT, env=env, timeout=60, artifact_dir=artifacts, check=True)
        env.update(PATH=str(helper) + os.pathsep + env["PATH"], UPDATE_CANCEL_VERIFIER_READY=str(directory / "verifier-ready"))
        cargo([*command, "cancellable_verifier_reaps_native_owned_process_tree", "--", "--ignored", "--exact", "--nocapture"], env, artifacts, 1)
        with tls_fixture("cancellation", directory) as connection:
            env.update(UPDATE_CANCELLATION_URL=connection["url"], UPDATE_CANCELLATION_CERT=connection["cert"])
            public = [*command, "public_cancellation_replays_go", "--", "--ignored", "--exact", "--nocapture"]
            cargo(public, env, artifacts, 1)
            fixture.write_text(json.dumps(mutated), encoding="utf-8")
            cargo(public, env, artifacts, 0, negative_marker="public cancellation observation mismatch")


def legacy_entry(lane, args):
    """Keep historical CLI flags while requiring opt-in for live Go execution."""
    if os.environ.get("GO_ORACLE") == "1":
        return False
    if getattr(args, "write", False):
        raise ValueError("live Go regeneration requires explicit GO_ORACLE=1")
    arguments = ["--lane", lane]
    if any(argument == "--fixture" or argument.startswith("--fixture=") for argument in sys.argv[1:]):
        arguments += ["--fixture", str(args.fixture)]
    main(arguments)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", choices=tuple(COUNTS), required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "target/frozen-update")
    args = parser.parse_args(argv)
    raw, observations = read_capture(args.lane, args.fixture)
    if args.verify_only:
        print(f"PASS fixed original native {args.lane} capture")
        return
    args.output.mkdir(parents=True, exist_ok=True)
    snapshot = rust_snapshot()
    with tempfile.TemporaryDirectory(prefix=f"rust-update-{args.lane}-") as name:
        # Windows' default temp parent may use a DOS short name. Export the
        # same canonical root that the loopback readiness guard verifies.
        directory = Path(name).resolve(strict=True)
        env = dict(os.environ, CARGO_NET_OFFLINE="true", CARGO_TARGET_DIR=str(ROOT / "target"), TMPDIR=str(directory), TMP=str(directory), TEMP=str(directory))
        for variable, suffix in (("HOME", "home"), ("USERPROFILE", "home"), ("APPDATA", "config"), ("LOCALAPPDATA", "data"), ("XDG_CACHE_HOME", "cache"), ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_STATE_HOME", "state")):
            path = directory / suffix
            path.mkdir(mode=0o700, exist_ok=True)
            env[variable] = str(path)
        # Resolve toolchain homes before isolating HOME, without launching Go.
        for variable, suffix in (("CARGO_HOME", ".cargo"), ("RUSTUP_HOME", ".rustup")):
            env[variable] = os.environ.get(variable, str(Path.home() / suffix))
        metadata = run_checked(["cargo", "metadata", "--offline", "--locked", "--no-deps", "--format-version", "1"], cwd=ROOT, env=env, timeout=30, artifact_dir=args.output, check=True)
        metadata = json.loads(metadata.stdout)
        package = next(package for package in metadata["packages"] if package["name"] == "symaira-core-update")
        if Path(package["manifest_path"]).resolve() != ROOT / "rust/symaira-core-update/Cargo.toml" or Path(metadata["workspace_root"]).resolve() != ROOT or Path(metadata["target_directory"]).resolve() != ROOT / "target":
            raise ValueError("Cargo selected another candidate or target directory")
        previous_umask = os.umask(0o022) if os.name == "posix" else None
        try:
            replay_lane(args.lane, observations, directory, env, args.output)
        finally:
            if previous_umask is not None:
                os.umask(previous_umask)
    if read_capture(args.lane, args.fixture)[0] != raw:
        raise ValueError("native update recording changed during replay")
    if rust_snapshot() != snapshot:
        raise ValueError("Rust source inputs changed during native execution")
    report = {"status": "PASS", "target": "-".join(native_goos_arch()), "lane": args.lane, "case_count": COUNTS[args.lane], "fixture_sha256": digest(raw), "actual_rust_executed": True, "rust_input_sha256": digest(canonical_json(snapshot)), "rust_inputs": snapshot}
    (args.output / f"{args.lane}-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "rust_inputs"}, sort_keys=True))


if __name__ == "__main__":
    main()
