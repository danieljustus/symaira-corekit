#!/usr/bin/env python3
"""Execute both SQLite adapters; retain raw differences rather than hiding them."""
import argparse

import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

import generate
import typed_contract
import candidate

ROOT = generate.ROOT
MANIFEST = ROOT / "Cargo.toml"
TARGET = Path(os.environ.get("CARGO_TARGET_DIR", ROOT / "target")).resolve()


def _same_json(left, right):
    """Compare JSON values without Python's bool/int equality shortcut."""
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def validate_oracle_provenance(report):
    """Bind a stored Go observation to the real pinned source and helpers."""
    oracle = report.get('oracle')
    if not isinstance(oracle, dict):
        raise ValueError('missing Go oracle provenance')
    if oracle.get('commit') != generate.ORACLE_COMMIT:
        raise ValueError('Go oracle revision differs from pinned source')
    if oracle.get('implementation') != 'sqlitekit.Open/Migrate':
        raise ValueError('Go oracle implementation identity differs from pinned source')
    expected_source = {path: generate.sha(data) for path, data in generate.source_snapshot().items()}
    if not _same_json(oracle.get('source_hashes'), expected_source):
        raise ValueError('Go oracle source provenance differs from pinned source')
    expected_helpers = {path: generate.sha(data) for path, data in generate.helper_snapshot().items()}
    if not _same_json(oracle.get('artifact_hashes'), expected_helpers):
        raise ValueError('Go oracle helper provenance differs from current acceptance helpers')
    cases = report.get('cases')
    if not isinstance(cases, list) or not cases or not isinstance(cases[0], dict):
        raise ValueError('missing Go oracle case state')
    go_state = cases[0].get('state')
    if not isinstance(go_state, dict):
        raise ValueError('missing Go oracle case state')
    goos = go_state.get('native_goos')
    if not isinstance(goos, str) or not goos:
        raise ValueError('missing Go oracle native platform identity')
    expected_isolation = {
        'locale': 'C',
        'timezone': 'UTC',
        'umask': 'not-applicable' if goos == 'windows' else '0077',
        'os_sandbox': False,
    }
    if not _same_json(oracle.get('isolation'), expected_isolation):
        raise ValueError('Go oracle isolation provenance differs from the capture contract')
    if not isinstance(oracle.get('dependencies'), dict):
        raise ValueError('missing Go oracle dependency provenance')



