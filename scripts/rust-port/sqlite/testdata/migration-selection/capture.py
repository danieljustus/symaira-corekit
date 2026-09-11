#!/usr/bin/env python3
"""Generate/check one migration-selection fixture from the pinned Go source."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import generate

CASE_IDS = ["SQL-003/migration-selection"]


def validate(report):
    if report["go_version"] != generate.TOOLCHAIN:
        raise ValueError("wrong Go runtime")
    if report["case_ids"] != CASE_IDS or [c["id"] for c in report["cases"]] != CASE_IDS:
        raise ValueError("declared/executed case IDs differ")


def compare(expected, actual):
    validate(expected)
    validate(actual)
    # Exact JSON scalar types, string contents and array order; no normalizers.
    if json.dumps(expected, sort_keys=True) != json.dumps(actual, sort_keys=True):
        raise ValueError("migration-selection fixture/source drift")


def capture(scratch, build, evidence):
    source = generate.source_snapshot()
    tests = generate.run(["git", "ls-tree", "-r", "--name-only", generate.ORACLE_COMMIT,
                          "sqlitekit"], cwd=generate.ROOT).decode().splitlines()
    tests = {p: generate.git_bytes(p) for p in tests
             if p.endswith("_test.go") or "/testdata/" in p}
    paths = [HERE / name for name in ("main.go", "cases.json", "capture.py", "test_capture.py")]
    paths += [generate.HELPER / name for name in ("go.mod", "go.sum", "generate.py")]
    helpers = {p.relative_to(generate.ROOT).as_posix(): p.read_bytes() for p in paths}
    with tempfile.TemporaryDirectory(dir=scratch) as name:
        root = Path(name)
        oracle = root / "source"
        for rel, data in {**source, **tests, **helpers}.items():
            path = oracle / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        env = generate.isolated_env(root)
        env.update(GOCACHE=str(build / "cache"), GOTMPDIR=str(build / "tmp"))
        Path(env["GOTMPDIR"]).mkdir(parents=True, exist_ok=True)
        helper = oracle / "scripts/rust-port/sqlite"

        def run(label, command, cwd=helper):
            raw = generate.run(command, cwd=cwd, env=env, timeout=300)
            (evidence / (label + ".stdout")).write_bytes(raw)
            (evidence / (label + ".command.json")).write_text(json.dumps({
                "argv": command, "cwd": str(cwd), "exit_code": 0,
                "env": env}, indent=2) + "\n")
            return raw

        if run("toolchain", ["go", "env", "GOVERSION"]).decode().strip() != generate.TOOLCHAIN:
            raise ValueError("wrong Go compiler")
        pinned = generate.json_stream(run("pinned-modules", ["go", "list", "-m", "-json", "all"], oracle))
        modules = generate.json_stream(run("helper-modules", ["go", "list", "-m", "-json", "all"]))
        versions = {m["Path"]: m.get("Version", "") for m in pinned}
        dependencies = {}
        for module in modules:
            if module.get("Main"):
                continue
            if module["Path"] == generate.MODULE:
                if Path(module["Replace"]["Dir"]).resolve() != oracle.resolve():
                    raise ValueError("oracle module escaped pinned source")
            else:
                if "Replace" in module or module.get("Version", "") != versions[module["Path"]]:
                    raise ValueError("oracle dependency drift")
                dependencies[module["Path"]] = {k: module[k] for k in ("Version", "Sum", "GoModSum") if k in module}
        packages = generate.json_stream(run("packages", ["go", "list", "-deps", "-json", "./testdata/migration-selection"]))
        for package in packages:
            if package["ImportPath"].startswith(generate.MODULE + "/"):
                if not Path(package["Dir"]).resolve().is_relative_to(oracle.resolve()):
                    raise ValueError("oracle package escaped pinned source")
        test_events = [json.loads(line) for line in run("go-tests", ["go", "test", "-json", "-count=1", "./sqlitekit", "-run", "^TestMigrate$"], oracle).splitlines()]
        passed = [e["Test"] for e in test_events if e["Action"] == "pass" and "Test" in e]
        if passed != ["TestMigrate"]:
            raise ValueError("pinned Go test count/name mismatch")
        binary = build / ("migration-selection.exe" if os.name == "nt" else "migration-selection")
        run("build", ["go", "build", "-trimpath", "-o", str(binary), "./testdata/migration-selection"])
        manifest = helper / "testdata/migration-selection/cases.json"
        report = json.loads(run("observation", [str(binary), str(manifest)]))
        report.update(case_ids=json.loads(manifest.read_bytes())["case_ids"],
                      oracle_commit=generate.ORACLE_COMMIT,
                      source_hashes={p: generate.sha(b) for p, b in source.items()},
                      oracle_test_hashes={p: generate.sha(b) for p, b in tests.items()},
                      helper_hashes={p: generate.sha(b) for p, b in helpers.items()},
                      dependencies=dependencies)
        validate(report)
        if any((generate.ROOT / p).read_bytes() != b for p, b in helpers.items()):
            raise ValueError("helper changed during capture")
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch-root", required=True, type=Path)
    parser.add_argument("--build-root", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path in (args.scratch_root, args.build_root, args.evidence_root):
        path.mkdir(parents=True, exist_ok=True)
    report = capture(args.scratch_root.resolve(), args.build_root.resolve(), args.evidence_root.resolve())
    fixture = HERE / "observed.json"
    if args.check:
        compare(json.loads(fixture.read_bytes()), report)
    else:
        fixture.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "passed", "check": args.check, "go_tests_executed": 1,
                      "declared_case_ids": CASE_IDS, "executed_case_ids": [c["id"] for c in report["cases"]]}))


if __name__ == "__main__":
    main()
