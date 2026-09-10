#!/usr/bin/env python3
"""Capture/check the locked-migration fixture against the pinned production Go.

From the repository root, supply isolated internal scratch and external build
roots, e.g. --scratch-root .github/audit/sqlite-negative --build-root target/oracle.
--check compares all state exactly; raw driver wording and measured durations
remain diagnostics. Each real wait must independently pass the existing bounds.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import generate


def capture(scratch, builds):
    source = generate.source_snapshot()
    helpers = generate.helper_snapshot()
    with tempfile.TemporaryDirectory(dir=scratch) as tmp, tempfile.TemporaryDirectory(dir=builds) as build:
        root, build = Path(tmp), Path(build)
        oracle = root / "source"
        for rel, data in {**source, **helpers}.items():
            path = oracle / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        env = generate.isolated_env(root)
        env["GOCACHE"] = str(build / "cache")
        env["GOTMPDIR"] = str(build / "tmp")
        Path(env["GOTMPDIR"]).mkdir()
        helper = oracle / "scripts/rust-port/sqlite"
        modules = generate.json_stream(generate.run(["go", "list", "-m", "-json", "all"], cwd=helper, env=env))
        pinned = generate.json_stream(generate.run(["go", "list", "-m", "-json", "all"], cwd=oracle, env=env))
        versions = {m["Path"]: m.get("Version", "") for m in pinned}
        for module in modules:
            if module.get("Main"):
                continue
            if module["Path"] == generate.MODULE:
                assert Path(module["Replace"]["Dir"]).resolve() == oracle.resolve()
            else:
                assert "Replace" not in module and module.get("Version", "") == versions[module["Path"]]
        binary = build / ("locked-migration.exe" if os.name == "nt" else "locked-migration")
        generate.run(["go", "build", "-trimpath", "-o", str(binary), "./testdata/locked-migration"], cwd=helper, env=env, timeout=300)
        report = json.loads(generate.run([str(binary), str(root)], cwd=helper, env=env, timeout=20))
        assert report["go_version"] == generate.TOOLCHAIN
        for case in report["cases"]:
            assert 4.0 <= case["busy_seconds"] <= 6.0, case
            assert 0 <= case["rollback_seconds"] <= 1.0, case
        assert len(report["cases"]) == 2
        report["oracle_commit"] = generate.ORACLE_COMMIT
        report["source_hashes"] = {p: generate.sha(b) for p, b in source.items()}
        report["helper_hashes"] = {p: generate.sha(b) for p, b in helpers.items()}
    assert generate.helper_snapshot() == helpers, "helper changed during capture"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch-root", required=True, type=Path)
    parser.add_argument("--build-root", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path in (args.scratch_root, args.build_root):
        path.mkdir(parents=True, exist_ok=True)
    report = capture(args.scratch_root.resolve(), args.build_root.resolve())
    fixture = HERE / "observed.json"
    if args.check:
        expected = json.loads(fixture.read_text())
        for key in ("oracle_commit", "source_hashes", "helper_hashes"):
            assert report[key] == expected[key], f"{key} drift"
        assert [c["state"] for c in report["cases"]] == [c["state"] for c in expected["cases"]], "locked migration state drift"
    else:
        fixture.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"cases": 2, "check": args.check, "observed": report["cases"]}, sort_keys=True))


if __name__ == "__main__":
    main()
