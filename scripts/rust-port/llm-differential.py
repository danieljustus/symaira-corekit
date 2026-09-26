#!/usr/bin/env python3
"""Compare the Rust LLM contracts with recordings made by Go llmkit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "testdata/rust-port/fixtures/llm/go-oracle.json"
ORACLE = ["go", "run", "./scripts/rust-port/llm-oracle"]
SOURCE_DIRS = ("llmkit", "secretref", "exitcodes")
ORACLE_SOURCE = ROOT / "scripts/rust-port/llm-oracle/main.go"
RUNNER_SOURCE = Path(__file__)


def source_digest() -> str:
    digest = hashlib.sha256()
    for directory in SOURCE_DIRS:
        for path in sorted((ROOT / directory).glob("*.go")):
            if path.name.endswith("_test.go"):
                continue
            relative = path.relative_to(ROOT).as_posix().encode()
            content = path.read_bytes()
            digest.update(len(relative).to_bytes(4, "big"))
            digest.update(relative)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
    return digest.hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def oracle_command() -> list[str]:
    launcher = Path.home() / ".local/bin/dev-external"
    if launcher.is_file():
        return [str(launcher), *ORACLE]
    return ORACLE


def compare(observed: dict, expected: dict) -> None:
    if observed != expected:
        raise ValueError("Go oracle output differs from the committed LLM contract fixture")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="replace the fixture from the current Go implementation")
    args = parser.parse_args()

    env = os.environ.copy()
    env["GOTOOLCHAIN"] = "go1.26.6"
    result = subprocess.run(oracle_command(), cwd=ROOT, env=env, check=True, capture_output=True, text=True)
    observed = json.loads(result.stdout)
    observed["provenance"] = {
        "go_source_sha256": source_digest(),
        "oracle_sha256": file_digest(ORACLE_SOURCE),
        "runner_sha256": file_digest(RUNNER_SOURCE),
        "oracle_command": "GOTOOLCHAIN=go1.26.6 go run ./scripts/rust-port/llm-oracle",
    }
    serialized = json.dumps(observed, indent=2, sort_keys=True) + "\n"
    if args.write:
        FIXTURE.write_text(serialized, encoding="utf-8")
        print(f"WROTE {FIXTURE.relative_to(ROOT)}")
        return 0

    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    altered = json.loads(json.dumps(observed))
    altered["rate_limit"]["code"] = "provider_error"
    try:
        compare(observed, altered)
    except ValueError:
        pass
    else:
        raise ValueError("negative control was not rejected")
    compare(observed, expected)
    print("PASS Go/Rust LLM fixture provenance, provider registry, dialect requests, Ollama calls and error taxonomy")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        raise SystemExit(1)
