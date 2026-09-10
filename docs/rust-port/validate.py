#!/usr/bin/env python3
"""Validate the CoreKit Rust-migration handoff with stdlib only."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import NoReturn

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
ORACLE_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[A-Z]+-[0-9]{3}$")


def load(name: str):
    with (ROOT / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def integrity_digest(path: Path) -> str:
    """Hash tracked text independent of Git's platform EOL checkout."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def validate_gate_benchmark_binding(metrics: object, smokes: object, benchmark: dict) -> None:
    benchmark_metrics = [
        {
            "repository": entry.get("repository"),
            "workload": entry.get("workload"),
            "baseline_commit": entry.get("baseline_commit"),
            "candidate_commit": entry.get("candidate_commit"),
            "runs": entry.get("runs"),
            "maximum_regression_ratio": entry.get("maximum_regression_ratio"),
        }
        for entry in benchmark.get("measurements", [])
        if isinstance(entry, dict)
    ]
    if metrics != benchmark_metrics:
        fail("value-gate: consumer metrics differ from integrity-bound benchmark evidence")
    benchmark_smokes = [
        {"repository": entry.get("repository"), "passed": entry.get("passed")}
        for entry in benchmark.get("standalone_smokes", [])
        if isinstance(entry, dict)
    ]
    if smokes != benchmark_smokes:
        fail("value-gate: standalone smokes differ from integrity-bound benchmark evidence")


def validate_integrity(value_gate: dict) -> None:
    integrity = value_gate.get("integrity")
    if not isinstance(integrity, dict) or not isinstance(integrity.get("files"), list) or not integrity["files"]:
        fail("value-gate: independently validated integrity manifest is required")
    seen: set[str] = set()
    for entry in integrity["files"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not (isinstance(entry.get("sha256"), str) or entry.get("sha256") is None):
            fail("value-gate: malformed integrity entry")
        relative = PurePosixPath(entry["path"])
        if relative.is_absolute() or ".." in relative.parts or entry["path"] in seen:
            fail("value-gate: integrity path must be unique, relative and non-traversing")
        seen.add(entry["path"])
        path = (REPO / Path(*relative.parts)).resolve()
        try:
            path.relative_to(REPO.resolve())
        except ValueError:
            fail("value-gate: integrity path escapes repository")
        if entry.get("sha256") is None:
            if value_gate.get("status") == "pending" and entry["path"] == "testdata/rust-port/benchmarks/foundation.json":
                continue
            fail(f"value-gate: missing integrity digest for {entry['path']}")
        if not path.is_file() or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            fail(f"value-gate: invalid or missing integrity file {entry['path']}")
        if integrity_digest(path) != entry["sha256"]:
            fail(f"value-gate: digest mismatch for {entry['path']}")
    required = {
        "testdata/rust-port/benchmarks/foundation.json",
        "testdata/rust-port/adoption/evidence.json",
        "testdata/rust-port/cases/consumer-canaries.json",
        "scripts/rust-port/adoption.py",
        "scripts/rust-port/bench.py",
    }
    if not required.issubset(seen):
        fail(f"value-gate: integrity manifest is missing {sorted(required - seen)}")


def unique_ids(items: list[dict], label: str) -> set[str]:
    raw = [item.get("id") for item in items]
    if any(not isinstance(value, str) or not ID_RE.fullmatch(value) for value in raw):
        fail(f"{label}: every id must match {ID_RE.pattern}")
    if len(raw) != len(set(raw)):
        fail(f"{label}: duplicate ids")
    return {value for value in raw if isinstance(value, str)}


def visit(node: str, deps: dict[str, list[str]], active: set[str], done: set[str]) -> None:
    if node in active:
        fail(f"work-items: dependency cycle at {node}")
    if node in done:
        return
    active.add(node)
    for dep in deps[node]:
        visit(dep, deps, active, done)
    active.remove(node)
    done.add(node)


def ancestors(node: str, deps: dict[str, list[str]]) -> set[str]:
    result: set[str] = set()
    stack = list(deps[node])
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(deps[current])
    return result


def validate_links() -> None:
    pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    for path in ROOT.glob("*.md"):
        for target in pattern.findall(path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            local = target.split("#", 1)[0]
            if local and not (path.parent / local).exists():
                fail(f"{path.name}: missing local link {target}")


def oracle_digest(commit: str) -> tuple[str, int]:
    output = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", commit],
        cwd=REPO,
        text=True,
    )

    def owned(path: str) -> bool:
        if path.endswith(".go") and not path.endswith("_test.go"):
            return True
        if path.startswith("contracts/") and path.endswith(".json"):
            return True
        return "/testdata/" in path and path.endswith((".json", ".sql"))

    paths = sorted(path for path in output.splitlines() if owned(path))
    digest = hashlib.sha256()
    for path in paths:
        content = subprocess.check_output(
            ["git", "show", f"{commit}:{path}"],
            cwd=REPO,
        )
        digest.update(path.encode("utf-8") + b"\0" + content + b"\0")
    return digest.hexdigest(), len(paths)


def oracle_package_paths(commit: str) -> set[str]:
    tracked = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", commit],
        cwd=REPO,
        text=True,
    ).splitlines()
    return {
        str(PurePosixPath(path).parent)
        for path in tracked
        if path.endswith(".go") and not path.endswith("_test.go")
    }


