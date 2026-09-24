#!/usr/bin/env python3
"""Compare two prebuilt domkit test binaries serially; retain every sample."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path, help="new directory for raw logs and summary")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    binaries = {"baseline": args.baseline.resolve(), "candidate": args.candidate.resolve()}
    flags = ["-test.run=^$", "-test.bench=Benchmark(Truncate|RenderTruncated|RenderParseOnce)$",
             "-test.benchmem", "-test.benchtime=100ms", "-test.cpu=1", "-test.count=1"]
    env = dict(os.environ, GOMAXPROCS="1")
    pattern = re.compile(r"^(Benchmark\S+)\s+\d+\s+([\d.]+) ns/op(?:\s+[\d.]+ MB/s)?\s+(\d+) B/op\s+(\d+) allocs/op$", re.M)
    samples = {label: {} for label in binaries}
    expected_names = None
    manifest = {"sha256": {label: hashlib.sha256(binary.read_bytes()).hexdigest()
                           for label, binary in binaries.items()}, "flags": flags, "order": []}
    for run in range(11):
        order = ["baseline", "candidate"] if run % 2 == 0 else ["candidate", "baseline"]
        for label in order:
            phase = "warmup" if run == 0 else f"run-{run:02d}"
            name = f"{phase}-{label}"
            result = subprocess.run([str(binaries[label]), *flags], env=env,
                                    capture_output=True, text=True, timeout=120, check=True)
            (args.output / f"{name}.txt").write_text(result.stdout + result.stderr)
            rows = pattern.findall(result.stdout)
            names = {row[0] for row in rows}
            if expected_names is None:
                expected_names = names
            if len(rows) != 10 or names != expected_names or "PASS" not in result.stdout:
                raise RuntimeError(f"incomplete benchmark output: {name}")
            manifest["order"].append(name)
            (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            if run:
                for benchmark, ns, allocated, allocs in rows:
                    samples[label].setdefault(benchmark, []).append(
                        [float(ns), int(allocated), int(allocs)])
            print(name, "OK", flush=True)
    assert expected_names is not None
    summary = {}
    for name in sorted(expected_names):
        entry = {}
        for label in binaries:
            rows = samples[label][name]
            assert len(rows) == 10
            entry[label] = {metric: {"median": statistics.median(values),
                                     "min": min(values), "max": max(values)}
                            for metric, values in zip(["ns/op", "B/op", "allocs/op"], zip(*rows))}
        before = entry["baseline"]["ns/op"]["median"]
        after = entry["candidate"]["ns/op"]["median"]
        entry["latency_reduction_percent"] = (before - after) / before * 100
        summary[name] = entry
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
