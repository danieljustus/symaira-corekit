"""Explicit source freeze for SQLite diagnostic acceptance, never auto-refreshed."""
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
import generate

ROOT = generate.ROOT
DEFAULT = ROOT / 'testdata/rust-port/sqlite/candidate-source.json'
EXPECTED_BASE = '82968b4fc9537daf62c2008331f5e5ce5d32b6c6'


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
    if report.get('source_hashes') != manifest['source_hashes']:
        raise ValueError('Rust report differs from frozen source manifest')
    # A report and manifest must not be accepted merely because they agree with
    # each other. Recompute the manifest against the files that will actually
    # be built, so co-mutated evidence cannot replace the real source.
    if snapshot() != manifest['source_hashes']:
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
