"""Explicit source freeze for SQLite diagnostic acceptance, never auto-refreshed.

`snapshot()` records the complete forensic source set in one pass at freeze
time. Only its `enforced()` subset is bound when existing evidence is verified:
the files that determine the captured Rust artifact and the observations of the
SQLite differential. The remaining recorded files are forensic context and are
deliberately not enforced, so routine maintenance cannot invalidate retained
evidence. Per-file-class decision:
docs/rust-port/adr-rust-003-candidate-source-scope.md.
"""
import argparse
import hashlib
import json
import re
import tomllib
from pathlib import Path, PurePosixPath
import generate

ROOT = generate.ROOT
DEFAULT = ROOT / 'testdata/rust-port/sqlite/candidate-source.json'
EXPECTED_BASE = '82968b4fc9537daf62c2008331f5e5ce5d32b6c6'

# Workspace build inputs: the resolved dependency graph and the compiler pin.
ENFORCED_FILES = ('Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml')
# The crate under test, its workspace path dependencies, and the Go oracle,
# migration corpus and harness that produce the compared observations.
ENFORCED_TREES = ('rust/symaira-core-sqlite', 'rust/symaira-core-fs',
                  'scripts/rust-port/sqlite')
# Optional build configuration; enforced when present, never required.
OPTIONAL_ENFORCED_TREES = ('.cargo',)
SQLITE_MANIFEST = ROOT / 'rust/symaira-core-sqlite/Cargo.toml'