def rust_capture(manifest):
    candidate.validate_base(manifest)
    before = candidate.snapshot()
    if candidate.enforced(before) != candidate.enforced(manifest['source_hashes']):
        raise ValueError('candidate changed since explicit source freeze')
    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(TARGET)
    metadata = json.loads(generate.run(["cargo", "metadata", "--manifest-path", str(MANIFEST),
                                       "--no-deps", "--format-version", "1"], cwd=ROOT, env=env))
    if Path(metadata["workspace_root"]).resolve() != ROOT.resolve():
        raise ValueError("wrong Cargo workspace")
    package = next(p for p in metadata["packages"] if p["name"] == "symaira-core-sqlite")
    if not all(Path(t["src_path"]).resolve().is_relative_to(ROOT.resolve()) for t in package["targets"]):
        raise ValueError("Rust source outside candidate")
    generate.run(["cargo", "build", "--manifest-path", str(MANIFEST), "-p", "symaira-core-sqlite",
                  "--example", "sqlite-observe", "--locked"], cwd=ROOT, env=env, timeout=300)
    binary = TARGET / "debug/examples" / ("sqlite-observe.exe" if os.name == "nt" else "sqlite-observe")
    with tempfile.TemporaryDirectory(prefix="sqlite-rust-diff-") as tmp:
        sandbox = Path(tmp)
        env = generate.isolated_env(sandbox)
        data = sandbox / "databases"
        data.mkdir(mode=0o700)
        data.chmod(0o700)
        start = int(time.time())
        raw = generate.run([str(binary), str(data), str(generate.HELPER)], cwd=data, env=env, timeout=30)
        # The only diagnostic path rewrite substitutes this run-owned root.
        report = generate.normalize_temp_root(json.loads(raw.decode()), data)
        report["capture_interval"] = [start, int(time.time())]
    if candidate.snapshot() != before:
        raise ValueError('candidate source changed during build/capture')
    report['source_hashes'] = before
    generate.run(['git', 'merge-base', '--is-ancestor', manifest['base'], 'HEAD'], cwd=ROOT)
    report['candidate_base'] = manifest['base']
    report['candidate_revision'] = generate.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    report["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    return report


def equal(left, right):
    # JSON type identity matters: Python otherwise treats True == 1.
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def evaluate(go, rust, manifest, manifest_sha256):
    # Validate observable shape before provenance so malformed reports are
    # rejected for the defect they contain, even when an older capture is
    # intentionally being exercised as a historical negative control.
    generate.validate(go)
    generate.validate_observations(rust, require_busy_measurement=True)
    candidate.verify(rust, manifest, manifest_sha256)
    # Stored captures must prove the pinned Go source and the exact helper
    # bytes used to produce them; otherwise a co-mutated report can look valid.
    validate_oracle_provenance(go)
    native = rust.get('native', {})
    go_state = go['cases'][0]['state']
    if (native.get('goos') != go_state['native_goos']
            or native.get('goarch') != go_state['native_goarch']):
        raise ValueError('Go/Rust native platform identity differs')
    return _compare_observations(go, rust)


def _compare_observations(go, rust):
    """Historical state comparison only; never an acceptance entrypoint."""
    generate.validate(go)
    ids = generate.EXPECTED_IDS
    if [c["id"] for c in rust["cases"]] != ids:
        raise ValueError("Rust executed case IDs differ from declared oracle set")
    # Validate raw timestamps using the same explicit creation-window contract.
    g = generate.comparable(go)
    r = generate.comparable(rust)
    differences = []
    checked = []
    for gc, rc in zip(g["cases"], r["cases"]):
        cid = gc["id"]
        gs, rs = gc["state"], rc["state"]
        fields = {
            "SQL-001": ["ping", "database_exists", "parent_exists"] + (["database_mode", "parent_mode"] if go['cases'][0]['state']['native_goos'] != 'windows' else []),
            "SQL-002": ["connections"],
            "SQL-003": ["migration_count", "versions", "schema", "data", "large_integer", "null_value", "applied_at", "repeat"],
            "SQL-004": ["migration_count", "versions", "schema", "data", "large_integer", "null_value", "applied_at", "repeat", "rows_unchanged", "versions_unchanged", "schema_unchanged", "applied_at_unchanged", "replacement_read_attempts", "replacement_error_nil"],
            "SQL-005": ["rollback_probe_absent", "insert_migration_absent", "partial_rerun"],
            "SQL-006": ["in_memory_success", "in_memory"],
        }[cid]
        for field in fields:
            checked.append(f"{cid}/{field}")
            if field not in rs or not equal(gs[field], rs[field]):
                differences.append({"path": checked[-1], "go": gs.get(field), "rust": rs.get(field)})
        if cid == "SQL-002":
            for key, value in gs["contention"].items():
                checked.append(f"{cid}/contention/{key}")
                if key not in rs["contention"] or not equal(value, rs["contention"][key]):
                    differences.append({"path": checked[-1], "go": value, "rust": rs["contention"].get(key)})
        if cid == "SQL-001":
            for gkey, rkey in [("missing_directory", "directory"), ("parent_file", "parent_file")]:
                left = gs["open_errors"][gkey]
                right = rs["open_errors"][rkey]["error"]
                if left != right:
                    differences.append({"path": f"{cid}/open_errors/{gkey}", "go": left, "rust": right})
        for error in gc.get("negative", []):
            name = error["name"]
            observed = rc.get("errors", {}).get(name)
            if observed is None:
                differences.append({"path": f"{cid}/errors/{name}", "go": error["error"],
                                    "rust": None, "reason": rc.get("unsupported", [])})
            elif error["error"] != observed["error"]:
                differences.append({"path": f"{cid}/errors/{name}", "go": error["error"], "rust": observed["error"]})
    return {"status": "passed" if not differences else "partial", "case_ids": ids,
            "checked_fields": checked, "differences": differences}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--typed-errors", action="store_true", help="apply the approved phase/cause and consuming-close contract")
    parser.add_argument('--candidate-manifest', type=Path, default=candidate.DEFAULT)
    args = parser.parse_args()
    manifest, manifest_sha = candidate.load(args.candidate_manifest)
    if candidate.enforced(candidate.snapshot()) != candidate.enforced(manifest['source_hashes']):
        raise ValueError('candidate changed since explicit source freeze')
    go = generate.capture()
    rust = rust_capture(manifest)
    rust['candidate_manifest_sha256'] = manifest_sha
    try:
        verdict = evaluate(go, rust, manifest, manifest_sha)
        if args.typed_errors:
            verdict = typed_contract.apply(go, rust, verdict)
    except (ValueError, KeyError, TypeError) as error:
        # Preserve actual observations even when schema/success validation fails.
        args.output.write_text(json.dumps({'verdict': {'status': 'failed', 'error': str(error)},
                                          'go': go, 'rust': rust}, indent=2, sort_keys=True) + '\n')
        raise
    args.output.write_text(json.dumps({"verdict": verdict, "go": go, "rust": rust}, indent=2, sort_keys=True) + "\n")
    print(json.dumps(verdict, indent=2))
    raise SystemExit(0 if verdict["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
