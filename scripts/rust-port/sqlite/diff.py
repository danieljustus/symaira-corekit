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
TARGET = ROOT / "target"


def rust_capture(manifest):
    before = candidate.snapshot()
    if before != manifest['source_hashes']:
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
        data.mkdir()
        start = int(time.time())
        raw = generate.run([str(binary), str(data), str(generate.HELPER)], cwd=data, env=env, timeout=30)
        # The only diagnostic path rewrite substitutes this run-owned root.
        report = json.loads(raw.decode().replace(str(data), "<temp-root>"))
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


def evaluate(go, rust, manifest):
    candidate.verify(rust, manifest)
    # Rust is an independent observation source. Validate its full acceptance
    # shape before comparing it with Go, so self-reported case success cannot
    # hide a missing negative, rollback, schema, or timing observation.
    generate.validate_observations(rust, require_busy_measurement=True)
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
    if candidate.snapshot() != manifest['source_hashes']:
        raise ValueError('candidate changed since explicit source freeze')
    go = generate.capture()
    rust = rust_capture(manifest)
    rust['candidate_manifest_sha256'] = manifest_sha
    try:
        verdict = evaluate(go, rust, manifest)
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
