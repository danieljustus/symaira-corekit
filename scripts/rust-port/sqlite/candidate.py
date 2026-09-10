"""Explicit source freeze for SQLite diagnostic acceptance, never auto-refreshed."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import generate

ROOT = generate.ROOT
DEFAULT = ROOT / 'testdata/rust-port/sqlite/candidate-source.json'


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
    if manifest.get('schema_version') != 1 or not manifest.get('source_hashes'):
        raise ValueError('invalid frozen source manifest')
    return manifest, hashlib.sha256(raw).hexdigest()


def verify(report, manifest):
    if report.get('source_hashes') != manifest['source_hashes']:
        raise ValueError('Rust report differs from frozen source manifest')
    if report.get('candidate_base') != manifest['base']:
        raise ValueError('Rust candidate base differs from frozen manifest')
    revision = report.get('candidate_revision')
    if not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('missing or malformed candidate revision')
    # The immutable source manifest identifies dirty diagnostic bytes; the
    # revision must independently belong to the declared baseline's history.
    if revision != manifest['base']:
        try:
            generate.run(['git', 'merge-base', '--is-ancestor', manifest['base'], revision], cwd=ROOT)
        except RuntimeError as error:
            raise ValueError('candidate revision is not a verified descendant of the baseline') from error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=DEFAULT)
    args = parser.parse_args()
    base = generate.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    args.output.write_text(json.dumps({'schema_version': 1, 'base': base, 'source_hashes': snapshot()}, indent=2, sort_keys=True) + '\n')
    print(f'FROZEN {args.output}; requires independent review, not approval by generation')


if __name__ == '__main__':
    main()
