#!/usr/bin/env python3
"""Capture/replay the native FS/SEC Go oracle as an independently anchored v1.

Capture is additive and opt-in. Replay is the default, accepts only bytes whose
SHA-256 is present in ``fs_secret_anchors.py``, builds the assigned Rust source
with Cargo offline, and never invokes Go or Git. Native observations are not
accepted until a parent reviews the fresh capture and adds its digest to the
separate anchor map.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, Mapping
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = ROOT / "testdata/rust-port/fixtures/fs-secret/frozen-v1"
ORACLE = "f3d3eb79b9b1f31b4f973d2ed518a8292cedf588"
GO_VERSION = "go1.26.6"
CASE_IDS = tuple([*(f"FS-{n:03}" for n in range(1, 8)), *(f"SEC-{n:03}" for n in range(1, 7))])
PATH_CONTROL_IDS = ("0000", "001f", "0020", "007e", "007f", "0080", "0085", "009f", "00a0")
STRICT_V1_GO_ACCEPTED = frozenset(("007f", "0080", "0085", "009f"))
ORACLE_SOURCE_FILES = (
    "fsutil/pathutil.go",
    "fsutil/atomicwrite.go",
    "fsutil/safewrite.go",
    "secretref/secretref.go",
    "secretref/symvault.go",
)
GO_LIST_FIELDS = (
    "Dir,GoFiles,CompiledGoFiles,CgoFiles,CFiles,CXXFiles,MFiles,FFiles,SFiles,HFiles,"
    "SysoFiles,EmbedFiles,TestGoFiles,XTestGoFiles,TestEmbedFiles,XTestEmbedFiles,Module"
)
REQUIRED_COMMANDS = frozenset((
    "git-head-before", "git-status-before", "git-verify-oracle", "git-archive",
    "go-list-before", "go-build", "go-cases", "go-path-controls",
    "go-list-after", "git-status-after", "git-head-after",
))
GROUP_NAMES = ("candidate", "oracle", "modules", "sdk")
# The independently reviewed anchor is deliberately excluded: review may add
# its digest after a clean native capture without rewriting captured inputs.
CANDIDATE_SCRIPT_FILES = (
    "scripts/rust-port/generate_fs_secret.py",
    "scripts/rust-port/validate_fs_secret.py",
    "scripts/rust-port/diff_fs_secret.py",
    "scripts/rust-port/fs-path-control-differential.py",
    "scripts/rust-port/bounded_oracle_process.py",
    "scripts/rust-port/static_update_oracle.py",
    "scripts/rust-port/static_update_anchors.py",
    "scripts/rust-port/fs_secret_oracle.py",
    "scripts/rust-port/test_fs_secret_oracle.py",
    "scripts/rust-port/go-oracle/go.mod",
    "scripts/rust-port/go-oracle/go.sum",
    "scripts/rust-port/go-oracle/cmd/fssecret/main.go",
)
RUST_INPUT_DIRS = (
    "rust/symaira-core-fs",
    "rust/symaira-core-secretref",
    "rust/symaira-core-config",
    "rust/symaira-core-env",
    "rust/symaira-core-exit",
    "rust/symaira-core-log",
    "rust/symaira-core-version",
    "rust/test-support/symaira-contract-fixtures",
    "rust/test-support/symaira-core-foundation",
)

# Import the shared bounded runner and only the applicable Go environment/native
# identity helpers. static_update_oracle._source_inventory is lane-specific and
# intentionally is not used for this capture.
sys.path.insert(0, str(SCRIPT_DIR))
import static_update_oracle as _static_oracle  # noqa: E402
from bounded_oracle_process import run_checked  # noqa: E402
from fs_secret_anchors import TRUSTED_CAPTURE_SHA256  # noqa: E402


class OracleError(RuntimeError):
    """A fail-closed capture/replay validation error."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _decode_json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except UnicodeDecodeError as error:
        raise OracleError(f"{label} is not strict UTF-8 JSON") from error
    except ValueError as error:
        if str(error) == "duplicate JSON object key":
            raise OracleError(str(error)) from error
        raise OracleError(f"{label} is not strict UTF-8 JSON") from error


def _native_goos_arch() -> tuple[str, str]:
    target = _static_oracle.native_goos_arch()
    if target[0] not in ("darwin", "linux", "windows") or target[1] not in ("amd64", "arm64"):
        raise OracleError("FS/SEC frozen-v1 supports native darwin/linux/windows amd64/arm64 only")
    return target


def _target_key(goos: str, goarch: str) -> str:
    return f"{goos}-{goarch}"


