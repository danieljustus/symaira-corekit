#!/usr/bin/env python3
"""Capture the remaining native Go update observations without changing history.

Capture is explicitly opt-in. Registration and Rust acceptance are separate.
The existing bounded capture machinery supplies private roots and complete Go
compiler/module/source inventories; this producer never promotes its own bytes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

import static_update_oracle as original

ROOT = Path(__file__).resolve().parents[2]
LANES = {
    "request": ("update-request-oracle", 13, ("updatecheck/updatecheck.go",), "requests.json"),
    "cache": ("update-cache-oracle", 7, ("updatecheck/updatecheck.go",), "cache.json"),
    "persistence": ("update-cache-persistence-oracle", 7, ("updatecheck/updatecheck.go",), "cache.json"),
    "cosign": ("cosign-contract-oracle", 13, ("updatecheck/cosign/cosign.go",), "cosign.json"),
    "apply": ("update-apply-oracle", 17, ("updatecheck/updateapply/updateapply.go", "updatecheck/extract/extract.go"), "apply.json"),
    "cancellation": ("update-cancellation-oracle", 16, ("updatecheck/updatecheck.go",), "cancellation.json"),
}


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def legacy_observations(lane, result, goos):
    oracle, _, sources, _ = LANES[lane]
    if lane in ("persistence", "cancellation"):
        return result
    hashes = {
        "go_source_sha256": original.sha256(b"\0".join((ROOT / p).read_bytes() for p in sources)),
        "oracle_sha256": original.sha256((ROOT / f"scripts/rust-port/{oracle}/main.go").read_bytes()),
    }
    if lane in ("request", "apply"):
        return dict(hashes, goos=goos, cases=result)
    return dict(result, **hashes)


def capture(lane, destination):
    oracle, count, sources, legacy = LANES[lane]
    destination.mkdir(parents=True, exist_ok=False)
    original.LANES[lane] = {"source": sources, "oracle": (f"scripts/rust-port/{oracle}/main.go",), "legacy": legacy}
    with tempfile.TemporaryDirectory(prefix=f"native-update-{lane}-") as scratch:
        env, version, goroot, goos, goarch, _, compiler = original._prepare_go_env(Path(scratch), destination)
        previous_umask = os.umask(0o022) if os.name == "posix" else None
        try:
            before = original._capture_inputs(lane, compiler, env, destination)
            if not before["working_tree_clean"]:
                raise ValueError("native capture requires a clean committed checkout")
            producer = {"path": "repository/scripts/rust-port/native_update_capture.py", "sha256": original.sha256(Path(__file__).read_bytes())}
            result = original._run([str(compiler), "run", f"./scripts/rust-port/{oracle}"], env, ROOT, "native-go-observation", destination)
            (destination / "observation.stdout").write_bytes(result["stdout"])
            (destination / "observation.stderr").write_bytes(result["stderr"])
            if result["exit_code"]:
                raise RuntimeError(f"native {lane} failed with exit {result['exit_code']}")
            raw = json.loads(result["stdout"])
            cases = raw if isinstance(raw, list) else raw["cases"]
            ids = [row["input"]["id"] if lane == "apply" else row["id"] for row in cases]
            if len(cases) != count or len(set(ids)) != count:
                raise ValueError(f"native {lane} case inventory differs from {count}")
            if isinstance(raw, dict) and "goos" in raw and raw["goos"] != goos:
                raise ValueError("native observation platform mismatch")
            if original._capture_inputs(lane, compiler, env, destination) != before or original.sha256(Path(__file__).read_bytes()) != producer["sha256"]:
                raise ValueError("native capture inputs changed during execution")
            capture_record = {
                "schema_version": 1, "lane": lane, **before,
                "capture_mode": "native-go-update-original-v1",
                "go": {"version": version, "goversion": "go1.26.6", "goos": goos, "goarch": goarch, "goroot": Path(goroot).name},
                "producer": producer, "case_count": count, "case_ids": ids,
                "case_fingerprints_sha256": [original.sha256(original.canonical_json(row)) for row in cases],
                "raw": {"exit_code": result["exit_code"], "stdout_sha256": original.sha256(result["stdout"]), "stderr_sha256": original.sha256(result["stderr"])},
            }
            payload = {"observations": legacy_observations(lane, raw, goos), "capture": capture_record}
            (destination / f"{lane}.json").write_bytes(encode(payload))
            print(f"PASS original {goos}/{goarch} {lane}: {count} source-bound observations", flush=True)
        finally:
            if previous_umask is not None:
                os.umask(previous_umask)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("GO_ORACLE") != "1":
        raise RuntimeError("native Go capture requires explicit GO_ORACLE=1")
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("raw capture must be outside the source checkout")
    for lane in LANES:
        capture(lane, output / lane)


if __name__ == "__main__":
    main()