def validate_consumer_demand(baseline: dict, commit: str) -> None:
    demand = baseline.get("consumer_demand")
    snapshots = baseline.get("consumer_snapshots")
    if not isinstance(demand, list) or not demand:
        fail("baseline: consumer_demand must be a non-empty array")
    if not isinstance(snapshots, list) or not snapshots:
        fail("baseline: consumer_snapshots must be a non-empty array")

    snapshot_by_repo: dict[str, dict] = {}
    for snapshot in snapshots:
        repo = snapshot.get("repo")
        revision = snapshot.get("commit")
        imports = snapshot.get("tracked_head_go_import_files")
        if not isinstance(repo, str) or not repo or repo in snapshot_by_repo:
            fail("baseline: consumer snapshot repos must be unique non-empty strings")
        if not isinstance(revision, str) or not ORACLE_RE.fullmatch(revision):
            fail(f"baseline: {repo} snapshot needs a 40-hex commit")
        if not isinstance(snapshot.get("branch"), str) or not isinstance(
            snapshot.get("dirty_worktree_at_capture"), bool
        ):
            fail(f"baseline: {repo} snapshot needs branch and dirty state")
        if not isinstance(imports, dict) or any(
            not isinstance(name, str) or not isinstance(count, int) or count < 0
            for name, count in imports.items()
        ):
            fail(f"baseline: {repo} has invalid tracked import counts")
        snapshot_by_repo[repo] = snapshot

    available_packages = oracle_package_paths(commit)
    families = [row.get("package_family") for row in demand]
    if any(not isinstance(name, str) or not name for name in families):
        fail("baseline: every demand row needs a package_family")
    if len(families) != len(set(families)):
        fail("baseline: duplicate consumer-demand package_family")
    for row in demand:
        family = row["package_family"]
        paths = row.get("package_paths")
        if not isinstance(paths, list) or not paths or any(
            not isinstance(path, str) or path not in available_packages for path in paths
        ):
            fail(f"baseline: {family} contains an invalid package path")
        if any(path.split("/", 1)[0] != family for path in paths):
            fail(f"baseline: {family} package path escapes its family")
        expected_consumers = sorted(
            repo
            for repo, snapshot in snapshot_by_repo.items()
            if snapshot["tracked_head_go_import_files"].get(family, 0) > 0
        )
        if sorted(row.get("consumers", [])) != expected_consumers:
            fail(f"baseline: {family} consumer list differs from pinned snapshots")
        expected_files = sum(
            snapshot["tracked_head_go_import_files"].get(family, 0)
            for snapshot in snapshots
        )
        if row.get("go_files") != expected_files:
            fail(f"baseline: {family} file count differs from pinned snapshots")


