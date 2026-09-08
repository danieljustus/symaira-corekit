#!/usr/bin/env python3
"""Verify released CoreKit consumer pins without network or optimistic claims.

The verifier is deliberately read-only. It checks every record in
``docs/consumers.json`` and reports blockers when a checkout or an evidence
artifact is missing. It never treats a Git revision as a registry release,
a Cargo.toml declaration as a resolved lockfile, or a command description as
standalone/rollback proof.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import re
from pathlib import Path
import subprocess
import sys
import tomllib
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "consumers.json"
COREKIT_MODULE = "github.com/danieljustus/symaira-corekit"
COREKIT_URL = "https://github.com/danieljustus/symaira-corekit"
COREKIT_PACKAGE = "symaira-core-version"
CRATES_IO_SOURCE = "registry+https://github.com/rust-lang/crates.io-index"
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_TAG_RE = re.compile(r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
RUST_STATUSES = frozenset({"not_adopted", "git", "registry"})
GO_VERSION_RE = re.compile(
    r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
GO_REQUIRE_RE = re.compile(r"^\s*" + re.escape(COREKIT_MODULE) + r"\s+(\S+)")
SEMVER_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
EXACT_CARGO_RE = re.compile(r"^=(.+)$")


@dataclass(frozen=True)
class Finding:
    repository: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"repository": self.repository, "code": self.code, "message": self.message}


def parse_go_pin(text: str) -> str | None:
    """Return the exact CoreKit Go version, including pseudo-versions."""
    in_require = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_require = True
            continue
        if in_require and stripped == ")":
            in_require = False
            continue
        if in_require or stripped.startswith("require "):
            match = GO_REQUIRE_RE.match(line.removeprefix("require ").lstrip())
            if match and GO_VERSION_RE.fullmatch(match.group(1)):
                return match.group(1)
    return None


def _git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _add(findings: list[Finding], repository: str, code: str, message: str) -> None:
    findings.append(Finding(repository, code, message))


def _safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    candidate.relative_to(root.resolve())
    return candidate


def _dependency_tables(document: dict[str, Any]) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for key in ("dependencies", "dev-dependencies", "build-dependencies"):
        value = document.get(key)
        if isinstance(value, dict):
            tables.append(value)
    target = document.get("target")
    if isinstance(target, dict):
        for target_document in target.values():
            if isinstance(target_document, dict):
                for key in ("dependencies", "dev-dependencies", "build-dependencies"):
                    value = target_document.get(key)
                    if isinstance(value, dict):
                        tables.append(value)
    workspace = document.get("workspace")
    if isinstance(workspace, dict) and isinstance(workspace.get("dependencies"), dict):
        tables.append(workspace["dependencies"])
    return tables


def cargo_specs(manifest: Path) -> list[tuple[str, Any]]:
    document = tomllib.loads(manifest.read_text(encoding="utf-8"))
    result: list[tuple[str, Any]] = []
    for table in _dependency_tables(document):
        result.extend(table.items())
    return result


def _cargo_version(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("version"), str):
        return value["version"]
    return None


def _exact_cargo_version(value: Any) -> str | None:
    """Return the semantic version from a syntactically exact Cargo pin."""
    if not isinstance(value, str):
        return None
    match = EXACT_CARGO_RE.fullmatch(value)
    if not match or not SEMVER_RE.fullmatch(match.group(1)):
        return None
    return match.group(1)


def _expected_rust(record: dict[str, Any]) -> dict[str, Any] | None:
    rust = record.get("rust")
    if not isinstance(rust, dict) or rust.get("status") not in {"git", "registry"}:
        return None
    return rust


def _validate_rust_status(record: dict[str, Any], findings: list[Finding]) -> None:
    """Reject unknown Rust adoption states before any Cargo checks run."""
    repository = str(record.get("repo", "unknown"))
    if "rust" not in record:
        _add(
            findings,
            repository,
            "rust.status",
            "Rust adoption status is required and must be one of: not_adopted, git, registry",
        )
        return
    rust = record["rust"]
    if not isinstance(rust, dict) or rust.get("status") not in RUST_STATUSES:
        _add(
            findings,
            repository,
            "rust.status",
            "Rust adoption status must be one of: not_adopted, git, registry",
        )


def _evidence_error(
    findings: list[Finding], repository: str, name: str, suffix: str, message: str,
) -> None:
    _add(findings, repository, f"evidence.{name}.{suffix}", message)


def _check_evidence(record: dict[str, Any], checkout: Path, findings: list[Finding]) -> None:
    repository = str(record.get("repo", "unknown"))
    rust = _expected_rust(record)
    if rust is None:
        return
    evidence = rust.get("evidence")
    if not isinstance(evidence, dict):
        _add(findings, repository, "evidence.missing", "Rust adoption has no standalone/rollback evidence record")
        return
    release = rust.get("release")
    release_tag = release.get("tag") if isinstance(release, dict) else None
    release_commit = release.get("commit") if isinstance(release, dict) else None
    for name in ("standalone", "rollback"):
        item = evidence.get(name)
        if not isinstance(item, dict) or item.get("status") != "verified":
            _add(findings, repository, f"evidence.{name}", f"{name} evidence is not verified")
            continue
        report_relative = item.get("report")
        artifact_relative = item.get("artifact")
        command = item.get("command")
        result = item.get("result")
        if not isinstance(report_relative, str) or not report_relative.strip():
            _evidence_error(findings, repository, name, "report", f"{name} evidence needs a committed structured report path")
            continue
        if not isinstance(artifact_relative, str) or not artifact_relative.strip():
            _evidence_error(findings, repository, name, "artifact", f"{name} evidence needs an artifact path")
        if not isinstance(command, str) or not command.strip() or command.strip() in ("true", "/bin/true"):
            _evidence_error(findings, repository, name, "command", f"{name} evidence needs a non-fabricated observed command")
        if not isinstance(result, dict) or set(result) != {"exit_code", "stdout", "stderr"} or result.get("exit_code") != 0 or not isinstance(result.get("stdout"), str) or not isinstance(result.get("stderr"), str):
            _evidence_error(findings, repository, name, "result", f"{name} evidence needs an observed successful command result")
        try:
            report_path = _safe_child(checkout, report_relative)
        except (TypeError, ValueError):
            _evidence_error(findings, repository, name, "report", f"{name} report path escapes the consumer checkout")
            continue
        if not report_path.is_file():
            _evidence_error(findings, repository, name, "report", f"{name} report is unavailable locally: {report_relative}")
            continue
        code, tracked, _ = _git(["ls-files", "--error-unmatch", "--", report_relative], checkout)
        if code or tracked != report_relative:
            _evidence_error(findings, repository, name, "report", f"{name} report is not a tracked committed artifact: {report_relative}")
            continue
        code, _, _ = _git(["diff", "--cached", "--quiet"], checkout)
        if code:
            _evidence_error(findings, repository, name, "report", f"{name} report cannot be accepted while the checkout has staged but uncommitted changes")
            continue
        code, _, _ = _git(["diff", "--quiet", "--", report_relative], checkout)
        if code:
            _evidence_error(findings, repository, name, "report", f"{name} report has uncommitted changes: {report_relative}")
            continue
        code, _, _ = _git(["diff", "--quiet", "HEAD", "--", report_relative], checkout)
        if code:
            _evidence_error(findings, repository, name, "report", f"{name} report does not match the committed HEAD: {report_relative}")
            continue
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            _evidence_error(findings, repository, name, "report", f"{name} report is not valid JSON: {error}")
            continue
        if not isinstance(report, dict):
            _evidence_error(findings, repository, name, "report", f"{name} report must contain an object")
            continue
        if report.get("tag") != release_tag or report.get("commit") != release_commit:
            _evidence_error(findings, repository, name, "release", f"{name} report does not contain the exact release tag and commit")
        if report.get("artifact") != artifact_relative:
            _evidence_error(findings, repository, name, "artifact", f"{name} report artifact does not match the evidence record")
        observed = report.get("observed")
        expected_observed = {"command": command, **result} if isinstance(command, str) and isinstance(result, dict) else None
        if observed != expected_observed:
            _evidence_error(findings, repository, name, "result", f"{name} report does not contain the exact observed command result")
        if isinstance(artifact_relative, str):
            try:
                artifact_path = _safe_child(checkout, artifact_relative)
            except (TypeError, ValueError):
                artifact_path = None
            if artifact_path is None or not artifact_path.is_file():
                _evidence_error(findings, repository, name, "artifact", f"{name} artifact is unavailable locally: {artifact_relative}")


def _check_release_ancestry(
    repository: str,
    rust: dict[str, Any],
    corekit_root: Path,
    findings: list[Finding],
) -> None:
    release = rust.get("release")
    if not isinstance(release, dict):
        _add(findings, repository, "release.missing", "Rust pin has no release tag/commit evidence")
        return
    tag = release.get("tag")
    commit = release.get("commit")
    status = rust.get("status")
    if not isinstance(tag, str) or not tag or not isinstance(commit, str) or not REVISION_RE.fullmatch(commit):
        _add(findings, repository, "release.shape", "release evidence needs a tag and 40-hex commit")
        return
    code, resolved, _ = _git(["rev-parse", f"{tag}^{{commit}}"], corekit_root)
    if code or resolved != commit:
        _add(findings, repository, "release.tag", f"release tag {tag} does not resolve to recorded commit")

    candidate_key = "revision" if status == "git" else "release_candidate"
    candidate = rust.get(candidate_key)
    if status != "git" and candidate is None:
        candidate = rust.get("revision")
    if candidate is None:
        if status == "git":
            _add(findings, repository, "rust.revision", "Git adoption needs a 40-hex revision")
        return
    if not isinstance(candidate, str) or not REVISION_RE.fullmatch(candidate):
        _add(findings, repository, "rust.revision", "adoption/release-candidate revision must be a 40-hex commit")
        return
    code, _, _ = _git(["cat-file", "-e", f"{candidate}^{{commit}}"], corekit_root)
    if code:
        _add(findings, repository, "rust.revision", f"adoption revision {candidate} is not present in CoreKit")
        return
    # Adoption commits may be made after a release. The release must be in
    # their history; checking the inverse rejects legitimate post-release pins.
    code, _, _ = _git(["merge-base", "--is-ancestor", commit, candidate], corekit_root)
    if code:
        _add(findings, repository, "release.ancestry", f"release {tag} ({commit}) is not an ancestor of adoption/release candidate {candidate}")


def _check_rust(
    record: dict[str, Any],
    checkout: Path,
    corekit_root: Path,
    findings: list[Finding],
) -> None:
    repository = str(record.get("repo", "unknown"))
    rust = _expected_rust(record)
    if rust is None:
        return
    if rust.get("package") != COREKIT_PACKAGE:
        _add(
            findings,
            repository,
            "rust.package",
            f"Rust adoption package must be exactly {COREKIT_PACKAGE!r}",
        )
        return
    manifest_paths = rust.get("manifest_paths")
    if not isinstance(manifest_paths, list) or not manifest_paths:
        _add(findings, repository, "rust.manifests", "Rust adoption needs at least one Cargo.toml path")
        return
    expected_package = rust.get("package", COREKIT_PACKAGE)
    expected_version = rust.get("version")
    expected_revision = rust.get("revision")
    pins: list[tuple[Path, Any]] = []
    for relative in manifest_paths:
        if not isinstance(relative, str) or Path(relative).name != "Cargo.toml":
            _add(findings, repository, "rust.manifest.path", f"invalid Cargo.toml path: {relative!r}")
            continue
        try:
            path = _safe_child(checkout, relative)
            document = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
            _add(findings, repository, "rust.manifest.read", f"cannot read {relative}: {error}")
            continue
        package = document.get("package")
        if isinstance(package, dict) and package.get("name") == expected_package:
            if expected_version is not None and package.get("version") != expected_version:
                _add(findings, repository, "rust.version", f"{relative}: package version is {package.get('version')!r}, expected {expected_version!r}")
        for dependency, spec in cargo_specs(path):
            if isinstance(spec, dict) and spec.get("workspace") is True:
                workspace_manifest = checkout / "Cargo.toml"
                if workspace_manifest.is_file():
                    try:
                        workspace_document = tomllib.loads(workspace_manifest.read_text(encoding="utf-8"))
                        workspace = workspace_document.get("workspace", {})
                        workspace_dependencies = workspace.get("dependencies", {}) if isinstance(workspace, dict) else {}
                        if isinstance(workspace_dependencies, dict) and dependency in workspace_dependencies:
                            spec = workspace_dependencies[dependency]
                    except (OSError, tomllib.TOMLDecodeError):
                        pass
            if dependency == expected_package:
                pins.append((path, spec))
    if not pins:
        _add(findings, repository, "rust.pin.missing", f"no {expected_package} dependency found in declared manifests")
    status = rust.get("status")
    recorded_version = expected_version if status == "git" else rust.get("registry_version")
    if not isinstance(recorded_version, str) or not SEMVER_RE.fullmatch(recorded_version):
        _add(findings, repository, "rust.version.shape", "recorded Rust dependency version is not valid SemVer")
    for path, spec in pins:
        relative = path.relative_to(checkout).as_posix()
        if not isinstance(spec, dict):
            _add(findings, repository, "rust.pin.shape", f"{relative}: dependency must be a table with an exact version")
            continue
        version = _exact_cargo_version(_cargo_version(spec))
        if version is None:
            _add(findings, repository, "rust.pin.exact", f"{relative}: Rust dependency must use an exact =MAJOR.MINOR.PATCH version")
        elif version != recorded_version:
            _add(findings, repository, "rust.pin.version", f"{relative}: dependency version {version!r} != recorded {recorded_version!r}")
        if status == "git":
            if spec.get("git") != COREKIT_URL or spec.get("rev") != expected_revision:
                _add(findings, repository, "rust.pin.git", f"{relative}: Git URL/revision does not match recorded adoption")
            if "path" in spec:
                _add(findings, repository, "rust.pin.path", f"{relative}: sibling CoreKit path dependency is forbidden")
        elif status == "registry":
            if "git" in spec or "path" in spec or spec.get("registry") not in (None, "crates-io"):
                _add(findings, repository, "rust.pin.registry", f"{relative}: registry adoption must use crates.io without git/path fields")
            registry_version = rust.get("registry_version")
            if version is not None and version != registry_version:
                _add(findings, repository, "rust.pin.registry_version", f"{relative}: registry version {version!r} != ={registry_version}")
    lock_path = checkout / "Cargo.lock"
    if not lock_path.is_file():
        _add(findings, repository, "rust.lock.missing", "Cargo.lock is required to prove the resolved Rust pin")
        _check_release_ancestry(repository, rust, corekit_root, findings)
        return
    try:
        lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        _add(findings, repository, "rust.lock.invalid", f"Cargo.lock is invalid: {error}")
        _check_release_ancestry(repository, rust, corekit_root, findings)
        return
    packages = [package for package in lock.get("package", []) if isinstance(package, dict) and package.get("name") == expected_package]
    if not packages:
        _add(findings, repository, "rust.lock.unique", f"Cargo.lock must contain {expected_package}")
        _check_release_ancestry(repository, rust, corekit_root, findings)
        return
    package = packages[0]
    if status == "git":
        expected_source = f"git+{COREKIT_URL}?rev={expected_revision}#{expected_revision}"
        matching = [item for item in packages if item.get("source") == expected_source]
        if matching:
            package = matching[0]
        if package.get("source") != expected_source:
            _add(findings, repository, "rust.lock.source", f"Cargo.lock source {package.get('source')!r} != {expected_source!r}")
        if "checksum" in package:
            _add(findings, repository, "rust.lock.checksum", "Git-sourced Cargo.lock package must not claim a registry checksum")
    elif status == "registry":
        matching = [item for item in packages if item.get("source") == CRATES_IO_SOURCE]
        if matching:
            package = matching[0]
        if package.get("source") != CRATES_IO_SOURCE:
            _add(findings, repository, "rust.lock.registry_source", "registry adoption must resolve from the crates.io registry source")
        if not isinstance(package.get("checksum"), str) or not re.fullmatch(r"[0-9a-f]{64}", package["checksum"]):
            _add(findings, repository, "rust.lock.checksum", "registry adoption requires a 64-hex Cargo.lock checksum")
    else:
        matching = packages
    if len(matching) != 1:
        _add(findings, repository, "rust.lock.unique", f"Cargo.lock must contain exactly one matching {expected_package} package, found {len(matching)}")
    else:
        resolved_version = matching[0].get("version")
        if resolved_version != recorded_version:
            _add(findings, repository, "rust.lock.version", f"Cargo.lock resolves {expected_package} to {resolved_version!r}, recorded pin is {recorded_version!r}")
        for path, spec in pins:
            declared = _exact_cargo_version(_cargo_version(spec))
            if declared is not None and declared != resolved_version:
                _add(findings, repository, "rust.lock.version", f"Cargo.lock version {resolved_version!r} does not match manifest pin {declared!r}")
    _check_release_ancestry(repository, rust, corekit_root, findings)
    registry = rust.get("registry")
    if status == "registry" and (not isinstance(registry, dict) or registry.get("status") != "published"):
        _add(findings, repository, "registry.status", "registry pin is claimed without published/read-back registry evidence")
    if status == "git" and isinstance(registry, dict) and registry.get("status") == "published":
        _add(findings, repository, "registry.mismatch", "Git pin cannot be reported as a registry release")


def _skip_go_ignored(text: str, index: int) -> int:
    while index < len(text):
        if text[index].isspace():
            index += 1
        elif text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = len(text) if newline < 0 else newline + 1
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = len(text) if end < 0 else end + 2
        else:
            break
    return index


def _skip_go_string(text: str, index: int) -> int:
    quote = text[index]
    index += 1
    while index < len(text):
        if quote != "`" and text[index] == "\\":
            index += 2
        elif text[index] == quote:
            return index + 1
        else:
            index += 1
    return len(text)


def _go_import_string(text: str, index: int) -> tuple[str | None, int]:
    if index >= len(text) or text[index] != '"':
        return None, index
    end = index + 1
    while end < len(text):
        if text[end] == "\\":
            return None, _skip_go_string(text, index)
        if text[end] == '"':
            return text[index + 1:end], end + 1
        end += 1
    return None, len(text)


def go_imports(text: str) -> list[str]:
    """Parse Go import declarations while ignoring comments and literals."""
    imports: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("//", index) or text.startswith("/*", index):
            index = _skip_go_ignored(text, index)
            continue
        if text[index] in ('"', "'", "`"):
            index = _skip_go_string(text, index)
            continue
        if text[index].isalpha() or text[index] == "_":
            start = index
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                index += 1
            if text[start:index] != "import":
                continue
            index = _skip_go_ignored(text, index)
            if index < len(text) and text[index] == "(":
                index += 1
                while index < len(text):
                    index = _skip_go_ignored(text, index)
                    if index >= len(text) or text[index] == ")":
                        index += 1
                        break
                    if text[index] in (".", "_") or text[index].isalpha():
                        index += 1
                        while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                            index += 1
                        index = _skip_go_ignored(text, index)
                    imported, index_after = _go_import_string(text, index)
                    if imported is not None:
                        imports.append(imported)
                    index = index_after if index_after > index else index + 1
            else:
                # A single import may have an optional alias: import _ "path".
                if index < len(text) and text[index] != '"':
                    while index < len(text) and (text[index].isalnum() or text[index] in "._"):
                        index += 1
                    index = _skip_go_ignored(text, index)
                imported, index_after = _go_import_string(text, index)
                if imported is not None:
                    imports.append(imported)
                index = index_after if index_after > index else index + 1
        else:
            index += 1
    return imports


def _tracked_go_files(checkout: Path) -> tuple[bool, list[Path]]:
    code, output, _ = _git(["ls-files", "-z", "--", "*.go"], checkout)
    if code:
        return False, []
    paths: list[Path] = []
    for relative in output.split("\0"):
        if not relative:
            continue
        parts = Path(relative).parts
        if any(part in (".git", ".worktrees", "vendor") for part in parts):
            continue
        paths.append(checkout / relative)
    return True, paths


def tracked_go_imports(checkout: Path) -> list[str]:
    available, paths = _tracked_go_files(checkout)
    if not available:
        return []
    imports: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if any(imported == COREKIT_MODULE or imported.startswith(COREKIT_MODULE + "/") for imported in go_imports(text)):
            imports.append(path.relative_to(checkout).as_posix())
    return imports


def _check_go(record: dict[str, Any], checkout: Path, findings: list[Finding]) -> None:
    repository = str(record.get("repo", "unknown"))
    pins = record.get("pins")
    if not isinstance(pins, list) or not pins:
        _add(findings, repository, "go.manifests", "consumer record needs a non-empty pins array")
        return
    found: list[str] = []
    for relative in pins:
        if not isinstance(relative, str):
            _add(findings, repository, "go.manifest.path", "Go pin path must be a string")
            continue
        try:
            path = _safe_child(checkout, relative)
        except ValueError:
            _add(findings, repository, "go.manifest.path", f"Go manifest path escapes checkout: {relative}")
            continue
        if not path.is_file():
            _add(findings, repository, "go.manifest.missing", f"missing declared Go manifest: {relative}")
            continue
        pin = parse_go_pin(path.read_text(encoding="utf-8"))
        if pin is None:
            _add(findings, repository, "go.pin.missing", f"no exact CoreKit require found in {relative}")
        else:
            found.append(pin)
    if found and len(set(found)) != 1:
        _add(findings, repository, "go.pin.inconsistent", f"declared Go manifests disagree: {sorted(set(found))}")
    available, _ = _tracked_go_files(checkout)
    imports = tracked_go_imports(checkout)
    if not available:
        _add(findings, repository, "go.imports.unavailable", "cannot inspect the selected repository's tracked Go files")
    elif not imports:
        _add(findings, repository, "go.imports.missing", "no tracked Go import of the CoreKit module was found")


def canonical_checkout(repo_root: Path) -> Path:
    code, common, error = _git(["rev-parse", "--path-format=absolute", "--git-common-dir"], repo_root)
    if code:
        raise RuntimeError(error or "cannot resolve Git common directory")
    common_path = Path(common)
    return common_path.parent if common_path.name == ".git" else common_path


def verify_manifest(
    manifest_path: Path = MANIFEST,
    *,
    workspace_root: Path | None = None,
    corekit_root: Path | None = None,
) -> dict[str, Any]:
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = document.get("consumers") if isinstance(document, dict) else None
    findings: list[Finding] = []
    corekit = document.get("corekit") if isinstance(document, dict) else None
    if not isinstance(corekit, dict) or corekit.get("repository") != "danieljustus/symaira-corekit" or corekit.get("go_module") != COREKIT_MODULE:
        raise ValueError("docs/consumers.json corekit repository/module is invalid")
    registry = corekit.get("rust_registry")
    if not isinstance(registry, dict) or registry.get("package") != COREKIT_PACKAGE or registry.get("status") != "not_released":
        raise ValueError("docs/consumers.json must keep Rust registry status not_released")
    if not isinstance(records, list) or not records:
        raise ValueError("docs/consumers.json must contain a non-empty consumers array")
    repositories: set[str] = set()
    if workspace_root is None:
        workspace_root = canonical_checkout(ROOT).parent
    if corekit_root is None:
        corekit_root = canonical_checkout(ROOT)

    release_tag = corekit.get("release_tag")
    release_commit = corekit.get("release_commit")
    if not isinstance(release_tag, str) or not RELEASE_TAG_RE.fullmatch(release_tag):
        _add(findings, "corekit", "release.shape", "CoreKit release tag must be a stable vMAJOR.MINOR.PATCH tag")
    elif not isinstance(release_commit, str) or not REVISION_RE.fullmatch(release_commit):
        _add(findings, "corekit", "release.shape", "CoreKit release commit must be a 40-hex commit")
    else:
        code, resolved, _ = _git(["rev-parse", f"{release_tag}^{{commit}}"], corekit_root)
        if code or resolved != release_commit:
            _add(findings, "corekit", "release.tag", f"release tag {release_tag} does not resolve to recorded commit")

    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("repo"), str) or "/" not in record["repo"]:
            findings.append(Finding("unknown", "record.shape", "consumer record must contain an owner/name repo"))
            continue
        repository = record["repo"]
        if repository in repositories:
            _add(findings, repository, "record.duplicate", "consumer record is duplicated")
            continue
        repositories.add(repository)
        _validate_rust_status(record, findings)
        checkout = (workspace_root / repository.rsplit("/", 1)[1]).resolve()
        if not checkout.is_dir():
            _add(findings, repository, "checkout.missing", f"canonical checkout is missing: {checkout}")
            continue
        _check_go(record, checkout, findings)
        _check_rust(record, checkout, corekit_root, findings)
        _check_evidence(record, checkout, findings)
    return {
        "schema_version": 1,
        "status": "passed" if not findings else "blocked",
        "manifest": str(manifest_path),
        "consumer_count": len(records),
        "checked_repositories": sorted(repositories),
        "findings": [finding.as_dict() for finding in findings],
        "honesty": "A consumer is passed only when exact pins, lock resolution, release ancestry, imports, and required evidence are all read back.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--released-consumers", action="store_true", help="verify every record in docs/consumers.json")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--corekit-root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if not args.released_consumers:
        parser.error("--released-consumers is required; verification is never implicit")
    try:
        workspace = args.workspace_root.resolve() if args.workspace_root else None
        corekit = args.corekit_root.resolve() if args.corekit_root else canonical_checkout(ROOT)
        report = verify_manifest(args.manifest.resolve(), workspace_root=workspace, corekit_root=corekit)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        print(f"error: consumer verification unavailable: {error}", file=sys.stderr)
        return 2
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