def snapshot():
    paths = {ROOT / 'Cargo.toml', ROOT / 'Cargo.lock', ROOT / 'rust-toolchain.toml',
             ROOT / 'scripts/rust-port/sqlite/go.mod', ROOT / 'scripts/rust-port/sqlite/go.sum'}
    for optional in ('.gitattributes', '.cargo/config', '.github/workflows/ci.yml'):
        if (ROOT / optional).is_file():
            paths.add(ROOT / optional)
    for base in (ROOT / 'rust', ROOT / 'scripts/rust-port/sqlite', ROOT / '.cargo'):
        if base.exists():
            paths.update(p for p in base.rglob('*') if p.is_file()
                         and p.suffix in {'.rs', '.toml', '.py', '.go', '.sql'}
                         and '__pycache__' not in p.parts and 'target' not in p.relative_to(base).parts)
    result = {}
    for path in sorted(paths):
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('candidate source escapes repository')
        result[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def is_enforced(path):
    """True when the path determines the built artifact or the observations."""
    return (path in ENFORCED_FILES
            or any(path.startswith(tree + '/')
                   for tree in ENFORCED_TREES + OPTIONAL_ENFORCED_TREES))


def enforced(hashes):
    """Binding view of a hash mapping; the recorded superset stays forensic."""
    return {path: digest for path, digest in hashes.items() if is_enforced(path)}


def port_path_dependencies(manifest=SQLITE_MANIFEST, seen=None):
    """Repository-relative directories of the crate's transitive path dependencies.

    Keeps the enforced scope honest when the dependency graph changes: a new
    workspace path dependency must be covered, or the manifest is rejected
    instead of silently verifying an incomplete input set.
    """
    seen = set() if seen is None else seen
    manifest = Path(manifest)
    document = tomllib.loads(manifest.read_text())
    tables = [document.get('dependencies'), document.get('dev-dependencies'),
              document.get('build-dependencies')]
    for value in (document.get('target') or {}).values():
        if isinstance(value, dict):
            tables.extend(value.get(name) for name in
                          ('dependencies', 'dev-dependencies', 'build-dependencies'))
    found = set()
    for table in tables:
        for spec in (table or {}).values():
            if not isinstance(spec, dict) or 'path' not in spec:
                continue
            dependency = (manifest.parent / spec['path']).resolve()
            if not dependency.is_relative_to(ROOT.resolve()):
                raise ValueError('path dependency escapes repository')
            relative = dependency.relative_to(ROOT.resolve()).as_posix()
            if relative in seen:
                continue
            seen.add(relative)
            found.add(relative)
            if (dependency / 'Cargo.toml').is_file():
                found.update(port_path_dependencies(dependency / 'Cargo.toml', seen))
    return sorted(found)


def validate_scope():
    """Every workspace path dependency of the crate under test must be enforced."""
    for dependency in port_path_dependencies():
        if not any(dependency == tree or dependency.startswith(tree + '/')
                   for tree in ENFORCED_TREES):
            raise ValueError(f'candidate scope does not cover path dependency {dependency}')


def load(path=DEFAULT):
    raw = Path(path).read_bytes()
    manifest = json.loads(raw)
    validate_manifest(manifest)
    return manifest, hashlib.sha256(raw).hexdigest()


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 1:
        raise ValueError('invalid frozen source manifest')
    validate_base(manifest)
    source_hashes = manifest.get('source_hashes')
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError('invalid frozen source manifest')
    for path, digest in source_hashes.items():
        if (not isinstance(path, str) or not path or '\\' in path
                or PurePosixPath(path).is_absolute()
                or '..' in PurePosixPath(path).parts):
            raise ValueError('invalid frozen source manifest path')
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('invalid frozen source manifest digest')
    if any(path not in source_hashes for path in ENFORCED_FILES):
        raise ValueError('frozen source manifest omits a required build input')
    for tree in ENFORCED_TREES:
        if not any(path.startswith(tree + '/') for path in source_hashes):
            raise ValueError('frozen source manifest omits an enforced source tree')
    validate_scope()


def validate_base(manifest):
    base = manifest.get('base')
    if not isinstance(base, str) or not re.fullmatch('[0-9a-f]{40}', base):
        raise ValueError('missing or malformed candidate base')
    if base != EXPECTED_BASE:
        raise ValueError('candidate base differs from immutable expected base')


def verify(report, manifest, manifest_sha256):
    # Validate the baseline representation before any Git command can resolve
    # a moving ref, abbreviation, revision expression, or other input.
    validate_manifest(manifest)
    if not isinstance(manifest_sha256, str) or not re.fullmatch('[0-9a-f]{64}', manifest_sha256):
        raise ValueError('missing or malformed candidate manifest digest')
    if report.get('candidate_manifest_sha256') != manifest_sha256:
        raise ValueError('Rust report differs from frozen candidate manifest digest')
    report_hashes = report.get('source_hashes')
    if not isinstance(report_hashes, dict):
        raise ValueError('Rust report differs from frozen source manifest')
    if enforced(report_hashes) != enforced(manifest['source_hashes']):
        raise ValueError('Rust report differs from frozen source manifest')
    # A report and manifest must not be accepted merely because they agree with
    # each other. Recompute the manifest against the files that will actually
    # be built, so co-mutated evidence cannot replace the real source. The
    # comparison is scoped to the enforced port inputs: recorded CI, attribute
    # and unrelated-crate digests are forensic context, not build inputs.
    if enforced(snapshot()) != enforced(manifest['source_hashes']):
        raise ValueError('frozen source manifest is not bound to the current candidate source')
    if report.get('candidate_base') != manifest['base']:
        raise ValueError('Rust candidate base differs from frozen manifest')
    revision = report.get('candidate_revision')
    if not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('missing or malformed candidate revision')
    # Validate the declared baseline even when the candidate revision equals it;
    # otherwise a nonexistent object bypasses every Git provenance check below.
    try:
        generate.run(['git', 'cat-file', '-e', f"{manifest['base']}^{{commit}}"], cwd=ROOT)
    except RuntimeError as error:
        raise ValueError('candidate base is not a verified commit') from error
    # The immutable source manifest identifies dirty diagnostic bytes; the
    # revision must independently belong to the declared baseline's history.
    if revision != manifest['base']:
        try:
            generate.run(['git', 'merge-base', '--is-ancestor', manifest['base'], revision], cwd=ROOT)
        except RuntimeError as error:
            raise ValueError('candidate revision is not a verified descendant of the baseline') from error
    try:
        generate.run(['git', 'merge-base', '--is-ancestor', revision, 'HEAD'], cwd=ROOT)
    except RuntimeError as error:
        raise ValueError('candidate revision is not an ancestor of the actual checkout') from error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=DEFAULT)
    args = parser.parse_args()
    args.output.write_text(json.dumps({'schema_version': 1, 'base': EXPECTED_BASE, 'source_hashes': snapshot()}, indent=2, sort_keys=True) + '\n')
    print(f'FROZEN {args.output}; requires independent review, not approval by generation')


if __name__ == '__main__':
    main()
