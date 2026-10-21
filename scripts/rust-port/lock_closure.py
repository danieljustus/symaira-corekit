"""Digest of the Cargo.lock entries a set of workspace crates can resolve to.

Frozen FS/SEC and SQLite evidence binds this digest instead of the raw
Cargo.lock bytes (docs/rust-port/adr-rust-004-lockfile-dependency-closure.md).
The closure follows every lockfile dependency edge, including dev and build
edges, so it is a superset of what the bound crates can compile against.
Unresolvable or ambiguous edges fail closed.
"""
import hashlib
import json
import tomllib
from pathlib import Path


def _parse_edge(edge):
    parts = edge.split(" ", 2)
    name = parts[0]
    version = parts[1] if len(parts) > 1 else None
    source = parts[2][1:-1] if len(parts) > 2 else None
    return name, version, source


def closure_packages(lock_path, roots):
    """Return the lockfile package tables reachable from the named workspace crates."""
    lock = tomllib.loads(Path(lock_path).read_text(encoding="utf-8"))
    packages = lock.get("package")
    if not isinstance(packages, list) or not packages:
        raise ValueError("Cargo.lock has no package list")
    by_name = {}
    for package in packages:
        by_name.setdefault(package["name"], []).append(package)

    def resolve(edge):
        name, version, source = _parse_edge(edge)
        matches = [p for p in by_name.get(name, [])
                   if (version is None or p["version"] == version)
                   and (source is None or p.get("source") == source)]
        if len(matches) != 1:
            raise ValueError(f"Cargo.lock dependency edge {edge!r} does not resolve to exactly one package")
        return matches[0]

    pending = []
    for root in roots:
        local = [p for p in by_name.get(root, []) if "source" not in p]
        if len(local) != 1:
            raise ValueError(f"workspace crate {root!r} is not exactly one local Cargo.lock package")
        pending.append(local[0])
    seen = {}
    while pending:
        package = pending.pop()
        key = (package["name"], package["version"], package.get("source"))
        if key in seen:
            continue
        seen[key] = package
        pending.extend(resolve(edge) for edge in package.get("dependencies", []))
    return {"lock_version": lock.get("version"),
            "packages": [seen[key] for key in sorted(seen, key=lambda k: (k[0], k[1], k[2] or ""))]}


def closure_digest(lock_path, roots):
    canonical = json.dumps(closure_packages(lock_path, roots), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
