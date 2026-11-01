"""Read Go library sources retired from the working tree.

The Go library was removed after its last release, v0.18.3. Frozen fixture
provenance still binds exact Go source bytes. Those bytes stay readable from
one immutable Git commit instead of from the working tree. A path present in
the given root is always read from that root, so temporary-root mutation
controls keep working. Only absent Go paths fall back to the anchor.

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


@functools.cache
def anchor_blob(relative: str) -> bytes:
    """Return the exact bytes of a retired Go path at the anchor commit."""
    if not is_go_path(relative) or ".." in PurePosixPath(relative).parts:
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
    path = Path(root) / relative
    if path.is_file():
        return True
    if not is_go_path(relative):
        return False
    try:
        anchor_blob(relative)
    except FileNotFoundError:
        return False
    return True


def read_bytes(root: Path, relative: str) -> bytes:
    path = Path(root) / relative
    if path.exists() or not is_go_path(relative):
        return path.read_bytes()
    return anchor_blob(relative)
