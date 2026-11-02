"""Read Go library sources retired from the working tree.

The Go library was removed after its last release, v0.18.3. Frozen fixture
provenance still binds exact Go source bytes. Those bytes stay readable from
one immutable Git commit instead of from the working tree. A path present in
the given root is always read from that root, so temporary-root mutation
controls keep working. Only absent Go paths fall back to the anchor. Unsafe
relative paths, symlinks and paths resolving outside the root are rejected.

Shallow clones without the anchor commit fail closed.
"""

from __future__ import annotations

import functools
from pathlib import Path, PurePosixPath
import subprocess

ANCHOR_TAG = "v0.18.3"
ANCHOR_COMMIT = "0a446ac7c37c7c29995c261cfa89067196a4f9f4"
REPO = Path(__file__).resolve().parents[2]


def is_go_path(relative: str) -> bool:
    path = PurePosixPath(relative)
    return path.suffix == ".go" or path.name in {"go.mod", "go.sum"}


def _checked_relative(relative: str) -> str:
    path = PurePosixPath(relative)
    if (not relative or "\\" in relative or path.is_absolute()
            or any(part in ("", ".", "..") for part in relative.split("/"))):
        raise ValueError(f"unsafe repository-relative path: {relative!r}")
    return path.as_posix()


def _tree_file(root: Path, relative: str) -> Path | None:
    """Return the in-root regular file, None when absent; reject symlinks/escapes."""
    path = Path(root) / _checked_relative(relative)
    current = Path(root)
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"repository input is a symlink: {relative}")
    if not path.exists():
        return None
    if not path.is_file() or not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError(f"repository input is not an in-root regular file: {relative}")
    return path


@functools.cache
def anchor_blob(relative: str) -> bytes:
    """Return the exact bytes of a retired Go path at the anchor commit."""
    relative = _checked_relative(relative)
    if not is_go_path(relative):
        raise ValueError(f"not a retired Go library path: {relative}")
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{ANCHOR_COMMIT}:{relative}"],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
    )
    if result.returncode != 0:
        raise FileNotFoundError(
            f"retired Go source {relative} is absent at {ANCHOR_TAG} ({ANCHOR_COMMIT}); "
            "a full clone with that commit is required"
        )
    return result.stdout


def exists(root: Path, relative: str) -> bool:
    if _tree_file(root, relative) is not None:
        return True
    if not is_go_path(relative):
        return False
    try:
        anchor_blob(relative)
    except FileNotFoundError:
        return False
    return True


def read_bytes(root: Path, relative: str) -> bytes:
    path = _tree_file(root, relative)
    if path is not None:
        return path.read_bytes()
    if not is_go_path(relative):
        raise FileNotFoundError(f"repository input is absent: {relative}")
    return anchor_blob(relative)
