#!/usr/bin/env python3
"""Validate RUST-005 consumer adoption evidence without optimistic claims.

The validator deliberately separates facts that can be checked in a local
consumer checkout from live pull-request state. An open PR is useful evidence
of work in progress, but it is never treated as a merged adoption.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
from typing import Any, cast

from trust import assert_clean_checkout, assert_origin, checkout_for_record, github_json, safe_checkout_child, safe_workspace_path

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parents[2]
DEFAULT_EVIDENCE = ROOT / "testdata/rust-port/adoption/evidence.json"
DEFAULT_REPORT = ROOT / "testdata/rust-port/adoption/report.json"
REV_RE = re.compile(r"^[0-9a-f]{40}$")
COREKIT_URL = "https://github.com/danieljustus/symaira-corekit"
COREKIT_PACKAGE = "symaira-core-version"
FORBIDDEN_CLOSURE = {
    "tokio", "reqwest", "hyper", "axum", "actix-web", "rocket", "rusqlite",
    "libsqlite3-sys", "sqlx", "ureq", "isahc", "serde_yaml", "openssl",
}


@dataclass
class Finding:
    consumer: str
    message: str
    blocking: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {"consumer": self.consumer, "message": self.message, "blocking": self.blocking}


def fail(message: str) -> None:
    raise ValueError(message)


def git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def git_bytes(*args: str, cwd: Path) -> bytes:
    completed = subprocess.run(["git", *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {completed.stderr.decode('utf-8', 'replace').strip()}")
    return completed.stdout


def load(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        fail(f"{path}: top-level JSON value must be an object")
    return document


def assert_revision(value: Any, label: str) -> str:
    if not isinstance(value, str) or not REV_RE.fullmatch(value):
        fail(f"{label}: expected a 40-character lowercase git revision")
    return value


def repository_root(path: Path) -> Path:
    return Path(git("rev-parse", "--show-toplevel", cwd=path)).resolve()


def cargo_manifests(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("Cargo.toml") if ".git" not in path.parts and "target" not in path.parts)


def dependency_specs(manifest: Path) -> list[tuple[str, dict[str, Any] | str]]:
    document = tomllib.loads(manifest.read_text(encoding="utf-8"))
    result: list[tuple[str, dict[str, Any] | str]] = []

    def collect(table: Any) -> None:
        if not isinstance(table, dict):
            return
        for name, spec in table.items():
            if isinstance(spec, (dict, str)):
                result.append((name, spec))

    collect(document.get("dependencies"))
    collect(document.get("workspace", {}).get("dependencies"))
    targets = document.get("target", {})
    if isinstance(targets, dict):
        for target in targets.values():
            if isinstance(target, dict):
                collect(target.get("dependencies"))
    return result


def lock_package(lock: dict[str, Any], name: str, source: str | None = None) -> dict[str, Any] | None:
    packages = [package for package in lock.get("package", []) if package.get("name") == name]
    if source is not None:
        packages = [package for package in packages if package.get("source") == source]
    if len(packages) != 1:
        return None
    return packages[0]


def lock_closure(lock: dict[str, Any], root: dict[str, Any]) -> set[str]:
    packages = lock.get("package", [])
    by_name: dict[str, list[dict[str, Any]]] = {}
    for package in packages:
        by_name.setdefault(package.get("name", ""), []).append(package)
    seen: set[tuple[str, str | None]] = set()
    names: set[str] = set()
    stack = [root]
    while stack:
        package = stack.pop()
        identity = (package.get("name", ""), package.get("source"))
        if identity in seen:
            continue
        seen.add(identity)
        names.add(package.get("name", ""))
        for dependency in package.get("dependencies", []):
            dependency_name = str(dependency).split(" ", 1)[0]
            candidates = by_name.get(dependency_name, [])
            if len(candidates) == 1:
                stack.append(candidates[0])
            elif candidates:
                # A lockfile can contain multiple versions. The package's
                # version/source suffix identifies the exact dependency.
                match = next((candidate for candidate in candidates if str(candidate.get("version")) in str(dependency)), None)
                if match is not None:
                    stack.append(match)
    return names


def noncomment_loc(lines: list[str]) -> int:
    return sum(1 for line in lines if line.strip() and not line.lstrip().startswith("//") and not line.lstrip().startswith("#"))


def diff_loc(root: Path, before: str, after: str, paths: list[str]) -> tuple[int, int]:
    output = git("diff", "--unified=0", before, after, "--", *paths, cwd=root)
    removed: list[str] = []
    added: list[str] = []
    for line in output.splitlines():
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            continue
        if line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith("+"):
            added.append(line[1:])
    return noncomment_loc(removed), noncomment_loc(added)


def validate_consumer_files(record: dict[str, Any], root: Path, expected_rev: str) -> tuple[dict[str, Any], list[Finding]]:
    """Check a consumer checkout; intentionally pure for negative-control tests."""
    name = str(record.get("repository", "unknown"))
    findings: list[Finding] = []
    manifests = cargo_manifests(root)
    declared_manifests = record.get("manifest_paths", [])
    if not isinstance(declared_manifests, list) or not declared_manifests:
        findings.append(Finding(name, "manifest_paths must be a non-empty array"))
    else:
        for relative in declared_manifests:
            try:
                manifest_path = safe_checkout_child(root, relative, f"{name}.manifest_paths")
                if not manifest_path.is_file() or manifest_path.name != "Cargo.toml":
                    findings.append(Finding(name, f"manifest path is not a Cargo.toml beneath checkout: {relative}"))
            except (TypeError, ValueError) as error:
                findings.append(Finding(name, str(error)))
    if not manifests:
        findings.append(Finding(name, "no Cargo.toml found"))
        return {"manifests": [], "lock": None}, findings

    workspace_document: dict[str, Any] = {}
    workspace_manifest = root / "Cargo.toml"
    if workspace_manifest.is_file():
        try:
            parsed_root = tomllib.loads(workspace_manifest.read_text(encoding="utf-8"))
            workspace_document = parsed_root.get("workspace", {})
        except (OSError, tomllib.TOMLDecodeError):
            pass
    workspace_specs = workspace_document.get("dependencies", {}) if isinstance(workspace_document, dict) else {}
    pins: list[dict[str, Any]] = []
    for manifest in manifests:
        try:
            specs = dependency_specs(manifest)
        except (OSError, tomllib.TOMLDecodeError) as error:
            findings.append(Finding(name, f"invalid {manifest.relative_to(root)}: {error}"))
            continue
        for dependency, spec in specs:
            effective = spec
            if isinstance(spec, dict) and spec.get("workspace") is True:
                workspace_spec = workspace_specs.get(dependency) if isinstance(workspace_specs, dict) else None
                if isinstance(workspace_spec, (dict, str)):
                    effective = workspace_spec
            if dependency == COREKIT_PACKAGE:
                pins.append({"manifest": manifest.relative_to(root).as_posix(), "spec": effective})
            if isinstance(effective, dict) and "path" in effective:
                path_value = str(effective["path"])
                resolved = (manifest.parent / path_value).resolve()
                if "symaira-corekit" in path_value.lower() or resolved == ROOT.resolve() or resolved.name == "symaira-corekit":
                    findings.append(Finding(name, f"sibling CoreKit path dependency in {manifest.relative_to(root)}: {path_value}"))

    if not pins:
        findings.append(Finding(name, f"{COREKIT_PACKAGE} dependency is absent"))
    for pin in pins:
        spec = pin["spec"]
        if not isinstance(spec, dict):
            findings.append(Finding(name, f"{pin['manifest']}: CoreKit dependency is not an explicit table"))
            continue
        if spec.get("git") != COREKIT_URL:
            findings.append(Finding(name, f"{pin['manifest']}: CoreKit git URL is not {COREKIT_URL}"))
        if spec.get("rev") != expected_rev:
            findings.append(Finding(name, f"{pin['manifest']}: CoreKit rev {spec.get('rev')!r} != {expected_rev}"))
        if "path" in spec:
            findings.append(Finding(name, f"{pin['manifest']}: CoreKit dependency has a path override"))
        if spec.get("features"):
            findings.append(Finding(name, f"{pin['manifest']}: CoreKit dependency enables consumer features {spec['features']!r}"))
        if spec.get("default-features") is True:
            findings.append(Finding(name, f"{pin['manifest']}: CoreKit default features were enabled implicitly; closure must be explicit"))

    lock_paths = [root / "Cargo.lock"]
    if not lock_paths[0].is_file():
        findings.append(Finding(name, "Cargo.lock is missing; resolved source/revision cannot be proven"))
        return {"manifests": [p.relative_to(root).as_posix() for p in manifests], "lock": None, "pins": pins}, findings
    try:
        lock = tomllib.loads(lock_paths[0].read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        findings.append(Finding(name, f"Cargo.lock is invalid: {error}"))
        return {"manifests": [p.relative_to(root).as_posix() for p in manifests], "lock": None, "pins": pins}, findings
    source = f"git+{COREKIT_URL}?rev={expected_rev}#{expected_rev}"
    all_corekit = [package for package in lock.get("package", []) if package.get("name") == COREKIT_PACKAGE]
    package = lock_package(lock, COREKIT_PACKAGE, source)
    if len(all_corekit) != 1:
        findings.append(Finding(name, f"Cargo.lock must contain exactly one {COREKIT_PACKAGE} package, found {len(all_corekit)}"))
    if package is None:
        findings.append(Finding(name, f"Cargo.lock has no unique {COREKIT_PACKAGE} package resolved from {source}"))
    closure: set[str] = set()
    if package is not None:
        closure = lock_closure(lock, package)
        forbidden = sorted(closure & FORBIDDEN_CLOSURE)
        if forbidden:
            findings.append(Finding(name, f"CoreKit dependency feature closure pulls forbidden product packages: {forbidden}"))
    return {
        "manifests": [p.relative_to(root).as_posix() for p in manifests],
        "pins": pins,
        "lock": {"source": source, "closure": sorted(closure)},
    }, findings


def validate_duplicate(record: dict[str, Any], root: Path) -> tuple[dict[str, Any], list[Finding]]:
    name = str(record["repository"])
    duplicate = record.get("duplicate", {})
    findings: list[Finding] = []
    fields = ("corekit_loc_added", "adapter_loc_added", "duplicate_loc_removed")
    if any(not isinstance(duplicate.get(field), int) or duplicate[field] < 0 for field in fields):
        findings.append(Finding(name, "duplicate evidence needs non-negative integer LOC measurements"))
    else:
        if duplicate["duplicate_loc_removed"] < duplicate["corekit_loc_added"] + duplicate["adapter_loc_added"]:
            findings.append(Finding(name, "duplicate-removal rule failed: removed LOC is below shared plus adapter LOC"))
    before = record.get("pre_adoption_commit")
    after = record.get("adoption_commit")
    paths = duplicate.get("source_paths", [])
    trusted_paths: list[str] = []
    if not isinstance(paths, list):
        findings.append(Finding(name, "duplicate source_paths must be an array"))
        paths = []
    for path in paths:
        if not isinstance(path, str):
            findings.append(Finding(name, "duplicate source path must be a string"))
            continue
        try:
            safe_checkout_child(root, path, f"{name}.duplicate.source_paths")
            trusted_paths.append(path)
        except ValueError as error:
            findings.append(Finding(name, str(error)))
    if isinstance(before, str) and isinstance(after, str) and trusted_paths:
        try:
            measured_removed, measured_added = diff_loc(root, before, after, trusted_paths)
            if isinstance(duplicate.get("measured_removed_loc"), int) and measured_removed != duplicate["measured_removed_loc"]:
                findings.append(Finding(name, f"measured removed LOC {measured_removed} != evidence {duplicate['measured_removed_loc']}"))
            if isinstance(duplicate.get("measured_added_loc"), int) and measured_added != duplicate["measured_added_loc"]:
                findings.append(Finding(name, f"measured added LOC {measured_added} != evidence {duplicate['measured_added_loc']}"))
        except RuntimeError as error:
            findings.append(Finding(name, f"cannot measure duplicate diff: {error}"))
    for marker in duplicate.get("before_markers", []):
        if not any(marker.encode() in git_bytes("show", f"{before}:{path}", cwd=root) for path in trusted_paths):
            findings.append(Finding(name, f"pre-adoption duplicate marker is absent: {marker}"))
    for marker in duplicate.get("after_forbidden_markers", []):
        if any(marker.encode() in safe_checkout_child(root, path, f"{name}.duplicate.source_paths").read_bytes() for path in trusted_paths):
            findings.append(Finding(name, f"duplicate marker remains after adoption: {marker}"))
    return duplicate, findings


def live_pr(record: dict[str, Any], offline: bool) -> dict[str, Any]:
    if offline:
        state = record.get("offline_pr_state")
        if not isinstance(state, dict):
            return {"state": "unknown", "error": "offline mode has no offline_pr_state"}
        return state
    repository = record.get("repository")
    number = record.get("pr_number")
    if not isinstance(repository, str) or not isinstance(number, int) or number <= 0:
        return {"state": "unknown", "error": "invalid repository or PR number"}
    try:
        payload = github_json(f"/repos/{repository}/pulls/{number}")
    except (RuntimeError, ValueError) as error:
        return {"state": "unknown", "error": str(error)}
    head = payload.get("head") if isinstance(payload.get("head"), dict) else {}
    base = payload.get("base") if isinstance(payload.get("base"), dict) else {}
    return {
        "number": payload.get("number"),
        "state": "MERGED" if payload.get("merged_at") else str(payload.get("state", "UNKNOWN")).upper(),
        "isDraft": payload.get("draft"),
        "mergedAt": payload.get("merged_at"),
        "mergeCommit": {"oid": payload.get("merge_commit_sha")} if payload.get("merge_commit_sha") else None,
        "headRefOid": head.get("sha"),
        "baseRefOid": base.get("sha"),
    }


def validate_smokes(records: list[dict[str, Any]], report: dict[str, Any] | None) -> list[Finding]:
    findings: list[Finding] = []
    entries = (report or {}).get("standalone_smokes", [])
    if not isinstance(entries, list):
        return [Finding("all", "standalone_smokes must be an array")]
    smokes: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("repository"), str):
            findings.append(Finding("unknown", "smoke entry must identify a repository"))
            continue
        repository = entry["repository"]
        if repository in smokes:
            findings.append(Finding(repository, "duplicate consumer smoke evidence"))
        smokes[repository] = entry
    expected = {record["repository"] for record in records}
    if set(smokes) != expected:
        findings.append(Finding("all", "smoke evidence consumer set is not exactly the adoption consumer set"))
    for record in records:
        name = record["repository"]
        smoke = smokes.get(name)
        if not smoke or smoke.get("candidate_commit") != record.get("adoption_commit") or smoke.get("passed") is not True:
            findings.append(Finding(name, "no passing smoke recorded for the exact adoption artifact"))
            continue
        commands = smoke.get("commands")
        results = smoke.get("results")
        if not isinstance(commands, list) or len(commands) != 2 or not isinstance(results, list) or len(results) != 2:
            findings.append(Finding(name, "smoke needs separate text and JSON command/result evidence"))
            continue
        seen: set[tuple[str, ...]] = set()
        text_output: str | None = None
        json_payload: dict[str, Any] | None = None
        for command, result in zip(commands, results, strict=True):
            argv = command.get("argv") if isinstance(command, dict) else None
            if not isinstance(argv, list) or not argv or not isinstance(argv[0], str) or not Path(argv[0]).is_absolute():
                findings.append(Finding(name, "smoke command must use an absolute artifact path"))
                continue
            key = tuple(argv)
            if key in seen:
                findings.append(Finding(name, "duplicate smoke command"))
            seen.add(key)
            if argv[1:] not in (["version"], ["version", "--json"]):
                findings.append(Finding(name, "smoke command must cover version and version --json"))
            if not isinstance(result, dict) or result.get("exit_code") != 0 or result.get("stderr") not in ("", None):
                findings.append(Finding(name, "smoke result lacks successful clean stderr/exit evidence"))
                continue
            encoded = result.get("stdout_base64")
            digest = result.get("stdout_sha256")
            if not isinstance(encoded, str) or not isinstance(digest, str):
                findings.append(Finding(name, "smoke result lacks raw stdout and SHA-256 evidence"))
                continue
            try:
                import base64
                output = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError):
                findings.append(Finding(name, "smoke stdout_base64 is invalid"))
                continue
            if hashlib.sha256(output).hexdigest() != digest:
                findings.append(Finding(name, "smoke stdout digest does not match raw output"))
            if argv[-1] == "--json":
                try:
                    payload = json.loads(output)
                except json.JSONDecodeError:
                    findings.append(Finding(name, "smoke JSON stdout is invalid"))
                    continue
                if not isinstance(payload, dict) or any(key not in payload for key in ("tool", "version", "schema_version")):
                    findings.append(Finding(name, "smoke JSON lacks required semantic version fields"))
                else:
                    json_payload = payload
            else:
                text_output = output.decode("utf-8", "replace")
                if not text_output.strip():
                    findings.append(Finding(name, "smoke text stdout is empty"))
        if json_payload is None or text_output is None or text_output.strip() != f"{json_payload['tool']} {json_payload['version']}":
            findings.append(Finding(name, "smoke text/JSON semantic outputs disagree"))
    return findings


def make_report(evidence: dict[str, Any], records: list[dict[str, Any]], facts: list[dict[str, Any]], findings: list[Finding], live: list[dict[str, Any]]) -> dict[str, Any]:
    pending = any(f.blocking for f in findings)
    return {
        "schema_version": 1,
        "gate_id": "RUST-005",
        "status": "pending" if pending else "passed",
        "claims": {"merged": False if pending else all(item.get("state") == "MERGED" for item in live)},
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "corekit": evidence.get("corekit"),
        "minimum_consumers": evidence.get("minimum_consumers"),
        "consumers": facts,
        "live_pr": live,
        "findings": [finding.as_dict() for finding in findings],
        "honesty": "Open or unverified PRs remain pending; no merged adoption is claimed.",
    }


def validate_minimum(records: list[dict[str, Any]], minimum: int) -> None:
    independent = {record.get("repository") for record in records}
    if len(independent) < minimum:
        fail(f"only {len(independent)} independent consumer records; minimum is {minimum}")
    if len(records) < minimum:
        fail(f"only {len(records)} consumer records; minimum is {minimum}")


def report_label(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def check(evidence_path: Path, report_path: Path, minimum: int, offline: bool) -> int:
    evidence = load(evidence_path)
    if evidence.get("schema_version") != 1 or evidence.get("gate_id") != "RUST-005":
        fail("adoption evidence has an unsupported schema or gate id")
    expected_rev = assert_revision(evidence.get("corekit", {}).get("revision"), "corekit.revision")
    if evidence.get("corekit", {}).get("url") != COREKIT_URL or evidence.get("corekit", {}).get("package") != COREKIT_PACKAGE:
        fail("adoption evidence CoreKit URL/package is not canonical")
    raw_records = evidence.get("consumers")
    if not isinstance(raw_records, list) or any(not isinstance(record, dict) for record in raw_records):
        fail("adoption evidence consumers must be an array of objects")
    records: list[dict[str, Any]] = cast(list[dict[str, Any]], raw_records)
    validate_minimum(records, minimum)

    facts: list[dict[str, Any]] = []
    findings: list[Finding] = []
    live_records: list[dict[str, Any]] = []
    benchmark_report = None
    benchmark_path = ROOT / "testdata/rust-port/benchmarks/foundation.json"
    if not benchmark_path.is_file():
        smoke_path = ROOT / "testdata/rust-port/benchmarks/foundation-smoke.json"
        if smoke_path.is_file():
            benchmark_path = smoke_path
    if benchmark_path.is_file():
        benchmark_report = load(benchmark_path)

    fetch_holder = tempfile.TemporaryDirectory(prefix="rust005-adoption-fetch-")
    fetch_root = Path(fetch_holder.name)
    for record in records:
        if not isinstance(record, dict):
            findings.append(Finding("unknown", "consumer record is not an object"))
            continue
        name = record.get("repository")
        if not isinstance(name, str) or "/" not in name:
            findings.append(Finding(str(name), "repository must be owner/name"))
            continue
        try:
            adoption_commit = assert_revision(record.get("adoption_commit"), f"{name}.adoption_commit")
            pre_commit = assert_revision(record.get("pre_adoption_commit"), f"{name}.pre_adoption_commit")
            assert_revision(record.get("merged_commit"), f"{name}.merged_commit")
            root, _disposable = checkout_for_record(record, [pre_commit, adoption_commit], fetch_root)
            actual_root = repository_root(root)
            if actual_root != root.resolve():
                findings.append(Finding(name, f"checkout root mismatch: {actual_root} != {root.resolve()}"))
            assert_origin(root, name)
            head = git("rev-parse", "HEAD", cwd=root)
            if head != adoption_commit:
                findings.append(Finding(name, f"checkout HEAD {head} != adoption commit {adoption_commit}"))
            ancestor = subprocess.run(
                ["git", "merge-base", "--is-ancestor", pre_commit, adoption_commit],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if ancestor.returncode:
                findings.append(Finding(name, "pre-adoption commit is not an ancestor of adoption commit"))
        except (OSError, RuntimeError, ValueError) as error:
            findings.append(Finding(name, f"checkout/revision validation failed: {error}"))
            facts.append({"repository": name, "status": "unverified"})
            continue
        file_facts, file_findings = validate_consumer_files(record, root, expected_rev)
        findings.extend(file_findings)
        commands = record.get("standalone_commands", [])
        if not isinstance(commands, list) or not commands or any(not isinstance(command, str) or "<artifact>" not in command for command in commands):
            findings.append(Finding(name, "standalone commands must be explicit artifact-path commands"))
        duplicate, duplicate_findings = validate_duplicate(record, root)
        findings.extend(duplicate_findings)
        pr = live_pr(record, offline)
        if pr.get("number") is not None and pr.get("number") != record.get("pr_number"):
            findings.append(Finding(name, "live PR number does not match evidence"))
        state = str(pr.get("state", "UNKNOWN")).upper()
        if state == "OPEN":
            findings.append(Finding(name, f"PR #{record['pr_number']} is OPEN; adoption is pending and not merged"))
        elif state == "MERGED":
            live_merge = (pr.get("mergeCommit") or {}).get("oid") if isinstance(pr.get("mergeCommit"), dict) else pr.get("mergeCommit")
            if not live_merge or record.get("merged_commit") != live_merge:
                findings.append(Finding(name, "PR is merged live but evidence.merged_commit is not filled with the live merge commit"))
        else:
            findings.append(Finding(name, f"PR #{record['pr_number']} live state is {state or 'UNKNOWN'}: merged evidence is unavailable"))
        if pr.get("headRefOid") and pr["headRefOid"] != record["adoption_commit"]:
            findings.append(Finding(name, "live PR head does not match the adoption commit"))
        if pr.get("baseRefOid") and pr["baseRefOid"] != record["pre_adoption_commit"]:
            findings.append(Finding(name, "live PR base does not match the pre-adoption parent"))
        live_records.append({"repository": name, "pr_number": record["pr_number"], **pr, "classification": "pending" if state != "MERGED" or record.get("merged_commit") is None else "merged"})
        facts.append({
            "repository": name,
            "checkout": record["checkout"],
            "commit": head,
            "crate": record.get("crate"),
            "exact_pin": expected_rev,
            "files": file_facts,
            "duplicate": duplicate,
            "pr": live_records[-1],
        })

    findings.extend(validate_smokes(records, benchmark_report))
    fetch_holder.cleanup()
    report = make_report(evidence, records, facts, findings, live_records)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "consumers": len(records), "blocking_findings": len(findings), "report": report_label(report_path)}, sort_keys=True))
    return 1 if findings else 0


def self_test() -> int:
    """Negative controls for the validator's trust boundaries."""
    with tempfile.TemporaryDirectory(prefix="rust005-adoption-selftest-") as raw:
        root = Path(raw)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
        (root / "src").mkdir()
        (root / "Cargo.toml").write_text('[workspace]\nmembers=[]\n[workspace.dependencies]\nsymaira-core-version = { git = "https://github.com/danieljustus/symaira-corekit", rev = "73f3fbd8c02ef9670346e144e42d8f134e2b3934" }\n', encoding="utf-8")
        (root / "Cargo.lock").write_text('version = 4\n[[package]]\nname = "symaira-core-version"\nversion = "0.0.0"\nsource = "git+https://github.com/danieljustus/symaira-corekit?rev=73f3fbd8c02ef9670346e144e42d8f134e2b3934#73f3fbd8c02ef9670346e144e42d8f134e2b3934"\n', encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "-c", "user.email=test@example.invalid", "-c", "user.name=test", "commit", "-qm", "initial"], cwd=root, check=True)
        record = {"repository": "test/consumer", "manifest_paths": ["Cargo.toml"], "pre_adoption_commit": git("rev-parse", "HEAD", cwd=root), "adoption_commit": git("rev-parse", "HEAD", cwd=root), "duplicate": {"corekit_loc_added": 0, "adapter_loc_added": 0, "duplicate_loc_removed": 0, "source_paths": []}}
        assert_clean_checkout(root, "test/consumer")
        _, findings = validate_consumer_files(record, root, "73f3fbd8c02ef9670346e144e42d8f134e2b3934")
        assert not findings, findings
        (root / "Cargo.toml").write_text((root / "Cargo.toml").read_text().replace("73f3fbd8c02ef9670346e144e42d8f134e2b3934", "0" * 40), encoding="utf-8")
        _, findings = validate_consumer_files(record, root, "73f3fbd8c02ef9670346e144e42d8f134e2b3934")
        assert any("rev" in finding.message for finding in findings), "manipulated pin was accepted"
        (root / "Cargo.toml").write_text((root / "Cargo.toml").read_text().replace('rev = "' + "0" * 40 + '"', 'path = "../../symaira-corekit"'), encoding="utf-8")
        _, findings = validate_consumer_files(record, root, "73f3fbd8c02ef9670346e144e42d8f134e2b3934")
        assert any("path" in finding.message for finding in findings), "sibling path dependency was accepted"
        (root / "Cargo.toml").write_text('[workspace]\nmembers=[]\n', encoding="utf-8")
        _, findings = validate_consumer_files(record, root, "73f3fbd8c02ef9670346e144e42d8f134e2b3934")
        assert any("absent" in finding.message for finding in findings), "one consumer missing-pin control failed"
        (root / "Cargo.lock").unlink()
        _, findings = validate_consumer_files(record, root, "73f3fbd8c02ef9670346e144e42d8f134e2b3934")
        assert any("Cargo.lock" in finding.message for finding in findings), "missing lock control failed"
        try:
            validate_minimum([record, dict(record)], 2)
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate consumer control failed")
        try:
            safe_workspace_path("../escape")
        except ValueError:
            pass
        else:
            raise AssertionError("checkout traversal control failed")
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/wrong/repo.git"], cwd=root, check=True)
        try:
            assert_origin(root, "test/consumer")
        except (RuntimeError, ValueError):
            pass
        else:
            raise AssertionError("origin mismatch control failed")
        try:
            assert_clean_checkout(root, "test/consumer")
        except ValueError:
            pass
        else:
            raise AssertionError("dirty checkout control failed")
    print("PASS adoption negative controls: manipulated pin, path dependency, missing pin/lock, duplicate consumer, path traversal, origin mismatch, dirty checkout")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--min-consumers", type=int, default=2)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--offline", action="store_true", help="use explicitly recorded offline PR state; tests only")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            return self_test()
        if not args.check:
            parser.error("use --check")
        if args.min_consumers < 2:
            parser.error("--min-consumers must be at least 2")
        return check(args.evidence, args.report, args.min_consumers, args.offline)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        print(f"FAIL adoption: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