def fixture_path(goos: str, goarch: str) -> Path:
    if goos not in ("darwin", "linux", "windows") or goarch not in ("amd64", "arm64"):
        raise OracleError("invalid native fixture target")
    return FIXTURE_DIR / f"{_target_key(goos, goarch)}.json"


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _is_commit(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def _safe_label(value: Any) -> bool:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value or ":" in value:
        return False
    return all(part not in ("", ".", "..") for part in value.split("/"))


def _validate_file_records(value: Any, label: str, *, required: bool = True) -> list[dict[str, str]]:
    if not isinstance(value, list) or (required and not value):
        raise OracleError(f"{label} input inventory missing or malformed")
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise OracleError(f"{label} input record schema mismatch")
        path, digest = item["path"], item["sha256"]
        if not _safe_label(path) or path in seen or not _is_digest(digest):
            raise OracleError(f"{label} input record identity invalid")
        seen.add(path)
        result.append({"path": path, "sha256": digest})
    if result != sorted(result, key=lambda item: item["path"]):
        raise OracleError(f"{label} input records are not deterministically ordered")
    return result


def _inventory_digest(files: list[dict[str, str]]) -> str:
    return sha256(_canonical_json(files))


def _group_digests(files: list[dict[str, str]]) -> dict[str, str]:
    groups = {}
    for group in GROUP_NAMES:
        selected = [item for item in files if item["path"].startswith(group + "/")]
        if not selected:
            raise OracleError(f"required {group} input inventory is empty")
        groups[group] = _inventory_digest(selected)
    return groups


def _validate_command_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise OracleError("capture command inventory missing")
    seen = set()
    required_seen = set()
    for item in value:
        required = {
            "id", "exit_code", "timed_out", "output_exceeded", "cleanup_verified",
            "stdout_bytes", "stderr_bytes", "stdout_sha256", "stderr_sha256",
        }
        if not isinstance(item, dict) or set(item) != required:
            raise OracleError("capture command record schema mismatch")
        name = item["id"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9-]+", name) or name in seen:
            raise OracleError("capture command identity invalid or duplicated")
        seen.add(name)
        if type(item["exit_code"]) is not int or item["exit_code"] != 0:
            raise OracleError(f"capture command {name} did not exit successfully")
        for field in ("timed_out", "output_exceeded", "cleanup_verified"):
            if type(item[field]) is not bool:
                raise OracleError(f"capture command {name} has malformed {field}")
        if item["timed_out"] or item["output_exceeded"] or not item["cleanup_verified"]:
            raise OracleError(f"capture command {name} exceeded a process guard")
        for field in ("stdout_bytes", "stderr_bytes"):
            if type(item[field]) is not int or item[field] < 0:
                raise OracleError(f"capture command {name} has malformed byte count")
        for field in ("stdout_sha256", "stderr_sha256"):
            if not _is_digest(item[field]):
                raise OracleError(f"capture command {name} has malformed raw digest")
        if name in REQUIRED_COMMANDS:
            required_seen.add(name)
        elif not name.startswith("go-env-"):
            raise OracleError(f"unexpected capture command {name}")
    if required_seen != REQUIRED_COMMANDS:
        raise OracleError("capture command inventory is incomplete")
    return value


def validate_capture_payload(payload: Any, native: tuple[str, str]) -> dict[str, Any]:
    """Strict v1 structural/provenance validator; anchors are checked separately."""
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "capture", "observations"}:
        raise OracleError("frozen-v1 top-level schema mismatch")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise OracleError("unsupported frozen-v1 schema_version")
    capture = payload["capture"]
    required_capture = {"oracle", "candidate", "native", "go", "inputs", "commands", "raw", "case_inventory"}
    if not isinstance(capture, dict) or set(capture) != required_capture:
        raise OracleError("frozen-v1 capture schema mismatch")

    oracle = capture["oracle"]
    if not isinstance(oracle, dict) or set(oracle) != {"commit", "source_sha256", "source_files"}:
        raise OracleError("frozen oracle identity schema mismatch")
    if oracle["commit"] != ORACLE or not _is_digest(oracle["source_sha256"]):
        raise OracleError("frozen production-oracle identity mismatch")
    oracle_files = _validate_file_records(oracle["source_files"], "historical Go source")
    if [item["path"] for item in oracle_files] != sorted(ORACLE_SOURCE_FILES):
        raise OracleError("pinned historical Go source inventory mismatch")

    candidate = capture["candidate"]
    candidate_fields = {"head_before", "head_after", "clean_before", "clean_after", "go_helper_sha256", "files"}
    if not isinstance(candidate, dict) or set(candidate) != candidate_fields:
        raise OracleError("candidate source identity schema mismatch")
    for field in ("head_before", "head_after"):
        if not _is_commit(candidate[field]):
            raise OracleError(f"candidate {field} is not a full commit")
    if candidate["head_before"] != candidate["head_after"]:
        raise OracleError("candidate HEAD changed during Go capture")
    for field in ("clean_before", "clean_after"):
        if type(candidate[field]) is not bool or candidate[field] is not True:
            raise OracleError("Go capture requires a clean candidate before and after execution")
    if not _is_digest(candidate["go_helper_sha256"]):
        raise OracleError("current candidate Go helper digest invalid")
    candidate_files = _validate_file_records(candidate["files"], "candidate")
    helper_path = "candidate/scripts/rust-port/go-oracle/cmd/fssecret/main.go"
    helper_record = next((item for item in candidate_files if item["path"] == helper_path), None)
    if helper_record is None or helper_record["sha256"] != candidate["go_helper_sha256"]:
        raise OracleError("current helper identity is not independently inventoried")

    recorded_native = capture["native"]
    if not isinstance(recorded_native, dict) or set(recorded_native) != {"goos", "goarch"}:
        raise OracleError("native target schema mismatch")
    goos, goarch = recorded_native["goos"], recorded_native["goarch"]
    if goos not in ("darwin", "linux", "windows") or goarch not in ("amd64", "arm64"):
        raise OracleError("unsupported recorded native target")
    if (goos, goarch) != native:
        raise OracleError("capture native OS/architecture does not match this replay host")

    go = capture["go"]
    go_fields = {"version", "goversion", "goos", "goarch", "binary_sha256", "probe_binary_sha256", "goroot_label", "gomodcache_policy", "sdk_sha256", "modules_sha256"}
    if not isinstance(go, dict) or set(go) != go_fields:
        raise OracleError("Go toolchain identity schema mismatch")
    if go["goversion"] != GO_VERSION or go["version"] != f"go version {GO_VERSION} {goos}/{goarch}":
        raise OracleError("capture does not record executed native Go 1.26.6")
    if (go["goos"], go["goarch"]) != (goos, goarch):
        raise OracleError("executed Go environment disagrees with capture target")
    if (not _is_digest(go["binary_sha256"]) or not _is_digest(go["probe_binary_sha256"])
            or go["goroot_label"] != "installed-go-sdk"):
        raise OracleError("Go compiler identity is incomplete")
    if go["gomodcache_policy"] != "existing-cache-offline-read-only":
        raise OracleError("Go module cache was not restricted to existing offline inputs")
    if not _is_digest(go["sdk_sha256"]) or not _is_digest(go["modules_sha256"]):
        raise OracleError("Go SDK/module inventory digest missing")

    inputs = capture["inputs"]
    if not isinstance(inputs, dict) or set(inputs) != {"before_sha256", "after_sha256", "files", "groups"}:
        raise OracleError("Go build-input inventory schema mismatch")
    input_files = _validate_file_records(inputs["files"], "transitive Go build")
    before_digest, after_digest = inputs["before_sha256"], inputs["after_sha256"]
    actual_inventory_digest = _inventory_digest(input_files)
    if not _is_digest(before_digest) or not _is_digest(after_digest) or before_digest != after_digest or before_digest != actual_inventory_digest:
        raise OracleError("Go build inputs changed between pre-build and post-execution inventories")
    groups = inputs["groups"]
    if not isinstance(groups, dict) or set(groups) != set(GROUP_NAMES):
        raise OracleError("Go source/module/SDK input group inventory mismatch")
    computed_groups = _group_digests(input_files)
    if groups != computed_groups:
        raise OracleError("Go source/module/SDK group digest mismatch")
    if go["sdk_sha256"] != groups["sdk"] or go["modules_sha256"] != groups["modules"]:
        raise OracleError("recorded SDK/module digest disagrees with transitive inventory")
    inventory_candidate = [item for item in input_files if item["path"].startswith("candidate/")]
    if candidate_files != inventory_candidate:
        raise OracleError("candidate inventory differs from the pre/post Go build inventory")
    inventory_oracle = [item for item in input_files if item["path"].startswith("oracle/")]
    compiler_path = "sdk/bin/" + ("go.exe" if goos == "windows" else "go")
    if {"path": compiler_path, "sha256": go["binary_sha256"]} not in input_files:
        raise OracleError("executed Go compiler differs from the frozen SDK inventory")
    for item in oracle_files:
        if {"path": "oracle/" + item["path"], "sha256": item["sha256"]} not in inventory_oracle:
            raise OracleError("pinned production source is absent from the transitive Go inventory")

    commands = _validate_command_records(capture["commands"])
    command_by_id = {item["id"]: item for item in commands}
    raw = capture["raw"]
    if not isinstance(raw, dict) or set(raw) != {"artifact_id", "observations"}:
        raise OracleError("private raw capture metadata schema mismatch")
    if raw["artifact_id"] != "private-run":
        raise OracleError("raw capture reference must use a non-personal identifier")
    raw_observations = raw["observations"]
    if not isinstance(raw_observations, dict) or set(raw_observations) != {"cases", "path_controls"}:
        raise OracleError("raw Go observation metadata missing")
    for name in ("cases", "path_controls"):
        record = raw_observations[name]
        fields = {"exit_code", "stdout_bytes", "stderr_bytes", "stdout_sha256", "stderr_sha256"}
        if not isinstance(record, dict) or set(record) != fields:
            raise OracleError(f"raw {name} output metadata schema mismatch")
        if type(record["exit_code"]) is not int or record["exit_code"] != 0:
            raise OracleError(f"raw {name} Go execution did not succeed")
        for field in ("stdout_bytes", "stderr_bytes"):
            if type(record[field]) is not int or record[field] < 0:
                raise OracleError(f"raw {name} output byte count invalid")
        for field in ("stdout_sha256", "stderr_sha256"):
            if not _is_digest(record[field]):
                raise OracleError(f"raw {name} output digest invalid")
        command_id = "go-cases" if name == "cases" else "go-path-controls"
        linked = command_by_id[command_id]
        linked_fields = ("exit_code", "stdout_bytes", "stderr_bytes", "stdout_sha256", "stderr_sha256")
        if any(record[field] != linked[field] for field in linked_fields):
            raise OracleError(f"raw {name} metadata does not match its retained subprocess record")

    inventory = capture["case_inventory"]
    if not isinstance(inventory, dict) or set(inventory) != {"case_ids", "path_control_ids"}:
        raise OracleError("FS/SEC case inventory schema mismatch")
    if inventory["case_ids"] != list(CASE_IDS) or inventory["path_control_ids"] != list(PATH_CONTROL_IDS):
        raise OracleError("FS/SEC capture does not declare all required case IDs")

    observations = payload["observations"]
    if not isinstance(observations, dict) or set(observations) != {"oracle_commit", "native_target", "cases", "path_controls"}:
        raise OracleError("Go observation schema mismatch")
    if observations["oracle_commit"] != ORACLE or observations["native_target"] != _target_key(goos, goarch):
        raise OracleError("Go observation oracle/native identity mismatch")
    cases = observations["cases"]
    if not isinstance(cases, dict) or set(cases) != set(CASE_IDS) or len(cases) != 13:
        raise OracleError("Go observation must contain all 13 FS/SEC cases")
    if any(not isinstance(cases[case_id], dict) for case_id in CASE_IDS):
        raise OracleError("Go FS/SEC case observations must be objects")
    controls = observations["path_controls"]
    if not isinstance(controls, dict) or set(controls) != set(PATH_CONTROL_IDS) or len(controls) != 9:
        raise OracleError("Go observation must contain all nine ASCII path-control keys")
    if any(type(controls[key]) is not bool for key in PATH_CONTROL_IDS):
        raise OracleError("Go path-control observations must be JSON booleans")
    if any(controls[key] is not True for key in STRICT_V1_GO_ACCEPTED):
        raise OracleError("versioned FS-001 strict-v1 controls require Go DEL/C1 acceptance")
    return payload


