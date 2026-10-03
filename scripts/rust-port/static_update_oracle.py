#!/usr/bin/env python3
"""Versioned static Go observations and explicit, isolated Go recapture tools."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

from static_update_anchors import ANCHORS, HISTORICAL_ANCHORS
from bounded_oracle_process import run_checked

ROOT = Path(__file__).resolve().parents[2]
UPDATE_FIXTURES = ROOT / "testdata/rust-port/fixtures/update"
HISTORICAL_ROOT = UPDATE_FIXTURES / "static-v1"
STATIC_ROOT = UPDATE_FIXTURES / "static-v2"
INDEX_PATH = STATIC_ROOT / "index-v2.json"
MANIFEST = ROOT / "rust/symaira-core-update/Cargo.toml"
GO_TOOLCHAIN = "go1.26.6"

LANES = {
    "version": {
        "count": 30,
        "legacy": "stable-versions.json",
        "fixture": "version.json",
        "case_path": ("cases",),
        "oracle": ("scripts/rust-port/update-oracle/main.go",),
        "source": ("updatecheck/updatecheck.go",),
        "command": ("go", "run", "./scripts/rust-port/update-oracle"),
    },
    "response": {
        "count": 9,
        "legacy": "responses.json",
        "fixture": "response.json",
        "case_path": ("cases",),
        "oracle": ("scripts/rust-port/update-response-oracle/main.go",),
        "source": ("updatecheck/updatecheck.go",),
        "command": ("go", "run", "./scripts/rust-port/update-response-oracle"),
    },
    "install-method": {
        "count": 15,
        "legacy": "install-methods.json",
        "fixture": "install-method.json",
        "case_path": ("cases",),
        "oracle": ("scripts/rust-port/install-method-oracle/main.go",),
        "source": ("updatecheck/installmethod/detect.go",),
        "command": ("go", "run", "./scripts/rust-port/install-method-oracle"),
    },
    "extract": {
        "count": 12,
        "legacy": "extract.json",
        "fixture": "extract.json",
        "case_path": ("cases",),
        "oracle": ("scripts/rust-port/update-extract-oracle/main.go",),
        "source": ("updatecheck/extract/extract.go",),
        "command": ("build-and-run", "./scripts/rust-port/update-extract-oracle"),
    },
    "swap": {
        "count": 8,
        "legacy": "swap.json",
        "fixture": "swap.json",
        "case_path": ("cases",),
        "oracle": ("updatecheck/updateapply/atomic_swap_oracle_test.go",),
        "source": ("updatecheck/updateapply/updateapply.go",),
        "command": ("go", "test", "-count=1", "-run", "^TestAtomicSwapOracle$", "./updatecheck/updateapply"),
    },
    "checker": {
        "count": 21,
        "legacy": "checker.json",
        "fixture": "checker.json",
        "case_path": ("observations", "cases"),
        "oracle": ("scripts/rust-port/update-checker-oracle/main.go",),
        "source": ("updatecheck/updatecheck.go",),
        "command": ("go", "run", "./scripts/rust-port/update-checker-oracle"),
    },
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _goos_arch(goos: str, goarch: str) -> str:
    return f"{goos}-{goarch}"


def native_goos_arch() -> tuple[str, str]:
    if sys.platform == "darwin":
        goos = "darwin"
    elif sys.platform.startswith("linux"):
        goos = "linux"
    elif sys.platform.startswith("win"):
        goos = "windows"
    else:
        goos = platform.system().lower()
    arch = platform.machine().lower()
    goarch = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64", "amd64": "amd64"}.get(arch, arch)
    return goos, goarch


def fixture_path(lane: str, root: Path = ROOT, target: tuple[str, str] | None = None, *, historical: bool = False) -> Path:
    if lane not in LANES:
        raise ValueError(f"unknown static update lane: {lane}")
    goos, goarch = target or native_goos_arch()
    generation = "static-v1" if historical else "static-v2"
    return root / "testdata/rust-port/fixtures/update" / generation / _goos_arch(goos, goarch) / LANES[lane]["fixture"]


def _at_path(value, keys):
    for key in keys:
        value = value[key]
    return value


def case_ids(lane: str, payload: dict) -> list[str]:
    cases = _at_path(payload, LANES[lane]["case_path"])
    if lane == "version":
        return [f"stable-version-{index:03d}" for index in range(1, len(cases) + 1)]
    if lane == "swap":
        return [case["input"]["id"] for case in cases]
    return [case["id"] for case in cases]


def validate_capture(lane: str, path: Path, root: Path = ROOT, *, diagnostic: bool = False) -> dict:
    """Require reviewed bytes and native provenance; dirty history is diagnostic only."""
    if lane not in LANES:
        raise ValueError(f"unknown static update lane: {lane}")
    if not path.is_file():
        raise ValueError(f"missing native {lane} Go capture: {path}")
    historical = path.resolve().is_relative_to((root / "testdata/rust-port/fixtures/update/static-v1").resolve())
    generation = "static-v1" if historical else "static-v2"
    index_path = root / "testdata/rust-port/fixtures/update" / generation / "index-v2.json"
    if not index_path.is_file():
        raise ValueError(f"missing static update provenance index: {index_path}")
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read static {lane} Go capture: {error}") from error
    if type(index.get("schema_version")) is not int or index["schema_version"] != 2:
        raise ValueError("unsupported static update provenance index version")
    goos, goarch = native_goos_arch()
    key = "/".join((goos, goarch, lane))
    entry = index.get("captures", {}).get(key)
    if not isinstance(entry, dict):
        raise ValueError(f"missing {lane} provenance entry")
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    if entry.get("path") != relative or path.resolve() != fixture_path(lane, root=root, historical=historical).resolve():
        raise ValueError(f"{lane} provenance path mismatch")
    if entry.get("sha256") != sha256(raw):
        raise ValueError(f"{lane} Go capture digest mismatch")
    capture = _validate_payload(lane, payload, (goos, goarch))
    if capture["capturer_sha256"] != entry.get("capturer_sha256"):
        raise ValueError(f"{lane} capture helper digest mismatch")
    if type(entry.get("working_tree_clean")) is not bool:
        raise ValueError(f"{lane} working_tree_clean must be boolean")
    if capture["source_commit"] != entry.get("source_commit") or capture["working_tree_clean"] != entry["working_tree_clean"]:
        raise ValueError(f"{lane} source identity mismatch")
    if type(entry.get("case_count")) is not int or entry["case_count"] != capture["case_count"] or entry.get("case_ids") != capture["case_ids"]:
        raise ValueError(f"{lane} provenance case inventory mismatch")
    if (entry.get("goos"), entry.get("goarch")) != (goos, goarch):
        raise ValueError(f"{lane} native platform identity mismatch")
    anchors = HISTORICAL_ANCHORS if historical else ANCHORS
    if anchors.get(key) != sha256(raw):
        raise ValueError(f"{lane} independently reviewed capture anchor mismatch")
    if not diagnostic and not capture["working_tree_clean"]:
        raise ValueError(f"{lane} dirty capture is diagnostic only; clean source-bound recapture required")
    if historical and not diagnostic:
        raise ValueError(f"{lane} historical capture is diagnostic only")
    if not diagnostic and capture.get("capture_mode") != "fresh-pinned-go-execution-additive-v2":
        raise ValueError(f"{lane} acceptance requires verified pre-execution transitive inputs")
    return payload


def _validate_payload(lane: str, payload: dict, target: tuple[str, str] | None = None) -> dict:
    """Apply one structural contract before registration and on replay."""
    if not isinstance(payload, dict):
        raise ValueError(f"{lane} capture payload must be an object")
    capture = payload.get("capture")
    if not isinstance(capture, dict) or type(capture.get("schema_version")) is not int or capture["schema_version"] != 1:
        raise ValueError(f"{lane} capture lacks versioned provenance")
    if capture.get("lane") != lane:
        raise ValueError(f"{lane} capture lane mismatch")
    # The producer is historical. The independent whole-capture anchor binds its
    # identity; changing the validator must not relabel a historical execution.
    for field, pattern in (("source_commit", r"[0-9a-f]{40}"), ("capturer_sha256", r"[0-9a-f]{64}")):
        if not isinstance(capture.get(field), str) or re.fullmatch(pattern, capture[field]) is None:
            raise ValueError(f"{lane} invalid required provenance field: {field}")
    if type(capture.get("working_tree_clean")) is not bool:
        raise ValueError(f"{lane} working_tree_clean must be boolean")
    dirty_paths = capture.get("dirty_paths")
    if not isinstance(dirty_paths, list) or any(not isinstance(item, str) for item in dirty_paths):
        raise ValueError(f"{lane} missing or malformed dirty-path inventory")
    if capture["working_tree_clean"] != (not dirty_paths):
        raise ValueError(f"{lane} dirty-path inventory contradicts source status")
    for field in ("source_files", "oracle_files", "go_module_inputs"):
        files = capture.get(field)
        if not isinstance(files, list) or not files:
            raise ValueError(f"{lane} missing required provenance inventory: {field}")
        seen = set()
        for item in files:
            if not isinstance(item, dict):
                raise ValueError(f"{lane} malformed provenance inventory: {field}")
            name, digest = item.get("path"), item.get("sha256")
            if not isinstance(name, str) or not name or name.startswith("/") or "\\" in name or ":" in name or any(part in ("", ".", "..") for part in name.split("/")) or name in seen:
                raise ValueError(f"{lane} invalid provenance input path: {field}")
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ValueError(f"{lane} invalid provenance input digest: {field}")
            seen.add(name)
    try:
        cases = _at_path(payload, LANES[lane]["case_path"])
        ids = case_ids(lane, payload)
    except (KeyError, TypeError) as error:
        raise ValueError(f"{lane} capture lacks a valid case inventory") from error
    if not isinstance(cases, list) or len(cases) != LANES[lane]["count"]:
        raise ValueError(f"{lane} capture case count mismatch")
    if any(not isinstance(item, str) or not item for item in ids) or len(set(ids)) != len(ids) or ids != capture.get("case_ids"):
        raise ValueError(f"{lane} capture case IDs mismatch")
    if type(capture.get("case_count")) is not int or capture["case_count"] != len(cases):
        raise ValueError(f"{lane} provenance case inventory mismatch")
    if capture.get("case_fingerprints_sha256") != _case_fingerprints(lane, payload):
        raise ValueError(f"{lane} case fingerprint inventory mismatch")
    go = capture.get("go")
    if not isinstance(go, dict) or go.get("goos") not in ("darwin", "linux", "windows") or go.get("goarch") not in ("amd64", "arm64"):
        raise ValueError(f"{lane} invalid Go platform identity")
    if go.get("version") != "go version go1.26.6 " + go["goos"] + "/" + go["goarch"]:
        raise ValueError(f"{lane} capture does not record executed Go 1.26.6 identity")
    if target is not None and (go["goos"], go["goarch"]) != target:
        raise ValueError(f"{lane} native platform identity mismatch")
    raw_record = capture.get("raw")
    raw_exit = raw_record.get("exit_code") if isinstance(raw_record, dict) else None
    if type(raw_exit) is not int or raw_exit != 0:
        raise ValueError(f"{lane} capture records a failed Go execution")
    if capture.get("capture_mode") == "fresh-pinned-go-execution-additive-v2":
        snapshot = {name: capture[name] for name in ("source_commit", "working_tree_clean", "dirty_paths", "source_files")}
        snapshot["go_binary_sha256"] = go.get("binary_sha256")
        if capture.get("input_inventory_verified") is not True or capture.get("input_snapshot_sha256") != sha256(canonical_json(snapshot)):
            raise ValueError(f"{lane} invalid verified input snapshot")
    return capture


def _source_files(lane: str) -> list[Path]:
    spec = LANES[lane]
    paths = [ROOT / path for path in spec["source"] + spec["oracle"]]
    # The package sources and test files participate in Go compilation. Include all
    # files for the narrow package plus the explicit runner above, not all of Go.
    package_dir = (ROOT / spec["source"][0]).parent
    for path in sorted(package_dir.glob("*.go")):
        if path not in paths:
            paths.append(path)
    if lane == "swap":
        for path in sorted(package_dir.glob("*_test.go")):
            if path not in paths:
                paths.append(path)
    for path in (ROOT / "go.mod", ROOT / "go.sum"):
        if path.is_file() and path not in paths:
            paths.append(path)
    return paths


def _source_inventory(lane: str, go_tool: Path, env: dict[str, str], artifacts_dir: Path | None = None) -> list[dict]:
    """Discover actual transitive native build inputs, including SDK and module files."""
    package = "./" + str(Path(LANES[lane]["oracle"][0]).parent).replace(os.sep, "/")
    fields = "Dir,GoFiles,CgoFiles,CFiles,CXXFiles,MFiles,FFiles,SFiles,HFiles,SysoFiles,EmbedFiles,TestGoFiles,XTestGoFiles,TestEmbedFiles,XTestEmbedFiles,Module"
    command = [str(go_tool), "list", "-deps", "-json=" + fields]
    if lane == "swap":
        command.append("-test")
    result = run_checked([*command, package], cwd=ROOT, env=env, timeout=30, artifact_dir=artifacts_dir)
    if result.returncode != 0:
        raise RuntimeError("cannot discover complete Go oracle build inputs")
    decoder = json.JSONDecoder()
    text = result.stdout.decode("utf-8")
    paths = set(_source_files(lane))
    while text.strip():
        text = text.lstrip()
        obj, end = decoder.raw_decode(text)
        text = text[end:]
        directory = Path(obj["Dir"])
        for field in fields.split(",")[1:-1]:
            paths.update(directory / name for name in obj.get(field, []))
        module = obj.get("Module")
        if isinstance(module, dict):
            for effective in (module, module.get("Replace", {})):
                if effective.get("GoMod"):
                    mod = Path(effective["GoMod"])
                    paths.add(mod)
                    if mod.with_name("go.sum").is_file():
                        paths.add(mod.with_name("go.sum"))
    tool_dir = run_checked([str(go_tool), "env", "GOTOOLDIR"], cwd=ROOT, env=env, timeout=30, artifact_dir=artifacts_dir, check=True)
    paths.update(path for path in Path(tool_dir.stdout.decode().strip()).iterdir() if path.is_file())
    paths.update((go_tool, Path(__file__), Path(__file__).with_name("static_update_anchors.py"), Path(__file__).with_name("bounded_oracle_process.py"), UPDATE_FIXTURES / LANES[lane]["legacy"]))
    if lane == "extract":
        paths.update(path for path in (ROOT / "scripts/rust-port/update-extract-oracle/testdata").rglob("*") if path.is_file())
    roots = [("toolchain", Path(env["GOROOT"]).resolve()), ("modules", Path(env["GOMODCACHE"]).resolve()),
             ("generated", Path(env["GOCACHE"]).resolve()), ("repository", ROOT.resolve())]
    files = {}
    for original in paths:
        path = original.resolve()
        if not path.is_file():
            raise ValueError("missing Go capture input")
        name = next((scope + "/" + path.relative_to(root).as_posix() for scope, root in roots if path.is_relative_to(root)), None)
        if name is None:
            raise ValueError("Go oracle input escapes repository, toolchain and module roots")
        files[name] = {"path": name, "sha256": sha256(path.read_bytes())}
    return [files[key] for key in sorted(files)]


def _capture_inputs(lane: str, go_tool: Path, env: dict[str, str], artifacts_dir: Path | None = None) -> dict:
    files = _source_inventory(lane, go_tool, env, artifacts_dir)
    status = run_checked(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=ROOT, env=env, timeout=30, artifact_dir=artifacts_dir, check=True)
    head = run_checked(["git", "rev-parse", "HEAD"], cwd=ROOT, env=env, timeout=30, artifact_dir=artifacts_dir, check=True)
    binary_name = "toolchain/" + go_tool.relative_to(Path(env["GOROOT"]).resolve()).as_posix()
    binary_digest = next(item["sha256"] for item in files if item["path"] == binary_name)
    return {"source_commit": head.stdout.decode().strip(), "working_tree_clean": not bool(status.stdout.strip()),
            "dirty_paths": [line[3:].decode("utf-8", "replace") for line in status.stdout.splitlines()],
            "source_files": files, "go_binary_sha256": binary_digest}


def _case_fingerprints(lane: str, payload: dict) -> list[str]:
    cases = _at_path(payload, LANES[lane]["case_path"])
    return [sha256(canonical_json(case)) for case in cases]


def _run(command: list[str], env: dict[str, str], cwd: Path, stage: str, artifacts_dir: Path | None = None) -> dict:
    result = run_checked(command, cwd=cwd, env=env, timeout=120, artifact_dir=artifacts_dir)
    temp_root = Path(env["TMPDIR"]).parent
    command_record = []
    for item in command:
        if item == str(Path(env["GOROOT"]) / "bin" / ("go.exe" if os.name == "nt" else "go")):
            command_record.append("go")
            continue
        try:
            command_record.append("<scratch>/" + Path(item).relative_to(temp_root).as_posix())
        except (ValueError, TypeError):
            command_record.append(item)
    return {
        "stage": stage,
        "command": command_record,
        "cwd": "repository" if cwd == ROOT else "isolated-extract-fixture-root",
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _resolve_go_tool(artifacts_dir: Path | None = None) -> Path:
    """Resolve the effective pinned compiler before changing HOME, without downloads."""
    launcher = os.environ.get("GO_ORACLE_BIN", "go")
    env = dict(os.environ, GOTOOLCHAIN=GO_TOOLCHAIN, GOPROXY="off", GOSUMDB="off", GOENV="off", GOWORK="off")
    result = run_checked([launcher, "env", "GOROOT"], env=env, cwd=ROOT, timeout=30, artifact_dir=artifacts_dir)
    if result.returncode != 0:
        raise RuntimeError("cannot resolve an installed pinned Go compiler")
    goroot = Path(result.stdout.decode("utf-8").strip())
    if not goroot.is_absolute():
        raise RuntimeError("Go compiler discovery returned a nonabsolute SDK root")
    tool = goroot / "bin" / ("go.exe" if os.name == "nt" else "go")
    if not tool.is_file():
        raise RuntimeError("resolved Go SDK has no compiler executable")
    return tool.resolve()


def _prepare_go_env(temp: Path, artifacts_dir: Path | None = None) -> tuple[dict[str, str], str, str, str, str, str, Path]:
    go_tool = _resolve_go_tool(artifacts_dir)
    env = dict(os.environ)
    base_env = dict(os.environ, GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off", GOFLAGS="-mod=readonly", GOENV="off", GOWORK="off")
    base_modcache = run_checked([str(go_tool), "env", "GOMODCACHE"], env=base_env, cwd=ROOT, timeout=30, artifact_dir=artifacts_dir)
    if base_modcache.returncode != 0:
        raise RuntimeError("cannot resolve existing Go module cache: " + base_modcache.stderr.decode("utf-8", "replace"))
    gomodcache = base_modcache.stdout.decode("utf-8").strip()
    if not Path(gomodcache).is_dir():
        raise RuntimeError(f"existing Go module cache is unavailable: {gomodcache}")
    for name in ("home", "xdg", "config", "data", "state", "tmp", "gocache"):
        (temp / name).mkdir(parents=True, exist_ok=True)
    env.update({
        "HOME": str(temp / "home"),
        "USERPROFILE": str(temp / "home"),
        "XDG_CACHE_HOME": str(temp / "xdg"),
        "XDG_CONFIG_HOME": str(temp / "config"),
        "XDG_DATA_HOME": str(temp / "data"),
        "XDG_STATE_HOME": str(temp / "state"),
        "APPDATA": str(temp / "config"),
        "LOCALAPPDATA": str(temp / "data"),
        "TMPDIR": str(temp / "tmp"),
        "TMP": str(temp / "tmp"),
        "TEMP": str(temp / "tmp"),
        "GOCACHE": str(temp / "gocache"),
        "GOTOOLCHAIN": "local",
        "GOPROXY": "off",
        "GOSUMDB": "off",
        "GOFLAGS": "-mod=readonly",
        "GOMODCACHE": gomodcache,
        "CGO_ENABLED": "0",
        "GOENV": "off",
        "GOWORK": "off",
    })
    actual = run_checked([str(go_tool), "version"], env=env, cwd=ROOT, timeout=30, artifact_dir=artifacts_dir)
    if actual.returncode != 0:
        raise RuntimeError("pinned Go version command failed: " + actual.stderr.decode("utf-8", "replace"))
    version = actual.stdout.decode("utf-8").strip()
    if not version.startswith("go version go1.26.6 "):
        raise RuntimeError(f"expected executed go1.26.6 compiler, got {version}")
    env_output = run_checked([str(go_tool), "env", "GOVERSION", "GOROOT", "GOOS", "GOARCH", "GOMODCACHE"], env=env, cwd=ROOT, timeout=30, artifact_dir=artifacts_dir)
    if env_output.returncode != 0:
        raise RuntimeError("pinned Go env command failed: " + env_output.stderr.decode("utf-8", "replace"))
    goversion, goroot, goos, goarch, gomodcache = env_output.stdout.decode("utf-8").splitlines()
    if goversion != "go1.26.6":
        raise RuntimeError(f"go env reported unexpected compiler {goversion}")
    if (goos, goarch) != native_goos_arch():
        raise RuntimeError("Go compiler target does not match the native capture platform")
    env["GOMODCACHE"] = gomodcache
    env["GOROOT"] = goroot
    return env, version, goroot, goos, goarch, gomodcache, go_tool


def _build_payload(lane: str, output: bytes, generated_files: list[dict], goos: str, goarch: str) -> dict:
    cases = json.loads(output)
    if lane in ("version", "response"):
        payload = {
            "go_source_sha256": sha256((ROOT / LANES[lane]["source"][0]).read_bytes()),
            "oracle_sha256": sha256((ROOT / LANES[lane]["oracle"][0]).read_bytes()),
            "cases": cases,
        }
    elif lane == "install-method":
        payload = cases
        payload["goos"] = goos
    elif lane == "extract":
        payload = {
            "go_source_sha256": sha256((ROOT / LANES[lane]["source"][0]).read_bytes()),
            "oracle_sha256": sha256((ROOT / LANES[lane]["oracle"][0]).read_bytes()),
            "goos": goos,
            "cases": cases,
        }
    elif lane == "swap":
        payload = {
            "go_source_sha256": sha256((ROOT / LANES[lane]["source"][0]).read_bytes()),
            "oracle_sha256": sha256((ROOT / LANES[lane]["oracle"][0]).read_bytes()),
            "goos": goos,
            "cases": cases,
        }
    elif lane == "checker":
        payload = {
            "go_source_sha256": sha256((ROOT / LANES[lane]["source"][0]).read_bytes()),
            "oracle_sha256": sha256((ROOT / LANES[lane]["oracle"][0]).read_bytes()),
            "observations": cases,
        }
    else:
        raise ValueError(f"unknown static update lane: {lane}")
    actual_cases = _at_path(payload, LANES[lane]["case_path"])
    if not isinstance(actual_cases, list) or len(actual_cases) != LANES[lane]["count"]:
        raise ValueError(f"Go {lane} oracle produced {len(actual_cases) if isinstance(actual_cases, list) else 'non-list'} cases; expected {LANES[lane]['count']}")
    if lane == "extract":
        by_path = {item["path"]: item["sha256"] for item in generated_files}
        for case in actual_cases:
            archive_path = case["archive"]
            observed_hash = case.get("archive_sha256")
            source_path = ROOT / archive_path
            if not source_path.is_file() or sha256(source_path.read_bytes()) != observed_hash or by_path.get(archive_path) != observed_hash:
                raise ValueError(f"Go extraction generator input differs from tracked archive: {archive_path}")
    return payload


def capture_go(lane: str, artifacts_dir: Path | None = None) -> tuple[dict, dict, Path | None]:
    """Execute the pinned Go oracle once and preserve raw stdout/stderr/observations."""
    if lane not in LANES:
        raise ValueError(f"unknown static update lane: {lane}")
    if os.environ.get("GO_ORACLE") != "1":
        raise RuntimeError("live Go capture requires explicit GO_ORACLE=1")
    if artifacts_dir is None:
        raise RuntimeError("live Go capture requires a raw execution evidence directory")
    with tempfile.TemporaryDirectory(prefix=f"static-update-{lane}-") as scratch_name:
        scratch = Path(scratch_name)
        env, version, goroot, goos, goarch, gomodcache, go_tool = _prepare_go_env(scratch, artifacts_dir)
        inputs_before = _capture_inputs(lane, go_tool, env, artifacts_dir)
        records: list[dict] = []
        generated_files: list[dict] = []
        observation_bytes: bytes | None = None
        if lane == "extract":
            binary = scratch / ("extract-oracle.exe" if os.name == "nt" else "extract-oracle")
            build = _run([str(go_tool), "build", "-o", str(binary), "./scripts/rust-port/update-extract-oracle"], env, ROOT, "build-go-extract-oracle", artifacts_dir)
            records.append(build)
            if build["exit_code"] != 0:
                raise RuntimeError("Go extraction oracle build failed")
            run_root = scratch / "extract-cwd"
            output_dir = run_root / "scripts/rust-port/update-extract-oracle/testdata"
            output_dir.mkdir(parents=True)
            result = _run([str(binary)], env, run_root, "run-go-extract-oracle", artifacts_dir)
            records.append(result)
            output_dir = run_root / "scripts/rust-port/update-extract-oracle/testdata"
            for generated in sorted(output_dir.iterdir()):
                raw = generated.read_bytes()
                generated_files.append({"path": f"scripts/rust-port/update-extract-oracle/testdata/{generated.name}", "sha256": sha256(raw), "bytes": len(raw)})
            observation_bytes = result["stdout"]
        elif lane == "swap":
            generated = scratch / "swap-observation.json"
            swap_env = dict(env, COREKIT_SWAP_ORACLE_OUT=str(generated))
            result = _run([str(go_tool), "test", "-count=1", "-run", "^TestAtomicSwapOracle$", "./updatecheck/updateapply"], swap_env, ROOT, "run-go-swap-test", artifacts_dir)
            records.append(result)
            if generated.is_file():
                observation_bytes = generated.read_bytes()
        else:
            command = [str(go_tool), *LANES[lane]["command"][1:]]
            result = _run(command, env, ROOT, f"run-go-{lane}-oracle", artifacts_dir)
            records.append(result)
            observation_bytes = result["stdout"]
        successful = all(item["exit_code"] == 0 for item in records) and observation_bytes is not None
        evidence_path = None
        raw = {"exit_code": next((item["exit_code"] for item in records if item["exit_code"] != 0), 0),
               "stdout_sha256": sha256(b"".join(item["stdout"] for item in records)),
               "stderr_sha256": sha256(b"".join(item["stderr"] for item in records)),
               "commands": [{key: value for key, value in item.items() if key not in ("stdout", "stderr")} for item in records]}
        if observation_bytes is not None:
            raw["observation_sha256"] = sha256(observation_bytes)
            raw["observation_bytes"] = len(observation_bytes)
        if artifacts_dir is not None:
            artifacts_dir = artifacts_dir.resolve()
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            evidence_path = Path(tempfile.mkdtemp(prefix=f"{lane}-", dir=artifacts_dir))
            for index, item in enumerate(records):
                (evidence_path / f"{index:02d}-{item['stage']}.stdout").write_bytes(item["stdout"])
                (evidence_path / f"{index:02d}-{item['stage']}.stderr").write_bytes(item["stderr"])
            if observation_bytes is not None:
                (evidence_path / "observation.raw").write_bytes(observation_bytes)
            (evidence_path / "generated-inputs.json").write_text(json.dumps(generated_files, indent=2) + "\n", encoding="utf-8")
            (evidence_path / "run.json").write_text(json.dumps({"lane": lane, "raw": raw, "go_version": version, "goos": goos, "goarch": goarch, "success": successful}, indent=2) + "\n", encoding="utf-8")
            raw["evidence_id"] = evidence_path.name
        if not successful:
            raise RuntimeError(f"Go {lane} oracle failed; raw execution evidence retained at {evidence_path or 'temporary scratch'}")
        if observation_bytes is None:
            raise RuntimeError(f"Go {lane} oracle produced no observation bytes")
        try:
            payload = _build_payload(lane, observation_bytes, generated_files, goos, goarch)
            if _capture_inputs(lane, go_tool, env, artifacts_dir) != inputs_before:
                raise ValueError("Go oracle source/toolchain inputs changed during execution")
        except Exception as error:
            if evidence_path is not None:
                (evidence_path / "run.json").write_bytes(_json_bytes({"lane": lane, "raw": raw, "go_version": version,
                    "goos": goos, "goarch": goarch, "success": False, "validation_error": type(error).__name__,
                    "input_snapshot": inputs_before}))
            raise
        # Exact historical files remain untouched. Record their digest to bind this
        # additive capture to the pre-existing generation without relabeling it.
        frozen = {item["path"]: item["sha256"] for item in inputs_before["source_files"]}
        legacy_digest = frozen[f"repository/testdata/rust-port/fixtures/update/{LANES[lane]['legacy']}"]
        payload["capture"] = {
            "schema_version": 1,
            "lane": lane,
            "source_commit": inputs_before["source_commit"],
            "working_tree_clean": inputs_before["working_tree_clean"],
            "dirty_paths": inputs_before["dirty_paths"],
            "go": {"version": version, "goversion": "go1.26.6", "goroot": Path(goroot).name, "goos": goos, "goarch": goarch,
                   "binary_sha256": inputs_before["go_binary_sha256"], "gomodcache": "existing-cache-read-only"},
            "capturer_sha256": frozen["repository/scripts/rust-port/static_update_oracle.py"],
            "oracle_files": [{"path": path, "sha256": frozen["repository/" + path]} for path in LANES[lane]["oracle"]],
            "source_files": inputs_before["source_files"],
            "go_module_inputs": [{"path": path, "sha256": frozen["repository/" + path]} for path in ("go.mod", "go.sum") if "repository/" + path in frozen],
            "historical_fixture": {"path": f"testdata/rust-port/fixtures/update/{LANES[lane]['legacy']}", "sha256": legacy_digest},
            "case_count": LANES[lane]["count"],
            "case_ids": case_ids(lane, payload),
            "case_fingerprints_sha256": [sha256(canonical_json(case)) for case in _at_path(payload, LANES[lane]["case_path"])],
            "generated_inputs": generated_files,
            "raw": raw,
            "capture_mode": "fresh-pinned-go-execution-additive-v2",
            "input_inventory_verified": True,
            "input_snapshot_sha256": sha256(canonical_json(inputs_before)),
        }
        return payload, payload["capture"], evidence_path


def _json_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def register_capture(candidate: Path, destination: Path, root: Path = ROOT) -> None:
    """Register a new, reviewed candidate without overwriting any prior capture."""
    if os.environ.get("GO_ORACLE") != "1":
        raise RuntimeError("registering a fresh Go capture requires explicit GO_ORACLE=1")
    candidate = candidate.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing capture: {destination}")
    try:
        lane = next(name for name, spec in LANES.items() if spec["fixture"] == destination.name)
    except StopIteration as error:
        raise ValueError("destination filename does not identify an update lane") from error
    data = candidate.read_bytes()
    payload = json.loads(data)
    capture = _validate_payload(lane, payload)
    if capture["capturer_sha256"] != sha256(Path(__file__).read_bytes()):
        raise ValueError("candidate provenance does not match this lane/capturer")
    go = capture.get("go", {})
    static_root = root / "testdata/rust-port/fixtures/update/static-v2"
    index_path = static_root / "index-v2.json"
    key = "/".join((go.get("goos", ""), go.get("goarch", ""), lane))
    expected_parent = static_root / _goos_arch(go.get("goos", ""), go.get("goarch", ""))
    if destination.parent != expected_parent.resolve():
        raise ValueError("capture must be registered only to its exact native GOOS/GOARCH directory")
    if ANCHORS.get(key) != sha256(data):
        raise ValueError("registration requires independently reviewed candidate bytes")
    index = {"schema_version": 2, "captures": {}}
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if type(index.get("schema_version")) is not int or index["schema_version"] != 2:
            raise ValueError("unsupported static update provenance index version")
        for prior_lane, prior in index.get("captures", {}).items():
            prior_path = (root / prior["path"]).resolve()
            if not prior_path.is_relative_to(root.resolve()) or not prior_path.is_file():
                raise ValueError(f"existing {prior_lane} capture path escapes the evidence root")
            digest = sha256(prior_path.read_bytes())
            if digest != prior.get("sha256") or digest != ANCHORS.get(prior_lane):
                raise ValueError(f"existing {prior_lane} capture/index integrity check failed")
    rel = destination.relative_to(root.resolve()).as_posix()
    entry = {"path": rel, "sha256": sha256(data), "capturer_sha256": capture["capturer_sha256"],
             "goos": go["goos"], "goarch": go["goarch"], "case_count": capture["case_count"], "case_ids": capture["case_ids"],
             "source_commit": capture["source_commit"], "working_tree_clean": capture["working_tree_clean"]}
    if key in index["captures"]:
        raise ValueError("refusing to replace a registered native capture")
    index["captures"][key] = entry
    destination.parent.mkdir(parents=True, exist_ok=True)
    # ponytail: one coordinator writes this index. Stage both files and roll back
    # ordinary publication failures; concurrent writers/crash recovery would need
    # an interprocess lock and journal, not a claim of two-file atomicity.
    with tempfile.TemporaryDirectory(prefix=".register-", dir=index_path.parent) as staging:
        capture_tmp = Path(staging) / "capture.json"
        index_tmp = Path(staging) / "index.json"
        capture_tmp.write_bytes(data)
        index_tmp.write_bytes(_json_bytes(index))
        owned = capture_tmp.stat()
        linked = indexed = False
        try:
            # A link publishes complete bytes without replacing a racing file.
            os.link(capture_tmp, destination)
            linked = True
            index_tmp.replace(index_path)
            indexed = True
        finally:
            if linked and not indexed:
                try:
                    current = destination.lstat()
                except FileNotFoundError:
                    pass
                else:
                    if os.path.samestat(owned, current):
                        destination.unlink()


def _capture_cli(args) -> None:
    if os.environ.get("GO_ORACLE") != "1":
        raise RuntimeError("capture requires explicit GO_ORACLE=1")
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite capture candidate: {output}")
    payload, capture, evidence = capture_go(args.lane, args.artifacts_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_json_bytes(payload))
    print(json.dumps({"lane": args.lane, "candidate": str(output), "case_count": capture["case_count"], "go": capture["go"], "evidence_dir": str(evidence) if evidence else None}, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    capture = sub.add_parser("capture", help="fresh Go capture; requires GO_ORACLE=1")
    capture.add_argument("--lane", choices=tuple(LANES), required=True)
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--artifacts-dir", type=Path, required=True)
    register = sub.add_parser("register", help="register a new additive candidate; requires GO_ORACLE=1")
    register.add_argument("--candidate", type=Path, required=True)
    register.add_argument("--destination", type=Path, required=True)
    check = sub.add_parser("check", help="validate a frozen native capture without running Go")
    check.add_argument("--lane", choices=tuple(LANES), required=True)
    check.add_argument("--fixture", type=Path)
    check.add_argument("--diagnostic", action="store_true", help="inspect retained dirty evidence; never grants acceptance")
    args = parser.parse_args(argv)
    if args.action == "capture":
        _capture_cli(args)
    elif args.action == "register":
        register_capture(args.candidate, args.destination)
        print(f"PASS registered additive capture: {args.destination}")
    else:
        path = args.fixture or fixture_path(args.lane, historical=args.diagnostic)
        payload = validate_capture(args.lane, path, diagnostic=args.diagnostic)
        classification = "DIAGNOSTIC ONLY" if args.diagnostic else "PASS"
        print(f"{classification} frozen Go {args.lane} capture: {len(_at_path(payload, LANES[args.lane]['case_path']))} cases ({payload['capture']['go']['goos']}/{payload['capture']['go']['goarch']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
