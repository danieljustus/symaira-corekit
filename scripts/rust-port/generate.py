#!/usr/bin/env python3
"""Generate deterministic Go-oracle fixtures for the Rust port."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Any

REPO = Path(__file__).resolve().parents[2]
PORT = REPO / "scripts" / "rust-port"
HELPER = PORT / "go-oracle"
FIXTURES = REPO / "testdata" / "rust-port" / "fixtures"
ORACLE_COMMIT = "f3d3eb79b9b1f31b4f973d2ed518a8292cedf588"
ORACLE_RELEASE = "v0.17.0"
ORACLE_DIGEST = "ab38c1cc4d2f91026e1d6836e1138388fd683a789ab8f104269d019c3caff95c"
CONTRACTS = (
    "config_paths.json",
    "exit_codes.json",
    "json_encoding.json",
    "llm_errors.json",
    "llm_providers.json",
    "mcp_tool_annotations.json",
    "mcp_tool_errors.json",
    "secret_refs.json",
    "update_check_invariants.json",
)
HARNESS_INPUTS = (
    "docs/rust-port/validate.py",
    "scripts/rust-port/diff.py",
    "scripts/rust-port/generate.py",
    "scripts/rust-port/go-oracle/go.mod",
    "scripts/rust-port/go-oracle/go.sum",
    "scripts/rust-port/go-oracle/cmd/probe/main.go",
    "scripts/rust-port/go-oracle/cmd/publicapi/main.go",
    "testdata/rust-port/README.md",
    "testdata/rust-port/cases/consumer-canaries.json",
    "testdata/rust-port/cases/oracle-selftest.json",
)


def run(*args: str, cwd: Path = REPO, env: dict[str, str] | None = None, stdin: bytes | None = None) -> bytes:
    completed = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"{' '.join(args)} failed ({completed.returncode}): {message}")
    return completed.stdout


def owned(path: str) -> bool:
    return (
        (path.endswith(".go") and not path.endswith("_test.go"))
        or (path.startswith("contracts/") and path.endswith(".json"))
        or ("/testdata/" in path and path.endswith((".json", ".sql")))
    )


def source_digest(commit: str = ORACLE_COMMIT, *, mutate_first: bool = False) -> tuple[str, int]:
    paths = sorted(
        path
        for path in run("git", "ls-tree", "-r", "--name-only", commit).decode().splitlines()
        if owned(path)
    )
    digest = hashlib.sha256()
    for index, path in enumerate(paths):
        content = run("git", "show", f"{commit}:{path}")
        if mutate_first and index == 0:
            content += b"deliberate-negative-control"
        digest.update(path.encode() + b"\0" + content + b"\0")
    return digest.hexdigest(), len(paths)


def require_source_digest(actual: str) -> None:
    if actual != ORACLE_DIGEST:
        raise RuntimeError(f"oracle source digest mismatch: expected {ORACLE_DIGEST}, got {actual}")


def assert_source() -> int:
    actual, count = source_digest()
    require_source_digest(actual)
    mutated, _ = source_digest(mutate_first=True)
    try:
        require_source_digest(mutated)
    except RuntimeError:
        pass
    else:
        raise RuntimeError("source-digest negative control accepted a mutated oracle input")
    return count


def path_digest(paths: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        content = (REPO / relative).read_bytes()
        digest.update(relative.encode() + b"\0" + content + b"\0")
    return digest.hexdigest()


def extract_oracle(target: Path) -> None:
    process = subprocess.Popen(
        ["git", "archive", "--format=tar", ORACLE_COMMIT],
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                destination = (target / member.name).resolve()
                if target.resolve() not in destination.parents and destination != target.resolve():
                    raise RuntimeError(f"oracle archive path escapes target: {member.name}")
                archive.extract(member, target, filter="data")
    finally:
        process.stdout.close()
    stderr = process.stderr.read() if process.stderr else b""
    if process.wait() != 0:
        raise RuntimeError(f"git archive failed: {stderr.decode('utf-8', 'replace')}")


def oracle_modfile(path: Path, oracle: Path) -> Path:
    source = (HELPER / "go.mod").read_text()
    marker = "replace github.com/danieljustus/symaira-corekit => ../../.."
    if source.count(marker) != 1:
        raise RuntimeError("go-oracle go.mod replacement marker drifted")
    content = source.replace(marker, f"replace github.com/danieljustus/symaira-corekit => {oracle.as_posix()}")
    path.write_text(content)
    return path


def build_helper(command: str, output: Path, oracle: Path) -> None:
    modfile = oracle_modfile(output.with_suffix(".mod"), oracle)
    shutil.copy2(HELPER / "go.sum", output.with_suffix(".sum"))
    env = os.environ.copy()
    env.update({"CGO_ENABLED": "0", "GOTOOLCHAIN": "go1.26.6"})
    run(
        "go", "build", "-trimpath", "-modfile", str(modfile), "-o", str(output),
        f"./cmd/{command}", cwd=HELPER, env=env,
    )


def generate_tree(target: Path) -> dict[str, Any]:
    source_count = assert_source()
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="corekit-oracle-") as temp_raw:
        temp = Path(temp_raw)
        oracle = temp / "oracle"
        oracle.mkdir()
        extract_oracle(oracle)

        publicapi = temp / ("publicapi.exe" if os.name == "nt" else "publicapi")
        build_helper("publicapi", publicapi, oracle)
        api_env = os.environ.copy()
        api_env.update({"CGO_ENABLED": "0", "GOTOOLCHAIN": "go1.26.6"})
        apis: dict[str, dict[str, Any]] = {}
        for goos in ("darwin", "linux", "windows"):
            for goarch in ("amd64", "arm64"):
                target_name = f"{goos}-{goarch}"
                api_raw = run(
                    str(publicapi), "--repo", str(oracle),
                    "--goos", goos, "--goarch", goarch, cwd=oracle, env=api_env,
                )
                apis[target_name] = json.loads(api_raw)

        package_digests = {
            target_name: hashlib.sha256(
                json.dumps(api["packages"], separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            for target_name, api in apis.items()
        }
        canonical_api = dict(apis["darwin-arm64"])
        canonical_api.pop("goos", None)
        canonical_api.pop("goarch", None)
        canonical_api["targets"] = sorted(apis)
        (target / "public-api.json").write_text(
            json.dumps(canonical_api, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        canonical_packages = {package["path"]: package for package in canonical_api["packages"]}
        overrides: dict[str, dict[str, Any]] = {}
        for target_name, api in apis.items():
            target_packages = {package["path"]: package for package in api["packages"]}
            changed = [
                target_packages[path]
                for path in sorted(target_packages)
                if canonical_packages.get(path) != target_packages[path]
            ]
            removed = sorted(set(canonical_packages) - set(target_packages))
            overrides[target_name] = {"changed_packages": changed, "removed_packages": removed}
        (target / "public-api-target-overrides.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "oracle_commit": ORACLE_COMMIT,
                    "canonical_target": "darwin-arm64",
                    "targets": overrides,
                },
                indent=2,
                ensure_ascii=False,
            ) + "\n",
            encoding="utf-8",
        )

        provenance_control = oracle / "versionkit" / "versionkit.go"
        original_source = provenance_control.read_bytes()
        try:
            provenance_control.write_bytes(original_source + b"\n// deliberate provenance mismatch\n")
            rejected = subprocess.run(
                [str(publicapi), "--repo", str(oracle), "--goos", "darwin", "--goarch", "arm64"],
                cwd=oracle,
                env=api_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if rejected.returncode == 0:
                raise RuntimeError("public API oracle accepted mutated source provenance")
        finally:
            provenance_control.write_bytes(original_source)

        probe = temp / ("probe.exe" if os.name == "nt" else "probe")
        build_helper("probe", probe, oracle)
        probe_home = temp / "probe-home"
        probe_home.mkdir()
        probe_output = probe_home / "probe-output.json"
        probe_env = {
            "HOME": str(probe_home), "USERPROFILE": str(probe_home),
            "XDG_CONFIG_HOME": str(probe_home / ".config"),
            "XDG_DATA_HOME": str(probe_home / ".local" / "share"),
            "XDG_CACHE_HOME": str(probe_home / ".cache"),
            "TMPDIR": str(probe_home / "tmp"), "TMP": str(probe_home / "tmp"), "TEMP": str(probe_home / "tmp"),
            "LANG": "C", "LC_ALL": "C", "TZ": "UTC", "PORT_PRIMARY": "fixture-value",
        }
        probe_env["PATH"] = os.environ.get("PATH", "")
        for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"):
            if key in os.environ:
                probe_env[key] = os.environ[key]
        (probe_home / "tmp").mkdir()
        request = {
            "tool": "symfixture", "version": "v1.2.3", "schema_version": 7,
            "env_name": "PORT_PRIMARY", "env_aliases": ["PORT_LEGACY"],
            "output_path": str(probe_output),
        }
        probe_raw = run(str(probe), cwd=oracle, env=probe_env, stdin=json.dumps(request).encode())
        probe_value = json.loads(probe_raw)
        probe_value["written_file"] = probe_output.read_text()
        (target / "oracle-probe.json").write_text(json.dumps(probe_value, indent=2, ensure_ascii=False) + "\n")

    contract_dir = target / "contracts"
    contract_dir.mkdir()
    contract_records = []
    for name in CONTRACTS:
        source = REPO / "contracts" / name
        content = source.read_bytes()
        (contract_dir / name).write_bytes(content)
        contract_records.append({"path": f"contracts/{name}", "sha256": hashlib.sha256(content).hexdigest()})

    api_targets = {}
    for target_name, api in apis.items():
        declaration_count = sum(len(package["declarations"]) for package in api["packages"])
        member_count = sum(
            len(declaration.get("methods", [])) + len(declaration.get("fields", []))
            for package in api["packages"]
            for declaration in package["declarations"]
        )
        api_targets[target_name] = {
            "packages": len(api["packages"]),
            "exported_top_level_declarations": declaration_count,
            "exported_members": member_count,
            "exported_surface_entries": declaration_count + member_count,
            "api_digest_sha256": package_digests[target_name],
        }
    index = {
        "schema_version": 1,
        "oracle": {"commit": ORACLE_COMMIT, "release": ORACLE_RELEASE, "source_digest_sha256": ORACLE_DIGEST, "source_files": source_count},
        "harness": {"input_digest_sha256": path_digest(HARNESS_INPUTS), "input_files": sorted(HARNESS_INPUTS)},
        "public_api": {"targets": api_targets},
        "contracts": contract_records,
        "known_contract_corrections": ["DEFECT-001"],
    }
    (target / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    return index


def compare_trees(expected: Path, actual: Path) -> None:
    expected_files = sorted(p.relative_to(expected) for p in expected.rglob("*") if p.is_file())
    actual_files = sorted(p.relative_to(actual) for p in actual.rglob("*") if p.is_file()) if actual.exists() else []
    if expected_files != actual_files:
        raise RuntimeError(f"fixture file set drift: generated={expected_files}, committed={actual_files}")
    for rel in expected_files:
        left, right = (expected / rel).read_bytes(), (actual / rel).read_bytes()
        if left != right:
            raise RuntimeError(f"fixture drift: {rel}; run python3 scripts/rust-port/generate.py")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="compare generated fixtures with committed files")
    parser.add_argument("--check-source", action="store_true", help="only verify pinned oracle provenance")
    args = parser.parse_args()
    try:
        if args.check_source:
            count = assert_source()
            print(f"PASS oracle source ({count} files, {ORACLE_DIGEST})")
            return 0
        if args.check:
            with tempfile.TemporaryDirectory(prefix="corekit-fixtures-") as raw:
                generated = Path(raw) / "fixtures"
                index = generate_tree(generated)
                compare_trees(generated, FIXTURES)
            target = index["public_api"]["targets"]
            print(f"PASS fixtures (6 OS/architecture targets, {target['darwin-arm64']['packages']} packages, {target['darwin-arm64']['exported_surface_entries']} Darwin/arm64 API entries)")
            return 0
        with tempfile.TemporaryDirectory(prefix="corekit-fixtures-") as raw:
            generated = Path(raw) / "fixtures"
            index = generate_tree(generated)
            if FIXTURES.exists():
                shutil.rmtree(FIXTURES)
            shutil.copytree(generated, FIXTURES)
        target = index["public_api"]["targets"]
        print(f"WROTE {FIXTURES} (6 OS/architecture targets, {target['darwin-arm64']['packages']} packages, {target['darwin-arm64']['exported_surface_entries']} Darwin/arm64 API entries)")
        return 0
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