def _anchor_for(native: tuple[str, str], anchors: Mapping[str, str] | None = None) -> str:
    trusted = TRUSTED_CAPTURE_SHA256 if anchors is None else anchors
    key = _target_key(*native)
    if key not in trusted:
        raise OracleError(f"no independently reviewed FS/SEC frozen-v1 anchor for {key}")
    anchor = trusted[key]
    if not _is_digest(anchor):
        raise OracleError(f"trusted FS/SEC anchor for {key} is not lowercase SHA-256")
    return anchor


def validate_capture_bytes(raw: bytes, native: tuple[str, str], *, anchors: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Validate one already-read byte string against an independent fixed anchor."""
    if not isinstance(raw, bytes):
        raise TypeError("capture bytes must be bytes")
    expected = _anchor_for(native, anchors)
    if sha256(raw) != expected:
        raise OracleError("frozen-v1 bytes do not match the independent trusted anchor")
    payload = _decode_json(raw, "frozen-v1 capture")
    return validate_capture_payload(payload, native)


def read_capture_once(path: Path, native: tuple[str, str], *, anchors: Mapping[str, str] | None = None) -> tuple[bytes, dict[str, Any]]:
    """Read raw bytes once, hash and parse the same bytes; reject links/nonfiles."""
    _anchor_for(native, anchors)
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise OracleError("native frozen-v1 fixture is unavailable") from error
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise OracleError("frozen-v1 fixture must be a regular non-symlink file")
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise OracleError("cannot read native frozen-v1 fixture") from error
    return raw, validate_capture_bytes(raw, native, anchors=anchors)


def normalized_probe(value: dict[str, Any]) -> dict[str, Any]:
    """Exact 13-row normalization already used by diff_fs_secret.normalized."""
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


def compare_observations(go_probe: dict[str, Any], rust_probe: dict[str, Any]) -> None:
    goos, goarch = _native_goos_arch()
    rust_os = {"darwin": "macos", "linux": "linux", "windows": "windows"}[goos]
    rust_arch = {"arm64": "aarch64", "amd64": "x86_64"}[goarch]
    if (go_probe.get("native_target") != _target_key(goos, goarch)
            or rust_probe.get("native_target") != f"{rust_os}-{rust_arch}"):
        raise OracleError("executed Rust and recorded Go native identities differ")
    expected_probe = normalized_probe(go_probe)
    actual_probe = normalized_probe(rust_probe)
    expected = {"oracle_commit": expected_probe.get("oracle_commit"), "cases": expected_probe.get("cases")}
    actual = {"oracle_commit": actual_probe.get("oracle_commit"), "cases": actual_probe.get("cases")}
    if _canonical_json(actual) != _canonical_json(expected):
        raise OracleError("actual Rust binary differs from complete normalized Go FS/SEC observations")
    if sorted(actual["cases"]) != list(CASE_IDS):
        raise OracleError("Rust differential did not execute all 13 FS/SEC cases")


def mutate_known_observation(probe: dict[str, Any]) -> dict[str, Any]:
    """Flip one real FS-001 boolean for the executable comparison negative control."""
    mutated = copy.deepcopy(probe)
    try:
        value = mutated["cases"]["FS-001"]["outcomes"]["valid/file"]["ok"]
    except (KeyError, TypeError) as error:
        raise OracleError("Go FS-001 observation lacks the mutation control field") from error
    if type(value) is not bool:
        raise OracleError("FS-001 mutation control must target a boolean observation")
    mutated["cases"]["FS-001"]["outcomes"]["valid/file"]["ok"] = not value
    return mutated


def _assert_named_test_result(result: subprocess.CompletedProcess, *, passed: bool, exact_reason: str | None = None) -> None:
    name = "fs001_strict_v1_replays_go_controls"
    text = (result.stdout + result.stderr).decode("utf-8", "replace")
    if passed:
        if result.returncode != 0 or not re.search(rf"(?m)^test {name} \.\.\. ok$", text):
            raise OracleError("Rust named FS-001 strict-v1 replay did not explicitly pass")
        if "test result: ok. 1 passed; 0 failed; 0 ignored;" not in text:
            raise OracleError("Rust named FS-001 replay did not report exactly one passing test")
        return
    if result.returncode == 0 or not re.search(rf"(?m)^test {name} \.\.\. FAILED$", text):
        raise OracleError("Rust path-control mutation did not fail the named test")
    if "test result: FAILED. 0 passed; 1 failed; 0 ignored;" not in text:
        raise OracleError("Rust path-control mutation was not one executed test failure")
    if exact_reason is None or exact_reason not in text:
        raise OracleError("Rust path-control mutation failed for the wrong reason")
    if "could not compile" in text.lower():
        raise OracleError("Rust mutation control failed during compilation, not at the assertion")


def _candidate_file_paths(root: Path) -> list[Path]:
    paths = {root / "Cargo.toml", root / "Cargo.lock"}
    for name in CANDIDATE_SCRIPT_FILES:
        paths.add(root / name)
    for name in ("rust-toolchain.toml", "rust-toolchain", ".cargo/config.toml"):
        candidate = root / name
        if candidate.is_file():
            paths.add(candidate)
    for relative in RUST_INPUT_DIRS:
        directory = root / relative
        if not directory.is_dir():
            raise OracleError(f"required Rust candidate source directory is absent: {relative}")
        for path in directory.rglob("*"):
            if not path.is_file() or any(part in ("target", ".git", "__pycache__") for part in path.parts):
                continue
            paths.add(path)
    for path in paths:
        if not path.is_file():
            raise OracleError(f"required candidate input is absent: {path.relative_to(root).as_posix()}")
        resolved = path.resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise OracleError("candidate source input escapes the assigned source root")
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def _candidate_file_records(root: Path) -> list[dict[str, str]]:
    records = []
    for path in _candidate_file_paths(root):
        relative = path.relative_to(root).as_posix()
        records.append({"path": "candidate/" + relative, "sha256": sha256(path.read_bytes())})
    return records


def _verify_candidate_files(capture: dict[str, Any], root: Path) -> None:
    recorded = capture["candidate"]["files"]
    current = _candidate_file_records(root)
    if current != recorded:
        raise OracleError("candidate harness/Rust source differs from the captured clean snapshot")


def _validate_cargo_metadata(raw: bytes, root: Path, target_dir: Path) -> None:
    metadata = _decode_json(raw, "Cargo metadata")
    if not isinstance(metadata, dict):
        raise OracleError("Cargo metadata root is not an object")
    try:
        workspace = Path(metadata["workspace_root"]).resolve()
        directory = Path(metadata["target_directory"]).resolve()
        packages = metadata["packages"]
    except (KeyError, TypeError) as error:
        raise OracleError("Cargo metadata is incomplete") from error
    if workspace != root.resolve() or directory != target_dir.resolve() or not isinstance(packages, list):
        raise OracleError("Cargo selected a workspace or target directory outside the candidate")
    manifest = root / "rust/test-support/symaira-core-foundation/Cargo.toml"
    source = root / "rust/test-support/symaira-core-foundation/src/bin/rust_fs_secret.rs"
    matches = [item for item in packages if isinstance(item, dict) and item.get("name") == "symaira-core-foundation"]
    if len(matches) != 1 or Path(matches[0].get("manifest_path", "")).resolve() != manifest.resolve():
        raise OracleError("Cargo metadata did not select the candidate foundation package")
    targets = matches[0].get("targets")
    if not isinstance(targets, list):
        raise OracleError("Cargo foundation target inventory is missing")
    binaries = [item for item in targets if isinstance(item, dict) and item.get("name") == "rust-fs-secret" and "bin" in item.get("kind", [])]
    if len(binaries) != 1 or Path(binaries[0].get("src_path", "")).resolve() != source.resolve():
        raise OracleError("Cargo metadata did not select the actual rust-fs-secret candidate binary")


def _scratch_parent() -> Path:
    preferred = os.environ.get("TMPDIR") or (Path.home() / ".hermes/cache/scratch")
    parent = Path(preferred).expanduser().resolve()
    if parent.is_relative_to(ROOT.resolve()):
        raise OracleError("private scratch must stay outside the source checkout")
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def _isolated_base_env(private: Path, *, include_go: bool = False) -> dict[str, str]:
    names = ("home", "xdg-cache", "xdg-config", "xdg-data", "xdg-state", "tmp", "go-cache")
    for name in names:
        (private / name).mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(private / "home"),
        "USERPROFILE": str(private / "home"),
        "XDG_CACHE_HOME": str(private / "xdg-cache"),
        "XDG_CONFIG_HOME": str(private / "xdg-config"),
        "XDG_DATA_HOME": str(private / "xdg-data"),
        "XDG_STATE_HOME": str(private / "xdg-state"),
        "TMPDIR": str(private / "tmp"),
        "TMP": str(private / "tmp"),
        "TEMP": str(private / "tmp"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_ALLOW_PROTOCOL": "file",
        "GIT_CEILING_DIRECTORIES": str(ROOT.parent.resolve()),
    }
    for name in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE"):
        if name in os.environ:
            env[name] = os.environ[name]
    if include_go and os.environ.get("GO_ORACLE_BIN"):
        env["GO_ORACLE_BIN"] = os.environ["GO_ORACLE_BIN"]
    if include_go:
        env["GO_ORACLE"] = "1"
    return env


class _Recorder:
    """Keep raw subprocess bytes privately before callers decode anything."""

    def __init__(self, artifact_root: Path):
        self.root = artifact_root
        self.raw_dir = self.root / "raw"
        self.raw_dir.mkdir(parents=True, mode=0o700)
        (self.root / "bounded").mkdir(mode=0o700)
        self.commands: list[dict[str, Any]] = []
        self._flush("running")

    def _summary(self, name: str, returncode: int | None, stdout: bytes, stderr: bytes, *, timed_out=False, output_exceeded=False, cleanup_verified=True) -> dict[str, Any]:
        safe_name = re.sub(r"[^a-z0-9-]", "-", name.lower())
        for suffix, data in (("stdout", stdout), ("stderr", stderr)):
            path = self.raw_dir / f"{safe_name}.{suffix}.raw"
            with path.open("xb") as stream:
                stream.write(data)
        record = {
            "id": safe_name,
            "exit_code": returncode,
            "timed_out": bool(timed_out),
            "output_exceeded": bool(output_exceeded),
            "cleanup_verified": bool(cleanup_verified),
            "stdout_bytes": len(stdout),
            "stderr_bytes": len(stderr),
            "stdout_sha256": sha256(stdout),
            "stderr_sha256": sha256(stderr),
        }
        self.commands.append(record)
        self._flush("running")
        return record

    def run(self, name: str, command, *, cwd: Path, env: Mapping[str, str], timeout: float = 180) -> subprocess.CompletedProcess:
        try:
            result = run_checked(
                command, cwd=cwd, env=env, timeout=timeout,
                artifact_dir=self.root / "bounded" / name,
            )
        except BaseException as error:
            result = getattr(error, "result", None)
            if isinstance(result, dict):
                self._summary(name, result.get("returncode"), result.get("stdout", b""), result.get("stderr", b""),
                              timed_out=result.get("timed_out", False), output_exceeded=result.get("output_exceeded", False),
                              cleanup_verified=result.get("cleanup_verified", False))
            else:
                self._summary(name, None, b"", b"", cleanup_verified=False)
            raise
        self._summary(name, result.returncode, result.stdout, result.stderr)
        return result

    def collect_runner_records(self, folder: Path, prefix: str) -> None:
        results = sorted(folder.glob("command-*/result.json")) if folder.exists() else []
        for index, metadata_path in enumerate(results):
            metadata = _decode_json(metadata_path.read_bytes(), "bounded runner metadata")
            record_dir = metadata_path.parent
            stdout = (record_dir / "stdout.raw").read_bytes()
            stderr = (record_dir / "stderr.raw").read_bytes()
            self._summary(
                f"{prefix}-{index:03d}", metadata.get("returncode"), stdout, stderr,
                timed_out=metadata.get("timed_out") is True,
                output_exceeded=metadata.get("output_exceeded") is True,
                cleanup_verified=metadata.get("cleanup_verified") is True,
            )

    def _flush(self, status: str, *, error_type: str | None = None, fixture_sha256: str | None = None) -> None:
        value = {"status": status, "commands": self.commands}
        if error_type:
            value["error_type"] = error_type
        if fixture_sha256:
            value["fixture_sha256"] = fixture_sha256
        (self.root / "run.json").write_bytes(_json_bytes(value))

    def finish(self, status: str, *, error_type: str | None = None, fixture_sha256: str | None = None) -> None:
        self._flush(status, error_type=error_type, fixture_sha256=fixture_sha256)


def _require_zero(result: subprocess.CompletedProcess, stage: str) -> bytes:
    if result.returncode != 0:
        raise OracleError(f"subprocess stage failed: {stage}")
    return result.stdout


def _git_identity(recorder: _Recorder, env: Mapping[str, str], suffix: str) -> tuple[str, bool]:
    head_bytes = _require_zero(recorder.run(f"git-head-{suffix}", ["git", "rev-parse", "HEAD"], cwd=ROOT, env=env, timeout=30), "git rev-parse HEAD")
    status = _require_zero(recorder.run(f"git-status-{suffix}", ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=ROOT, env=env, timeout=30), "git status")
    try:
        head = head_bytes.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise OracleError("Git HEAD is not ASCII") from error
    if not _is_commit(head):
        raise OracleError("Git HEAD is not a full commit")
    return head, not status.strip()


def _hash_source_files(archive_root: Path) -> tuple[str, list[dict[str, str]]]:
    digest = hashlib.sha256()
    records = []
    for name in ORACLE_SOURCE_FILES:
        path = archive_root / name
        if not path.is_file():
            raise OracleError("pinned Go archive omitted required production source")
        data = path.read_bytes()
        digest.update(name.encode("utf-8") + b"\0" + data)
        records.append({"path": name, "sha256": sha256(data)})
    return digest.hexdigest(), sorted(records, key=lambda item: item["path"])


def _add_record(records: dict[str, str], label: str, path: Path, *, root: Path | None = None) -> None:
    resolved = path.resolve()
    if root is not None and not resolved.is_relative_to(root.resolve()):
        raise OracleError("transitive Go input escaped its declared source root")
    if not resolved.is_file():
        raise OracleError("transitive Go build input is not a regular file")
    if not _safe_label(label):
        raise OracleError("transitive Go input produced an unsafe public label")
    value = sha256(resolved.read_bytes())
    prior = records.get(label)
    if prior is not None and prior != value:
        raise OracleError("one logical Go input resolved to inconsistent bytes")
    records[label] = value


def _parse_go_list(raw: bytes) -> list[dict[str, Any]]:
    try:
        text = raw.decode("utf-8")
        decoder = json.JSONDecoder(object_pairs_hook=_reject_duplicate_pairs)
        values = []
        while text.strip():
            text = text.lstrip()
            item, end = decoder.raw_decode(text)
            if not isinstance(item, dict):
                raise ValueError("go list item is not an object")
            values.append(item)
            text = text[end:]
        if not values:
            raise ValueError("go list returned no package records")
        return values
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise OracleError("go list did not return a complete JSON dependency inventory") from error


def _discover_input_inventory(
    recorder: _Recorder,
    go_tool: Path,
    env: Mapping[str, str],
    helper_root: Path,
    modfile: Path,
    archive_root: Path,
    goos: str,
    goarch: str,
    stage: str,
) -> list[dict[str, str]]:
    listing = recorder.run(
        stage,
        [str(go_tool), "list", "-deps", "-json=" + GO_LIST_FIELDS, "-modfile=" + str(modfile), "./cmd/fssecret"],
        cwd=helper_root, env=env, timeout=180,
    )
    raw = _require_zero(listing, stage)
    packages = _parse_go_list(raw)
    records: dict[str, str] = {}
    candidate_records = _candidate_file_records(ROOT)
    candidate_by_relative = {item["path"][len("candidate/"):]: item["sha256"] for item in candidate_records}
    sdk_root = Path(env["GOROOT"]).resolve()
    module_cache = Path(env["GOMODCACHE"]).resolve()
    archive_root = archive_root.resolve()
    helper_root = helper_root.resolve()

    def add_source(path: Path) -> None:
        resolved = path.resolve()
        if resolved.is_relative_to(helper_root):
            relative = (Path("scripts/rust-port/go-oracle") / resolved.relative_to(helper_root)).as_posix()
            label = "candidate/" + relative
            expected = candidate_by_relative.get(relative)
            if expected is None or sha256(resolved.read_bytes()) != expected:
                raise OracleError("copied Go helper differs from current candidate source")
            _add_record(records, label, resolved, root=helper_root)
        elif resolved.is_relative_to(archive_root):
            _add_record(records, "oracle/" + resolved.relative_to(archive_root).as_posix(), resolved, root=archive_root)
        elif resolved.is_relative_to(sdk_root):
            _add_record(records, "sdk/" + resolved.relative_to(sdk_root).as_posix(), resolved, root=sdk_root)
        elif resolved.is_relative_to(module_cache):
            _add_record(records, "modules/cache/" + resolved.relative_to(module_cache).as_posix(), resolved, root=module_cache)
        else:
            raise OracleError("go list source escaped helper, pinned source, SDK and module-cache roots")

    def add_module_file(path: Path) -> None:
        resolved = path.resolve()
        if resolved == modfile.resolve():
            _add_record(records, "modules/current-helper/effective.mod", resolved, root=modfile.parent)
        elif resolved == modfile.with_suffix(".sum").resolve():
            _add_record(records, "modules/current-helper/effective.sum", resolved, root=modfile.parent)
        elif resolved.is_relative_to(helper_root):
            if resolved.name in ("oracle.mod", "oracle.sum"):
                label = "modules/current-helper/effective." + ("mod" if resolved.suffix == ".mod" else "sum")
            else:
                label = "modules/current-helper/" + resolved.name
            _add_record(records, label, resolved, root=helper_root)
        elif resolved.is_relative_to(archive_root):
            _add_record(records, "modules/replacement/" + resolved.relative_to(archive_root).as_posix(), resolved, root=archive_root)
        elif resolved.is_relative_to(module_cache):
            _add_record(records, "modules/cache/" + resolved.relative_to(module_cache).as_posix(), resolved, root=module_cache)
        elif resolved.is_relative_to(sdk_root):
            _add_record(records, "sdk/" + resolved.relative_to(sdk_root).as_posix(), resolved, root=sdk_root)
        else:
            raise OracleError("Go module manifest escaped pinned source and installed caches")

    # Candidate capture harness and Rust inputs are frozen alongside every
    # transitive Go dependency, not inferred from generator membership.
    for item in candidate_records:
        _add_record(records, item["path"], ROOT / item["path"][len("candidate/"):], root=ROOT)
    for name, label in (("go.mod", "modules/current-helper/source-go.mod"), ("go.sum", "modules/current-helper/source-go.sum")):
        _add_record(records, label, helper_root / name, root=helper_root)
    _add_record(records, "modules/current-helper/effective.mod", modfile, root=helper_root.parent)
    effective_sum = modfile.with_suffix(".sum")
    _add_record(records, "modules/current-helper/effective.sum", effective_sum, root=helper_root.parent)
    for name in ("go.mod", "go.sum"):
        path = archive_root / name
        if path.is_file():
            _add_record(records, "modules/replacement/" + name, path, root=archive_root)
    for name in ORACLE_SOURCE_FILES:
        path = archive_root / name
        add_source(path)

    for package in packages:
        directory = Path(package.get("Dir", ""))
        if not directory.is_absolute():
            raise OracleError("go list returned a nonabsolute package directory")
        file_fields = (
            "GoFiles", "CompiledGoFiles", "CgoFiles", "CFiles", "CXXFiles", "MFiles",
            "FFiles", "SFiles", "HFiles", "SysoFiles", "EmbedFiles", "TestGoFiles",
            "XTestGoFiles", "TestEmbedFiles", "XTestEmbedFiles",
        )
        for field in file_fields:
            names = package.get(field, [])
            if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
                raise OracleError("go list returned a malformed source file list")
            for name in names:
                add_source(directory / name)
        module = package.get("Module")
        if module is not None:
            if not isinstance(module, dict):
                raise OracleError("go list returned malformed module metadata")
            for module_info in (module, module.get("Replace")):
                if not isinstance(module_info, dict):
                    continue
                gomod = module_info.get("GoMod")
                if isinstance(gomod, str) and gomod:
                    path = Path(gomod)
                    add_module_file(path)
                    sibling_sum = path.with_name("go.sum")
                    if sibling_sum.is_file():
                        add_module_file(sibling_sum)

    go_bin = go_tool.resolve()
    _add_record(records, "sdk/bin/" + go_bin.name, go_bin, root=sdk_root)
    for relative in ("VERSION", "go.env"):
        path = sdk_root / relative
        if path.is_file():
            _add_record(records, "sdk/" + relative, path, root=sdk_root)
    tool_result = recorder.run("go-env-tool-dir-" + stage.removeprefix("go-list-"), [str(go_tool), "env", "GOTOOLDIR"], cwd=helper_root, env=env, timeout=30)
    tool_dir_raw = _require_zero(tool_result, "go env GOTOOLDIR")
    tool_dir = Path(tool_dir_raw.decode("utf-8").strip()).resolve()
    if not tool_dir.is_relative_to(sdk_root) or not tool_dir.is_dir():
        raise OracleError("Go compiler tool directory is not inside the installed SDK")
    for path in sorted(tool_dir.iterdir()):
        if path.is_file():
            _add_record(records, "sdk/" + path.resolve().relative_to(sdk_root).as_posix(), path, root=sdk_root)

    result = [{"path": name, "sha256": digest} for name, digest in sorted(records.items())]
    # GOOS/GOARCH are validated independently; retaining them in this call makes
    # the inventory's intended native identity explicit to the caller.
    if not goos or not goarch:
        raise OracleError("native Go target missing during input inventory")
    return result


def _require_explicit_git_root(root: Path) -> None:
    """Never let Git climb from a disposable artifact into a neighboring repo."""
    marker = root / ".git"
    try:
        mode = marker.lstat().st_mode
    except OSError as error:
        raise OracleError("capture requires Git metadata at the source root; refusing parent discovery") from error
    if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
        raise OracleError("source-root Git metadata is not a regular worktree marker")


def _verify_output_locations(output: Path, artifacts_dir: Path, target: tuple[str, str]) -> tuple[Path, Path]:

    expected = fixture_path(*target).resolve()
    output = output.expanduser().resolve()
    if output != expected:
        raise OracleError("capture output must be the new native frozen-v1 fixture path")
    if output.exists():
        raise OracleError("refusing to overwrite an existing frozen-v1 fixture")
    artifacts_dir = artifacts_dir.expanduser().resolve()
    if artifacts_dir.exists():
        raise OracleError("refusing to reuse an existing private capture artifact directory")
    fixture_root = FIXTURE_DIR.resolve()
    if artifacts_dir.is_relative_to(fixture_root):
        raise OracleError("raw Go capture artifacts must stay outside the tracked fixture directory")
    if artifacts_dir.is_relative_to(ROOT.resolve()):
        raise OracleError("private raw capture artifacts must stay outside the source checkout")
    return output, artifacts_dir


def _capture_payload(
    *, head_before: str,
    head_after: str,
    clean_before: bool,
    clean_after: bool,
    target: tuple[str, str],
    version: str,
    go_tool: Path,
    probe_binary_sha256: str,
    source_sha: str,
    source_files: list[dict[str, str]],
    candidate_files: list[dict[str, str]],
    inventory: list[dict[str, str]],
    commands: list[dict[str, Any]],
    observations: dict[str, Any],
    artifacts_id: str = "private-run",
) -> dict[str, Any]:
    groups = _group_digests(inventory)
    goos, goarch = target
    go_binary = go_tool.resolve()
    candidate_helper = next(item["sha256"] for item in candidate_files if item["path"] == "candidate/scripts/rust-port/go-oracle/cmd/fssecret/main.go")
    cases_record = next(item for item in commands if item["id"] == "go-cases")
    controls_record = next(item for item in commands if item["id"] == "go-path-controls")
    capture = {
        "oracle": {"commit": ORACLE, "source_sha256": source_sha, "source_files": source_files},
        "candidate": {
            "head_before": head_before, "head_after": head_after,
            "clean_before": clean_before, "clean_after": clean_after,
            "go_helper_sha256": candidate_helper, "files": candidate_files,
        },
        "native": {"goos": goos, "goarch": goarch},
        "go": {
            "version": version, "goversion": GO_VERSION, "goos": goos, "goarch": goarch,
            "binary_sha256": sha256(go_binary.read_bytes()), "goroot_label": "installed-go-sdk",
            "probe_binary_sha256": probe_binary_sha256,
            "gomodcache_policy": "existing-cache-offline-read-only",
            "sdk_sha256": groups["sdk"], "modules_sha256": groups["modules"],
        },
        "inputs": {
            "before_sha256": _inventory_digest(inventory), "after_sha256": _inventory_digest(inventory),
            "files": inventory, "groups": groups,
        },
        "commands": commands,
        "raw": {
            "artifact_id": artifacts_id,
            "observations": {
                "cases": {field: cases_record[field] for field in ("exit_code", "stdout_bytes", "stderr_bytes", "stdout_sha256", "stderr_sha256")},
                "path_controls": {field: controls_record[field] for field in ("exit_code", "stdout_bytes", "stderr_bytes", "stdout_sha256", "stderr_sha256")},
            },
        },
        "case_inventory": {"case_ids": list(CASE_IDS), "path_control_ids": list(PATH_CONTROL_IDS)},
    }
    return {"schema_version": 1, "capture": capture, "observations": observations}


def capture_native(output: Path, artifacts_dir: Path) -> Path:
    """Capture real Go output; requires GO_ORACLE=1 and a clean real Git source."""
    if os.environ.get("GO_ORACLE") != "1":
        raise OracleError("live Go capture requires explicit GO_ORACLE=1")
    target = _native_goos_arch()
    output, artifacts_dir = _verify_output_locations(output, artifacts_dir, target)
    _require_explicit_git_root(ROOT)
    artifacts_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    recorder = _Recorder(artifacts_dir)
    try:
        scratch_parent = _scratch_parent()
        with tempfile.TemporaryDirectory(prefix="fs-secret-capture-", dir=scratch_parent) as temporary:
            private = Path(temporary)
            base_env = _isolated_base_env(private, include_go=True)
            head_before, clean_before = _git_identity(recorder, base_env, "before")
            if not clean_before:
                raise OracleError("native Go capture requires a clean candidate checkout")
            pinned = _require_zero(
                recorder.run("git-verify-oracle", ["git", "rev-parse", "--verify", ORACLE + "^{commit}"], cwd=ROOT, env=base_env, timeout=30),
                "git verify pinned oracle",
            ).decode("ascii", "strict").strip()
            if pinned != ORACLE:
                raise OracleError("pinned Go oracle resolved to a different commit")

            archive_path = private / "pinned-go-oracle.tar"
            _require_zero(
                recorder.run("git-archive", ["git", "archive", "--format=tar", f"--output={archive_path}", ORACLE], cwd=ROOT, env=base_env, timeout=120),
                "git archive pinned oracle",
            )
            archive_root = private / "oracle-source"
            archive_root.mkdir()
            try:
                with tarfile.open(archive_path, mode="r:") as archive:
                    archive.extractall(archive_root, filter="data")
            except (OSError, tarfile.TarError) as error:
                raise OracleError("pinned Go source archive could not be safely extracted") from error
            source_sha, source_files = _hash_source_files(archive_root)

            go_tmp = private / "go-work"
            go_tmp.mkdir()
            go_env_artifacts = artifacts_dir / "go-environment"
            try:
                # Resolve installed, read-only compiler/cache locations before
                # changing HOME; the isolated home has no downloaded toolchain.
                go_tool = _static_oracle._resolve_go_tool(go_env_artifacts)
                module_cache = _require_zero(recorder.run(
                    "go-env-module-cache", [str(go_tool), "env", "GOMODCACHE"],
                    cwd=ROOT, env=dict(os.environ, GOTOOLCHAIN="local", GOENV="off", GOWORK="off"),
                    timeout=30,
                ), "discover installed module cache").decode("utf-8").strip()
                base_env.update(GO_ORACLE_BIN=str(go_tool), GOMODCACHE=module_cache)
                with mock.patch.dict(os.environ, base_env, clear=True):
                    prepared = _static_oracle._prepare_go_env(go_tmp, go_env_artifacts)
            finally:
                recorder.collect_runner_records(go_env_artifacts, "go-env")
            env, version, goroot, goos, goarch, gomodcache, go_tool = prepared
            if (goos, goarch) != target or version != f"go version {GO_VERSION} {goos}/{goarch}":
                raise OracleError("executed Go compiler is not pinned 1.26.6 for this native target")
            if not Path(gomodcache).is_dir() or Path(env["GOMODCACHE"]).resolve() != Path(gomodcache).resolve():
                raise OracleError("existing Go module cache is unavailable or changed")
            env.update({
                "GOENV": "off", "GOWORK": "off", "GOTOOLCHAIN": "local", "CGO_ENABLED": "0",
                "GOPROXY": "off", "GOSUMDB": "off", "GOFLAGS": "-mod=readonly",
                "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
                "GIT_OPTIONAL_LOCKS": "0", "GIT_ALLOW_PROTOCOL": "file",
            })

            helper_root = private / "go-helper"
            helper_root.mkdir()
            helper_source = ROOT / "scripts/rust-port/go-oracle"
            (helper_root / "cmd/fssecret").mkdir(parents=True)
            shutil.copyfile(helper_source / "go.mod", helper_root / "go.mod")
            shutil.copyfile(helper_source / "go.sum", helper_root / "go.sum")
            shutil.copyfile(helper_source / "cmd/fssecret/main.go", helper_root / "cmd/fssecret/main.go")
            original_mod = (helper_root / "go.mod").read_text(encoding="utf-8")
            replace_line = "replace github.com/danieljustus/symaira-corekit => ../../.."
            if original_mod.count(replace_line) != 1:
                raise OracleError("current Go helper module replacement no longer matches the reviewed layout")
            replacement = json.dumps(archive_root.as_posix(), ensure_ascii=False)
            modfile = private / "oracle.mod"
            modfile.write_text(original_mod.replace(replace_line, "replace github.com/danieljustus/symaira-corekit => " + replacement), encoding="utf-8")
            shutil.copyfile(helper_root / "go.sum", private / "oracle.sum")
            binary = private / ("fssecret.exe" if os.name == "nt" else "fssecret")

            inventory_before = _discover_input_inventory(
                recorder, go_tool, env, helper_root, modfile, archive_root, goos, goarch, "go-list-before",
            )
            build = recorder.run(
                "go-build",
                [str(go_tool), "build", "-trimpath", "-modfile", str(modfile), "-o", str(binary), "./cmd/fssecret"],
                cwd=helper_root, env=env, timeout=180,
            )
            _require_zero(build, "build pinned Go oracle probe")
            if not binary.is_file():
                raise OracleError("Go compiler did not produce the oracle probe binary")
            probe_binary_sha256 = sha256(binary.read_bytes())
            shutil.copyfile(binary, artifacts_dir / "go-probe.binary")
            oracle_result = recorder.run("go-cases", [str(binary)], cwd=helper_root, env=env, timeout=180)
            oracle_raw = _require_zero(oracle_result, "run pinned Go FS/SEC oracle")
            go_probe = _decode_json(oracle_raw, "Go FS/SEC probe")
            path_result = recorder.run("go-path-controls", [str(binary), "--path-controls"], cwd=helper_root, env=env, timeout=60)
            path_raw = _require_zero(path_result, "run pinned Go path-control oracle")
            path_controls = _decode_json(path_raw, "Go path-control probe")
            if not isinstance(go_probe, dict) or set(go_probe) != {"oracle_commit", "native_target", "cases"}:
                raise OracleError("Go oracle probe returned an unexpected root schema")
            if go_probe["oracle_commit"] != ORACLE or go_probe["native_target"] != _target_key(goos, goarch):
                raise OracleError("Go probe emitted the wrong production revision or native target")
            if not isinstance(go_probe["cases"], dict) or set(go_probe["cases"]) != set(CASE_IDS) or len(go_probe["cases"]) != 13:
                raise OracleError("Go oracle did not execute exactly all 13 FS/SEC cases")
            if not isinstance(path_controls, dict) or set(path_controls) != set(PATH_CONTROL_IDS) or len(path_controls) != 9:
                raise OracleError("Go path-control probe did not return all nine named ASCII keys")
            if any(type(path_controls[key]) is not bool for key in PATH_CONTROL_IDS):
                raise OracleError("Go path-control values must be actual JSON booleans")
            if any(path_controls[key] is not True for key in STRICT_V1_GO_ACCEPTED):
                raise OracleError("Go must accept the versioned FS-001 strict-v1 DEL/C1 controls")

            inventory_after = _discover_input_inventory(
                recorder, go_tool, env, helper_root, modfile, archive_root, goos, goarch, "go-list-after",
            )
            if inventory_before != inventory_after:
                raise OracleError("Go transitive source/module/SDK inputs changed during capture")
            if sha256(binary.read_bytes()) != probe_binary_sha256:
                raise OracleError("Go probe executable changed during capture")
            head_after, clean_after = _git_identity(recorder, env, "after")
            if head_after != head_before or not clean_after:
                raise OracleError("candidate HEAD or clean source state changed during Go capture")

            candidate_files = _candidate_file_records(ROOT)
            payload = _capture_payload(
                head_before=head_before, head_after=head_after, clean_before=clean_before, clean_after=clean_after,
                target=target, version=version, go_tool=go_tool, source_sha=source_sha,
                probe_binary_sha256=probe_binary_sha256,
                source_files=source_files, candidate_files=candidate_files,
                inventory=inventory_before, commands=recorder.commands,
                observations={
                    "oracle_commit": ORACLE,
                    "native_target": _target_key(goos, goarch),
                    "cases": go_probe["cases"],
                    "path_controls": path_controls,
                },
            )
            validate_capture_payload(payload, target)
            serialized = _json_bytes(payload)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as stream:
                stream.write(serialized)
            recorder.finish("captured-unreviewed", fixture_sha256=sha256(serialized))
            return output
    except BaseException as error:
        recorder.finish("failed-unreviewed", error_type=type(error).__name__)
        raise


def _validate_fixture_location(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise OracleError("replay fixture must not be a symlink")
    resolved = expanded.resolve()
    fixture_root = FIXTURE_DIR.resolve()
    if not resolved.is_relative_to(fixture_root):
        raise OracleError("replay fixture must be under the FS/SEC frozen-v1 fixture directory")
    return resolved


def _cargo_environment(private: Path, target_dir: Path) -> dict[str, str]:
    env = _isolated_base_env(private)
    env["CARGO_HOME"] = os.environ.get("CARGO_HOME", str(Path.home() / ".cargo"))
    env["RUSTUP_HOME"] = os.environ.get("RUSTUP_HOME", str(Path.home() / ".rustup"))
    env["CARGO_TARGET_DIR"] = str(target_dir)
    env["CARGO_NET_OFFLINE"] = "true"
    env["CARGO_INCREMENTAL"] = "0"
    env["CARGO_TERM_COLOR"] = "never"
    env["RUSTUP_AUTO_INSTALL"] = "0"
    return env


def _rust_runtime_environment(private: Path, helper_dir: Path, mode_file: Path, argv_file: Path, controls: dict[str, bool] | None = None) -> dict[str, str]:
    env = _isolated_base_env(private)
    env["PATH"] = str(helper_dir) + os.pathsep + os.environ.get("PATH", "")
    env["RUST003_HELPER_MODE_FILE"] = str(mode_file)
    env["RUST003_HELPER_ARGV"] = str(argv_file)
    env["RUST003_HELPER_MODE"] = "success"
    if controls is not None:
        env["RUST_FS_GO_PATH_CONTROLS"] = "\n".join(f"{key}\t{str(controls[key]).lower()}" for key in PATH_CONTROL_IDS)
    return env


def _recorded_path_controls(observations: dict[str, Any]) -> dict[str, bool]:
    controls = observations["path_controls"]
    if not isinstance(controls, dict) or set(controls) != set(PATH_CONTROL_IDS):
        raise OracleError("captured Go path-control inventory is incomplete")
    if any(type(controls[key]) is not bool for key in PATH_CONTROL_IDS):
        raise OracleError("captured Go path-control inventory has non-boolean values")
    if any(controls[key] is not True for key in STRICT_V1_GO_ACCEPTED):
        raise OracleError("Go strict-v1 DEL/C1 acceptance invariant is absent")
    return controls


def replay_native(fixture: Path | None = None) -> dict[str, Any]:
    """Default acceptance route: anchored bytes, isolated Cargo/Rust only."""
    target = _native_goos_arch()
    path = fixture_path(*target) if fixture is None else _validate_fixture_location(fixture)
    _, payload = read_capture_once(path, target)
    _verify_candidate_files(payload["capture"], ROOT)
    observations = payload["observations"]
    go_controls = _recorded_path_controls(observations)

    scratch_parent = _scratch_parent()
    replay_root = Path(tempfile.mkdtemp(prefix="fs-secret-replay-", dir=scratch_parent))
    os.chmod(replay_root, 0o700)
    logs = replay_root / "logs"
    logs.mkdir(mode=0o700)
    recorder = _Recorder(logs)
    successful = False
    try:
        target_dir = replay_root / "cargo-target"
        env = _cargo_environment(replay_root / "cargo-home-scope", target_dir)
        cargo_manifest = ROOT / "Cargo.toml"
        metadata = recorder.run(
            "cargo-metadata",
            ["cargo", "metadata", "--offline", "--locked", "--no-deps", "--format-version", "1", "--manifest-path", str(cargo_manifest)],
            cwd=ROOT, env=env, timeout=120,
        )
        metadata_raw = _require_zero(metadata, "candidate Cargo metadata")
        _validate_cargo_metadata(metadata_raw, ROOT, target_dir)
        build = recorder.run(
            "cargo-build-rust-fs-secret",
            ["cargo", "build", "--manifest-path", str(cargo_manifest), "-p", "symaira-core-foundation", "--bin", "rust-fs-secret", "--locked", "--offline", "--target-dir", str(target_dir)],
            cwd=ROOT, env=env, timeout=600,
        )
        _require_zero(build, "build candidate Rust probe")
        rust_binary = target_dir / "debug" / ("rust-fs-secret.exe" if os.name == "nt" else "rust-fs-secret")
        if not rust_binary.is_file():
            raise OracleError("Cargo did not produce the candidate rust-fs-secret binary")

        isolated = replay_root / "runtime"
        for name in ("home", "xdg-cache", "xdg-config", "xdg-data", "xdg-state", "tmp", "helpers"):
            (isolated / name).mkdir(parents=True, exist_ok=True)
        mode_file = isolated / "helper-mode"
        mode_file.write_text("success", encoding="utf-8")
        argv_file = isolated / "helper-argv.json"
        for name in ("symvault", "security"):
            helper = isolated / "helpers" / (name + (".exe" if os.name == "nt" else ""))
            shutil.copy2(rust_binary, helper)
            if os.name != "nt":
                helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
        runtime_env = _rust_runtime_environment(isolated, isolated / "helpers", mode_file, argv_file)
        probe = recorder.run("rust-probe", [str(rust_binary)], cwd=ROOT, env=runtime_env, timeout=180)
        rust_raw = _require_zero(probe, "execute actual Rust FS/SEC probe")
        rust_probe = _decode_json(rust_raw, "Rust FS/SEC probe")
        if not isinstance(rust_probe, dict) or not isinstance(rust_probe.get("cases"), dict):
            raise OracleError("Rust probe output schema is incomplete")
        compare_observations(observations, rust_probe)

        # Mutation A changes an observable FS-001 Go value and must not compare
        # equal to the already-executed actual Rust probe.
        mutated_observations = copy.deepcopy(observations)
        mutated_observations["cases"] = mutate_known_observation({"cases": observations["cases"]})["cases"]
        try:
            compare_observations(mutated_observations, rust_probe)
        except OracleError:
            pass
        else:
            raise OracleError("13-row FS-001 observable mutation was not rejected by Rust comparison")

        test_command = [
            "cargo", "test", "--locked", "--offline", "--target-dir", str(target_dir),
            "--manifest-path", str(cargo_manifest), "-p", "symaira-core-fs", "--test", "parity",
            "fs001_strict_v1_replays_go_controls", "--", "--exact", "--ignored", "--nocapture",
        ]
        test_env = dict(env)
        test_env.update(_rust_runtime_environment(isolated, isolated / "helpers", mode_file, argv_file, go_controls))
        passing = recorder.run("rust-path-controls-pass", test_command, cwd=ROOT, env=test_env, timeout=180)
        _assert_named_test_result(passing, passed=True)

        # Mutation B flips the captured 007f result and re-executes the exact
        # named Rust boundary. Only its intentional Go-acceptance assertion is a
        # passing negative control; compile errors and zero-test runs are rejected.
        changed_controls = dict(go_controls)
        changed_controls["007f"] = not changed_controls["007f"]
        mutation_env = dict(env)
        mutation_env.update(_rust_runtime_environment(isolated, isolated / "helpers", mode_file, argv_file, changed_controls))
        negative = recorder.run("rust-path-controls-mutation", test_command, cwd=ROOT, env=mutation_env, timeout=180)
        _assert_named_test_result(negative, passed=False, exact_reason="Go must actually accept the versioned control case")
        recorder.finish("replay-passed")
        successful = True
        return {
            "oracle_commit": ORACLE,
            "native_target": _target_key(*target),
            "fs_sec_case_count": len(CASE_IDS),
            "path_control_count": len(PATH_CONTROL_IDS),
            "rust_named_test": "fs001_strict_v1_replays_go_controls",
            "rust_named_test_passes": 1,
            "mutations": ["FS-001 observable mismatch", "007f Go acceptance assertion"],
        }
    except BaseException as error:
        recorder.finish("replay-failed", error_type=type(error).__name__)
        raise
    finally:
        if successful:
            shutil.rmtree(replay_root)


def _capture_cli(args) -> int:
    if os.environ.get("GO_ORACLE") != "1":
        raise OracleError("live Go capture requires explicit GO_ORACLE=1")
    if args.output is None or args.artifacts_dir is None:
        raise OracleError("capture requires --output NEWPATH and --artifacts-dir")
    result = capture_native(args.output, args.artifacts_dir)
    goos, goarch = _native_goos_arch()
    print(json.dumps({
        "status": "captured-unreviewed",
        "native_target": _target_key(goos, goarch),
        "fixture": result.relative_to(ROOT).as_posix(),
        "case_count": len(CASE_IDS),
        "path_control_count": len(PATH_CONTROL_IDS),
        "anchor_registered": False,
    }, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true", help="capture fresh pinned Go output; requires GO_ORACLE=1")
    parser.add_argument("--output", type=Path, help="new native frozen-v1 fixture path; capture only")
    parser.add_argument("--artifacts-dir", type=Path, help="new private raw-log directory; capture only")
    parser.add_argument("--fixture", type=Path, help="explicit frozen-v1 replay path (must remain under the fixture directory)")
    args = parser.parse_args(argv)
    try:
        if args.capture:
            if args.fixture is not None:
                raise OracleError("--fixture is replay-only")
            return _capture_cli(args)
        if args.output is not None or args.artifacts_dir is not None:
            raise OracleError("--output and --artifacts-dir are capture-only")
        result = replay_native(args.fixture)
        print(json.dumps({"status": "PASS", **result}, sort_keys=True))
        return 0
    except Exception as error:
        detail = f": {error}" if isinstance(error, OracleError) else ""
        print(f"FAIL FS/SEC frozen-v1: {type(error).__name__}{detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
