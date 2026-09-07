"""Shared trust-boundary helpers for RUST-005 evidence validators."""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
from typing import Any, NoReturn
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parents[2].resolve()
GITHUB_API = "https://api.github.com"
GITHUB_WEB = "https://github.com"


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def _parts(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\x00" in value:
        fail(f"{label}: path must be a non-empty string")
    if "\\" in value:
        fail(f"{label}: backslashes are not valid checkout paths")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        fail(f"{label}: path must be relative and contain no traversal")
    return pure.parts


def _no_symlink_traversal(path: Path, base: Path, label: str) -> None:
    current = base
    for part in path.relative_to(base).parts:
        current = current / part
        if current.is_symlink():
            fail(f"{label}: symlink traversal is not allowed: {current}")


def safe_workspace_path(value: Any, label: str = "checkout") -> Path:
    parts = _parts(value, label)
    base = WORKSPACE
    candidate = base.joinpath(*parts)
    resolved_base = base.resolve()
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(resolved_base)
    except ValueError:
        fail(f"{label}: resolved path escapes canonical workspace")
    _no_symlink_traversal(candidate, base, label)
    return resolved


def safe_checkout_child(root: Path, value: Any, label: str) -> Path:
    parts = _parts(value, label)
    canonical_root = root.resolve()
    candidate = root.joinpath(*parts)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(canonical_root)
    except ValueError:
        fail(f"{label}: resolved path escapes checkout")
    _no_symlink_traversal(candidate, root, label)
    return resolved


def repository_slug_from_remote(remote: str) -> str:
    value = remote.strip()
    if value.startswith("git@github.com:"):
        value = value.removeprefix("git@github.com:")
    elif value.startswith("https://github.com/"):
        value = value.removeprefix("https://github.com/")
    elif value.startswith("http://github.com/"):
        value = value.removeprefix("http://github.com/")
    else:
        fail(f"origin remote is not an allowed GitHub URL: {remote!r}")
    value = value.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    parts = value.split("/")
    if len(parts) != 2 or any(not part for part in parts):
        fail(f"origin remote is not an owner/name repository: {remote!r}")
    return "/".join(parts)


def assert_origin(root: Path, repository: str) -> str:
    if not isinstance(repository, str) or repository.count("/") != 1:
        fail("repository must be an owner/name string")
    remote = git("remote", "get-url", "origin", cwd=root)
    actual = repository_slug_from_remote(remote)
    if actual != repository:
        fail(f"origin repository {actual!r} does not exactly match record {repository!r}")
    return remote


def assert_revision(value: Any, label: str) -> str:
    import re
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        fail(f"{label}: expected a 40-character lowercase git revision")
    return value


def github_json(path: str) -> dict[str, Any]:
    base_headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "symaira-corekit-rust005-validator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    attempts = [dict(base_headers)]
    if token:
        attempts.insert(0, {**base_headers, "Authorization": f"Bearer {token}"})
    last_error: Exception | None = None
    for headers in attempts:
        request = Request(f"{GITHUB_API}{path}", headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
            break
        except HTTPError as error:
            last_error = error
            if "Authorization" not in headers or error.code not in {401, 403, 404}:
                raise RuntimeError(f"GitHub REST request failed for {path}: {error}") from error
        except (URLError, TimeoutError) as error:
            raise RuntimeError(f"GitHub REST request failed for {path}: {error}") from error
    else:
        raise RuntimeError(f"GitHub REST request failed for {path}: {last_error}") from last_error
    if not isinstance(payload, dict):
        fail(f"GitHub REST response for {path} is not an object")
    return payload


def assert_public_commit(repository: str, revision: str) -> None:
    assert_revision(revision, f"{repository} commit")
    payload = github_json(f"/repos/{repository}/commits/{revision}")
    sha = payload.get("sha")
    if sha != revision:
        fail(f"GitHub commit readback mismatch for {repository}: {sha!r} != {revision}")


def assert_clean_checkout(checkout: Path, repository: str) -> None:
    dirty = git("status", "--porcelain=v1", "--untracked-files=all", cwd=checkout)
    if dirty:
        fail(f"{repository}: local checkout must be clean at the exact revision")


def clone_exact(repository: str, revisions: list[str], destination: Path) -> Path:
    """Clone only an exact public GitHub repository into a disposable directory."""
    if destination.exists():
        fail(f"clone destination already exists: {destination}")
    for revision in revisions:
        assert_public_commit(repository, revision)
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = f"{GITHUB_WEB}/{repository}.git"
    completed = subprocess.run(
        ["git", "clone", "--filter=blob:none", "--no-checkout", "--quiet", url, str(destination)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"git clone failed: {completed.stderr.decode('utf-8', 'replace').strip()}")
    assert_origin(destination, repository)
    for revision in revisions:
        git("fetch", "--quiet", "origin", revision, cwd=destination)
    git("checkout", "--quiet", "--detach", revisions[-1], cwd=destination)
    if git("rev-parse", "HEAD", cwd=destination) != revisions[-1]:
        fail(f"cloned checkout did not land on exact revision {revisions[-1]}")
    return destination


def checkout_for_record(record: dict[str, Any], revisions: list[str], temporary_root: Path) -> tuple[Path, bool]:
    """Return a trusted local checkout, or an exact disposable clone."""
    repository = record.get("repository")
    checkout_value = record.get("checkout")
    if not isinstance(repository, str):
        fail("consumer record repository is required")
    if not isinstance(checkout_value, str):
        fail(f"{repository}: checkout is required")
    local = safe_workspace_path(checkout_value, f"{repository}.checkout")
    if local.exists():
        if not local.is_dir():
            fail(f"{repository}: checkout is not a directory")
        assert_origin(local, repository)
        head = git("rev-parse", "HEAD", cwd=local)
        if head != revisions[-1]:
            fail(f"{repository}: local checkout HEAD {head} != expected {revisions[-1]}")
        assert_clean_checkout(local, repository)
        return local, False
    clone = temporary_root / repository.replace("/", "-")
    return clone_exact(repository, revisions, clone), True


def trusted_child(root: Path, value: Any, label: str) -> Path:
    path = safe_checkout_child(root, value, label)
    if not path.exists():
        fail(f"{label}: path does not exist beneath checkout: {value}")
    return path


def temporary_directory(prefix: str = "rust005-") -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix=prefix)