def validate_go_oracles(commit: str, contracts: list[dict]) -> int:
    tracked = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", commit],
        cwd=REPO,
        text=True,
    ).splitlines()
    test_names: dict[str, set[str]] = {}
    function_pattern = re.compile(
        rb"^func\s+((?:Test|Example|Fuzz|Benchmark)[A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    )
    for path in tracked:
        if not path.endswith("_test.go"):
            continue
        content = subprocess.check_output(
            ["git", "show", f"{commit}:{path}"],
            cwd=REPO,
        )
        parent = str(PurePosixPath(path).parent)
        package = "." if parent == "." else f"./{parent}"
        names = {match.decode("ascii") for match in function_pattern.findall(content)}
        test_names.setdefault(package, set()).update(names)

    checked = 0
    for row in contracts:
        command = row["go_oracle"]
        if " go test " not in command or " -run " not in command:
            continue
        tokens = shlex.split(command)
        try:
            test_index = tokens.index("test", tokens.index("go") + 1)
            run_index = tokens.index("-run", test_index + 1)
        except ValueError:
            fail(f"{row['id']}: cannot parse go test -run oracle")
        pattern = tokens[run_index + 1]
        packages = [
            token for token in tokens[test_index + 1 : run_index]
            if token.startswith("./")
        ]
        if not packages:
            packages = [
                token for token in tokens[run_index + 2 :]
                if token.startswith("./")
            ]
        try:
            compiled = re.compile(pattern)
        except re.error as error:
            fail(f"{row['id']}: invalid -run regex {pattern!r}: {error}")
        for package in packages:
            checked += 1
            if not any(compiled.search(name) for name in test_names.get(package, set())):
                fail(f"{row['id']}: -run {pattern!r} matches no test in {package}")
    return checked


def validate_rust001_artifacts(baseline: dict) -> None:
    fixture_root = REPO / "testdata" / "rust-port" / "fixtures"
    case_root = REPO / "testdata" / "rust-port" / "cases"
    required = [
        REPO / "scripts" / "rust-port" / "generate.py",
        REPO / "scripts" / "rust-port" / "diff.py",
        REPO / "scripts" / "rust-port" / "go-oracle" / "go.mod",
        REPO / "scripts" / "rust-port" / "go-oracle" / "go.sum",
        REPO / "scripts" / "rust-port" / "go-oracle" / "cmd" / "publicapi" / "main.go",
        REPO / "scripts" / "rust-port" / "go-oracle" / "cmd" / "probe" / "main.go",
        fixture_root / "index.json",
        fixture_root / "public-api.json",
        fixture_root / "public-api-target-overrides.json",
        fixture_root / "oracle-probe.json",
        case_root / "oracle-selftest.json",
        case_root / "consumer-canaries.json",
        REPO / "testdata" / "rust-port" / "README.md",
    ]
    missing = [str(path.relative_to(REPO)) for path in required if not path.is_file()]
    if missing:
        fail(f"RUST-001: missing artifacts {missing}")

    index = json.loads((fixture_root / "index.json").read_text(encoding="utf-8"))
    oracle = baseline["oracle"]
    if index.get("oracle", {}).get("commit") != oracle["commit"]:
        fail("RUST-001: fixture index oracle commit drift")
    if index.get("oracle", {}).get("source_digest_sha256") != oracle["tracked_input_digest_sha256"]:
        fail("RUST-001: fixture index source digest drift")
    harness = index.get("harness", {})
    harness_inputs = harness.get("input_files")
    if not isinstance(harness_inputs, list) or not harness_inputs or harness_inputs != sorted(harness_inputs):
        fail("RUST-001: harness input paths must be a non-empty sorted array")
    harness_digest = hashlib.sha256()
    for relative in harness_inputs:
        if not isinstance(relative, str):
            fail("RUST-001: invalid harness input path")
        path = REPO / relative
        if not path.is_file():
            fail(f"RUST-001: missing harness input {relative}")
        content = path.read_bytes().replace(b"\r\n", b"\n")
        harness_digest.update(relative.encode("utf-8") + b"\0" + content + b"\0")
    if harness_digest.hexdigest() != harness.get("input_digest_sha256"):
        fail("RUST-001: harness input digest drift; regenerate fixtures")
    inventory = baseline["owned_go_inventory"]
    expected_targets = [
        "darwin-amd64", "darwin-arm64", "linux-amd64",
        "linux-arm64", "windows-amd64", "windows-arm64",
    ]
    if inventory.get("public_api_snapshot_targets") != expected_targets:
        fail("RUST-001: baseline public API targets are incomplete")
    index_targets = index.get("public_api", {}).get("targets")
    if not isinstance(index_targets, dict) or sorted(index_targets) != expected_targets:
        fail("RUST-001: fixture index public API targets are incomplete")
    public_api = json.loads((fixture_root / "public-api.json").read_text(encoding="utf-8"))
    if public_api.get("oracle_commit") != oracle["commit"] or public_api.get("targets") != expected_targets:
        fail("RUST-001: canonical public API provenance or targets drift")
    canonical_packages = public_api.get("packages")
    if not isinstance(canonical_packages, list) or not canonical_packages:
        fail("RUST-001: canonical public API snapshot has no packages")
    package_paths = [package.get("path") for package in canonical_packages]
    if len(package_paths) != len(set(package_paths)) or package_paths != sorted(package_paths):
        fail("RUST-001: canonical public API packages must be unique and sorted")
    override_doc = json.loads((fixture_root / "public-api-target-overrides.json").read_text(encoding="utf-8"))
    overrides = override_doc.get("targets")
    if (
        override_doc.get("oracle_commit") != oracle["commit"]
        or override_doc.get("canonical_target") != "darwin-arm64"
        or not isinstance(overrides, dict)
        or sorted(overrides) != expected_targets
    ):
        fail("RUST-001: public API target overrides drift")
    canonical_by_path = {package["path"]: package for package in canonical_packages}
    for target_name in expected_targets:
        target_by_path = dict(canonical_by_path)
        override = overrides[target_name]
        for path in override.get("removed_packages", []):
            target_by_path.pop(path, None)
        for package in override.get("changed_packages", []):
            target_by_path[package["path"]] = package
        packages = [target_by_path[path] for path in sorted(target_by_path)]
        declarations = sum(len(package.get("declarations", [])) for package in packages)
        members = sum(
            len(declaration.get("methods", [])) + len(declaration.get("fields", []))
            for package in packages
            for declaration in package.get("declarations", [])
        )
        api_digest = hashlib.sha256(
            json.dumps(packages, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        observed = {
            "packages": len(packages),
            "exported_top_level_declarations": declarations,
            "exported_members": members,
            "exported_surface_entries": declarations + members,
            "api_digest_sha256": api_digest,
        }
        if index_targets[target_name] != observed:
            fail(f"RUST-001: {target_name} public API reconstruction differs from fixture index")
        if len(packages) != inventory.get("public_api_snapshot_packages"):
            fail(f"RUST-001: {target_name} public API package count differs from baseline")
        if declarations != inventory.get("public_api_snapshot_exported_top_level_declarations"):
            fail(f"RUST-001: {target_name} public API declaration count differs from baseline")
        if members != inventory.get("public_api_snapshot_exported_members"):
            fail(f"RUST-001: {target_name} public API member count differs from baseline")
        if declarations + members != inventory.get("public_api_snapshot_exported_surface_entries"):
            fail(f"RUST-001: {target_name} public API total surface count differs from baseline")

    contract_records = index.get("contracts")
    if not isinstance(contract_records, list) or not contract_records:
        fail("RUST-001: fixture index has no contract records")
    for record in contract_records:
        relative = record.get("path")
        if not isinstance(relative, str) or not relative.startswith("contracts/"):
            fail("RUST-001: invalid contract fixture path")
        source = REPO / relative
        fixture = fixture_root / relative
        if not source.is_file() or not fixture.is_file():
            fail(f"RUST-001: missing contract source or fixture {relative}")
        source_bytes = source.read_bytes()
        canonical_bytes = source_bytes.replace(b"\r\n", b"\n")
        if fixture.read_bytes().replace(b"\r\n", b"\n") != canonical_bytes:
            fail(f"RUST-001: contract fixture drift {relative}")
        if hashlib.sha256(canonical_bytes).hexdigest() != record.get("sha256"):
            fail(f"RUST-001: contract digest drift {relative}")

    suite = json.loads((case_root / "oracle-selftest.json").read_text(encoding="utf-8"))
    cases = suite.get("cases")
    if not isinstance(cases, list) or len(cases) != 1:
        fail("RUST-001: oracle self-test suite must contain one foundation case")
    case = cases[0]
    required_observations = {
        "exit_or_signal", "stdout", "stderr", "returned_json_or_error",
        "recursive_file_manifest", "sqlite_snapshots", "http_transcript", "process_argv",
    }
    if set(case.get("observations", [])) != required_observations:
        fail("RUST-001: oracle case observation surface is incomplete")
    if not case.get("isolation_limits") or not case.get("env_allowlist"):
        fail("RUST-001: oracle case lacks isolation limits or env allowlist")
    stdin_fields = [field for field in ("stdin_utf8", "stdin_base64", "stdin_json") if field in case]
    if len(stdin_fields) != 1 or "stdin" in case:
        fail("RUST-001: oracle case must use exactly one explicit stdin byte representation")
    for setup in case.get("setup", []):
        content_fields = [field for field in ("content_utf8", "content_base64", "content_json") if field in setup]
        if len(content_fields) != 1 or "content" in setup:
            fail("RUST-001: setup files must use exactly one explicit byte representation")
    normalizers = case.get("normalizers")
    if not isinstance(normalizers, list) or any(
        not isinstance(item, dict) or not item.get("name") or not item.get("reason")
        for item in normalizers
    ):
        fail("RUST-001: every nondeterministic-field normalizer needs a name and reason")

    canaries = json.loads((case_root / "consumer-canaries.json").read_text(encoding="utf-8"))
    consumers = canaries.get("consumers")
    if not isinstance(consumers, list) or len({item.get("repository") for item in consumers}) < 2:
        fail("RUST-001: at least two paired-consumer canaries are required")
    for item in consumers:
        if not all(item.get(field) for field in ("snapshot_commit", "go_build", "go_run", "rust_build", "rust_run", "metrics")):
            fail("RUST-001: incomplete paired-consumer canary")


def main() -> int:
    baseline = load("baseline.json")
    matrix = load("contract-matrix.json")
    value_gate = load("value-gate.json")
    work_doc = load("work-items.json")

    for label, doc in (
        ("baseline", baseline),
        ("contract-matrix", matrix),
        ("value-gate", value_gate),
        ("work-items", work_doc),
    ):
        if doc.get("schema_version") != 1:
            fail(f"{label}: unsupported schema_version")
    validate_integrity(value_gate)

    oracle = baseline.get("oracle", {}).get("commit")
    if not isinstance(oracle, str) or not ORACLE_RE.fullmatch(oracle):
        fail("baseline: oracle commit must be 40 lowercase hex characters")
    if matrix.get("oracle_commit") != oracle or work_doc.get("oracle_commit") != oracle:
        fail("oracle commit differs across baseline, contract matrix and work items")
    digest, input_count = oracle_digest(oracle)
    oracle_doc = baseline["oracle"]
    if oracle_doc.get("tracked_input_digest_sha256") != digest:
        fail("baseline: tracked production/fixture digest does not match oracle commit")
    if oracle_doc.get("tracked_input_files") != input_count:
        fail("baseline: tracked production/fixture file count does not match oracle commit")

    validate_consumer_demand(baseline, oracle)
    validate_rust001_artifacts(baseline)

    contracts = matrix.get("contracts")
    work = work_doc.get("items")
    if not isinstance(contracts, list) or not isinstance(work, list):
        fail("contracts/items must be arrays")
    contract_ids = unique_ids(contracts, "contract-matrix")
    work_ids = unique_ids(work, "work-items")

    allowed_comparisons = {
        "api-shape", "benchmark", "bytes", "filesystem", "json-semantic",
        "manual-gate", "network", "process", "source-digest", "sqlite",
    }
    allowed_contract_status = {"todo", "fixture-ready", "parity", "accepted-difference"}
    required_contract = {
        "id", "seam", "fixture", "go_oracle", "expected", "comparison",
        "platforms", "rust_test", "status",
    }
    for row in contracts:
        missing = required_contract - row.keys()
        if missing:
            fail(f"{row.get('id')}: missing {sorted(missing)}")
        if row["comparison"] not in allowed_comparisons:
            fail(f"{row['id']}: invalid comparison {row['comparison']!r}")
        if row["status"] not in allowed_contract_status:
            fail(f"{row['id']}: invalid status {row['status']!r}")
        if not isinstance(row["platforms"], list) or not row["platforms"]:
            fail(f"{row['id']}: platforms must be a non-empty array")
        if any(value not in {"darwin", "linux", "windows"} for value in row["platforms"]):
            fail(f"{row['id']}: unsupported platform value")
        for key in ("seam", "fixture", "go_oracle", "expected", "rust_test"):
            if not isinstance(row[key], str) or not row[key].strip():
                fail(f"{row['id']}: {key} must be non-empty")
    checked_oracles = validate_go_oracles(oracle, contracts)

    deps: dict[str, list[str]] = {}
    statuses: dict[str, str] = {}
    for item in work:
        item_deps = item.get("depends_on")
        refs = item.get("contracts")
        if not isinstance(item_deps, list) or not isinstance(refs, list) or not refs:
            fail(f"{item['id']}: depends_on/contracts must be arrays and contracts non-empty")
        dangling_deps = set(item_deps) - work_ids
        dangling_refs = set(refs) - contract_ids
        if dangling_deps:
            fail(f"{item['id']}: dangling dependencies {sorted(dangling_deps)}")
        if dangling_refs:
            fail(f"{item['id']}: dangling contracts {sorted(dangling_refs)}")
        status = item.get("status")
        if status not in {"blocked", "deferred", "ready", "in_progress", "complete"}:
            fail(f"{item['id']}: invalid status {status!r}")
        if item.get("demand_class") not in {"required", "demand_driven"}:
            fail(f"{item['id']}: invalid demand_class")
        if not item.get("acceptance_commands") or not item.get("stop_rule"):
            fail(f"{item['id']}: acceptance_commands and stop_rule are required")
        deps[item["id"]] = item_deps
        statuses[item["id"]] = status

    done: set[str] = set()
    for item_id in work_ids:
        visit(item_id, deps, set(), done)

    for item_id, item_deps in deps.items():
        dependencies_complete = all(statuses[dep] == "complete" for dep in item_deps)
        if statuses[item_id] == "ready" and not dependencies_complete:
            fail(f"{item_id}: ready while a dependency is incomplete")
        if statuses[item_id] == "blocked" and dependencies_complete:
            fail(f"{item_id}: blocked despite all dependencies being complete")
        if statuses[item_id] == "deferred" and next(
            candidate for candidate in work if candidate["id"] == item_id
        )["demand_class"] != "demand_driven":
            fail(f"{item_id}: only demand-driven work may be deferred")

    ready = [item_id for item_id, status in statuses.items() if status == "ready"]
    if not any(status == "complete" for status in statuses.values()) and ready != ["RUST-001"]:
        fail(f"exactly RUST-001 must be ready at initial handoff, got {ready}")

    defect = next((row for row in contracts if row["id"] == "DEFECT-001"), None)
    if defect is None:
        fail("contract-matrix: missing DEFECT-001 update-cache contract gate")
    later_active = any(
        item_id != "RUST-001" and status in {"ready", "in_progress", "complete"}
        for item_id, status in statuses.items()
    )
    if defect["status"] != "fixture-ready" and (
        statuses["RUST-001"] == "complete" or later_active
    ):
        fail("DEFECT-001 must be corrected and fixture-ready before Rust work can start")

    covered = {contract for item in work for contract in item["contracts"]}
    missing_coverage = contract_ids - covered
    if missing_coverage:
        fail(f"contracts without work item: {sorted(missing_coverage)}")

    gate = work_doc.get("value_gate_id")
    if gate not in work_ids:
        fail("work-items: invalid value_gate_id")
    barrier = work_doc.get("barrier_applies_to")
    if not isinstance(barrier, list) or not barrier:
        fail("work-items: barrier_applies_to must be non-empty")
    for item_id in barrier:
        if item_id not in work_ids:
            fail(f"work-items: barrier references unknown {item_id}")
        if gate not in ancestors(item_id, deps):
            fail(f"{item_id}: does not depend transitively on value gate {gate}")

    if value_gate.get("gate_id") != gate:
        fail("value-gate: gate_id differs from work-items value_gate_id")
    gate_status = value_gate.get("status")
    if gate_status not in {"pending", "passed", "failed"}:
        fail("value-gate: invalid status")
    # A pending value-gate may coexist with explicit in-progress revalidation
    # rows. Only a new ready/complete downstream claim violates the barrier.
    active_downstream = any(
        statuses[item_id] in {"ready", "complete"}
        for item_id in barrier
    )
    if active_downstream and statuses[gate] != "complete":
        fail("value-gate: downstream work is active before RUST-005 is complete")
    if statuses[gate] == "complete":
        if gate_status != "passed" or value_gate.get("decision") != "continue":
            fail("value-gate: completed RUST-005 requires a passed continue decision")
        requirements = value_gate.get("requirements", {})
        evidence = value_gate.get("evidence", {})
        basis = evidence.get("basis")
        minimum = requirements.get("minimum_independent_adopters_or_languages")
        if not isinstance(minimum, int) or minimum < 2:
            fail("value-gate: invalid minimum adoption requirement")
        if basis == "rust_adoption":
            adopters = evidence.get("adopters", [])
            repos = {entry.get("repository") for entry in adopters if isinstance(entry, dict)}
            if len(repos) < minimum or any(
                not all(entry.get(key) for key in ("repository", "commit", "crate", "exact_pin"))
                for entry in adopters
            ):
                fail("value-gate: insufficient reproducible Rust adopter evidence")
        elif basis == "cross_language_ssot":
            languages = evidence.get("cross_language_ssot_languages", [])
            if len(set(languages)) < minimum:
                fail("value-gate: insufficient cross-language SSOT evidence")
        else:
            fail("value-gate: passed evidence needs a valid basis")

        duplication = evidence.get("duplication", {})
        added = duplication.get("corekit_loc_added")
        adapters = duplication.get("adapter_loc_added")
        removed = duplication.get("duplicate_loc_removed")
        if not all(isinstance(value, int) and value >= 0 for value in (added, adapters, removed)):
            fail("value-gate: duplication measurements must be non-negative integers")
        if removed < added + adapters or not duplication.get("measured_from_commits"):
            fail("value-gate: duplicate-removal rule or commit provenance failed")

        metrics = evidence.get("consumer_metrics", [])
        benchmark = json.loads((REPO / "testdata/rust-port/benchmarks/foundation.json").read_text(encoding="utf-8"))

        ceiling = requirements.get("maximum_regression_ratio")
        exception = evidence.get("security_exception")
        if not isinstance(ceiling, (int, float)) or ceiling > 1.1:
            fail("value-gate: invalid regression ceiling")
        if len(metrics) < minimum or any(
            not isinstance(entry, dict)
            or not all(entry.get(key) for key in ("repository", "workload", "baseline_commit", "candidate_commit"))
            or not isinstance(entry.get("runs"), int)
            or entry["runs"] < 10
            or not isinstance(entry.get("maximum_regression_ratio"), (int, float))
            for entry in metrics
        ):
            fail("value-gate: insufficient reproducible consumer metrics")

        if any(entry["maximum_regression_ratio"] > ceiling for entry in metrics):
            if not isinstance(exception, dict) or not exception.get("issue_url"):
                fail("value-gate: regression ceiling exceeded without tracked security exception")
        smokes = evidence.get("standalone_smokes", [])
        if len(smokes) < minimum or any(
            not isinstance(entry, dict)
            or not entry.get("repository")
            or entry.get("passed") is not True
            for entry in smokes
        ):
            fail("value-gate: standalone smoke evidence is incomplete")
        validate_gate_benchmark_binding(metrics, smokes, benchmark)

    plan = (ROOT / "implementation-plan.md").read_text(encoding="utf-8")
    for item_id in sorted(work_ids):
        if f"## {item_id}:" not in plan:
            fail(f"implementation-plan.md: missing section for {item_id}")

    validate_links()
    print(
        f"ok: {len(contract_ids)} contracts, {len(work_ids)} work items, "
        f"{checked_oracles} Go test patterns, {len(ready)} ready item(s), acyclic DAG, "
        "value barrier and links valid"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
