"""Byte-preserving Go captures for the MCP and MCP-config process corpora.

Only explicit GO_ORACLE=1 capture/check mode invokes Go. Frozen mode always
executes the current Rust fixture binary; stored output is only the expected
side. Native captures are additive and pinned in frozen_process_anchors.py.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import subprocess
import sys
import tempfile
import threading
import time


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def native_os() -> str:
    return {"darwin": "darwin", "linux": "linux", "win32": "windows"}[sys.platform]


def serial_line_exchange(binary: Path, stdin: bytes, env: dict, timeout: int):
    """Same-process panic recovery, with bounded request/response readiness.

    ponytail: only the owned MCP line fixture uses this exchange. Add a framed
    decoder and descendant cleanup before widening it to arbitrary processes.
    """
    deadline = time.monotonic() + timeout
    replies = queue.Queue()
    output = bytearray()
    reader_errors = []
    limit = 2 * 1024 * 1024
    with tempfile.TemporaryFile() as errors, subprocess.Popen(
        [str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=errors, env=env,
    ) as process:
        source, sink = process.stdout, process.stdin
        assert source is not None and sink is not None
        def read_replies():
            try:
                while line := source.readline(limit + 1):
                    if len(output) + len(line) > limit:
                        raise ValueError("MCP exchange stdout exceeds its capture bound")
                    output.extend(line)
                    replies.put(line)
                replies.put(None)
            except Exception as error:
                reader_errors.append(error)
                replies.put(error)
        reader = threading.Thread(target=read_replies, daemon=True)
        reader.start()
        try:
            for line in stdin.splitlines(keepends=True):
                sink.write(line)
                sink.flush()
                reply = replies.get(timeout=max(0.001, deadline - time.monotonic()))
                if isinstance(reply, Exception):
                    raise reply
                if reply is None:
                    raise ValueError("MCP process ended before its next response")
            sink.close()
            code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            reader.join(timeout=1)
            if reader.is_alive():
                raise ValueError("MCP exchange stdout did not reach EOF")
            if reader_errors:
                raise reader_errors[0]
            errors.seek(0)
            stderr = errors.read(limit + 1)
            if len(stderr) > limit:
                raise ValueError("MCP exchange stderr exceeds its capture bound")
            return code, bytes(output), stderr
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            reader.join(timeout=1)


def provenance(runner: Path, helper: Path, cases_path: Path, oracle_commit: str) -> dict:
    return {
        "oracle_commit": oracle_commit,
        "cases_sha256": sha256(cases_path.read_bytes()),
        "generator_sha256": sha256(runner.read_bytes()),
        "capture_helper_sha256": sha256(Path(__file__).read_bytes()),
    }


def capture(runner, helper, cases_path, oracle_commit, cases, payloads, build_go, run):
    if not cases or len(cases) != len(payloads) or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("capture inputs must have unique IDs and complete payloads")
    env = dict(os.environ, GOTOOLCHAIN="go1.26.6", CGO_ENABLED="0")
    version = subprocess.check_output(["go", "version"], env=env, text=True).strip()
    if not version.startswith("go version go1.26.6 "):
        raise ValueError(f"unexpected Go toolchain: {version}")
    tree = subprocess.check_output(
        ["git", "rev-parse", f"{oracle_commit}^{{tree}}"],
        cwd=runner.resolve().parents[2], text=True,
    ).strip()
    with tempfile.TemporaryDirectory(prefix="corekit-frozen oracle path-") as raw:
        go = build_go(Path(raw))
        observations = [run(go, payload, case) for case, payload in zip(cases, payloads)]
        artifact_sha = sha256(go.read_bytes())
    return {
        "schema_version": 1,
        "provenance": dict(
            provenance(runner, helper, cases_path, oracle_commit),
            oracle_helper_sha256=sha256(helper.read_bytes()),
            go_version=version, oracle_tree=tree, go_binary_sha256=artifact_sha,
            goos=native_os(), architecture=platform.machine(),
        ),
        "case_count": len(cases),
        "cases": [
            {"id": case["id"], "stdin_sha256": sha256(payload), "exit_code": result[0],
             "stdout_base64": base64.b64encode(result[1]).decode("ascii"),
             "stderr_base64": base64.b64encode(result[2]).decode("ascii")}
            for case, payload, result in zip(cases, payloads, observations)
        ],
    }


def load_capture(path, expected_sha, runner, helper, cases_path, oracle_commit, cases, payloads):
    raw = path.read_bytes()
    if sha256(raw) != expected_sha:
        raise ValueError("frozen capture integrity mismatch")
    document = json.loads(raw)
    if document["schema_version"] != 1 or document["case_count"] != len(cases):
        raise ValueError("frozen capture schema/count mismatch")
    observed = document["provenance"]
    # The trusted whole-capture digest binds the original Go helper and tree.
    # Frozen replay must also work after the Go helper/source is retired.
    for key, value in provenance(runner, helper, cases_path, oracle_commit).items():
        if observed.get(key) != value:
            raise ValueError(f"frozen capture provenance mismatch: {key}")
    if observed["goos"] != native_os() or not observed["go_version"].startswith("go version go1.26.6 "):
        raise ValueError("frozen capture native platform/toolchain mismatch")
    rows = document["cases"]
    ids = [case["id"] for case in cases]
    if not ids or len(ids) != len(payloads) or len(ids) != len(set(ids)) or [row["id"] for row in rows] != ids:
        raise ValueError("frozen capture case identity/order mismatch")
    results = []
    for row, payload in zip(rows, payloads):
        if row["stdin_sha256"] != sha256(payload) or type(row["exit_code"]) is not int:
            raise ValueError(f"frozen capture input/exit mismatch: {row['id']}")
        results.append((row["exit_code"], base64.b64decode(row["stdout_base64"], validate=True),
                        base64.b64decode(row["stderr_base64"], validate=True)))
    return results


def mismatch(expected, actual, case):
    if expected[:2] != actual[:2]:
        return "exit/stdout differs"
    policy = case.get("stderr", "exact")
    if policy == "nonempty":
        if not expected[2] or not actual[2]:
            return "expected diagnostics on stderr"
        if b"\x00" in expected[2] or b"\x00" in actual[2]:
            return "stderr contains NUL"
    elif policy != "ignore" and expected[2] != actual[2]:
        return "stderr differs"
    if b"\x00" in actual[1]:
        return "stdout contains NUL"
    return None


def check(runner, helper, cases_path, oracle_commit, cases, payloads, build_go, run,
          rust, args):
    if os.environ.get("GO_ORACLE") not in (None, "", "0", "1"):
        raise ValueError("GO_ORACLE must be 0 or 1")
    live = os.environ.get("GO_ORACLE") == "1"
    if args.capture:
        if not live:
            raise ValueError("capturing Go observations requires GO_ORACLE=1")
        document = capture(runner, helper, cases_path, oracle_commit, cases, payloads, build_go, run)
        # Exclusive create prevents a recapture from overwriting accepted history.
        with args.capture.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
        print(f"CAPTURE {runner.stem}: {len(cases)} cases -> {args.capture}")
        return 0
    from frozen_process_anchors import ANCHORS
    key = f"{runner.stem}:{native_os()}"
    if key not in ANCHORS:
        raise ValueError(f"missing reviewed native capture: {key}")
    fixture = args.fixture or cases_path.parent / "fixtures" / f"{runner.stem}-{native_os()}.json"
    expected = load_capture(fixture, ANCHORS[key], runner, helper, cases_path, oracle_commit, cases, payloads)
    if live:
        document = capture(runner, helper, cases_path, oracle_commit, cases, payloads, build_go, run)
        for case, row, accepted in zip(cases, document["cases"], expected):
            observed = (row["exit_code"], base64.b64decode(row["stdout_base64"]), base64.b64decode(row["stderr_base64"]))
            error = mismatch(accepted, observed, case)
            if error:
                raise ValueError(f"fresh Go versus frozen capture {case['id']}: {error}")
    subprocess.run(["cargo", "build", "-p", args.rust_package, "--bin", args.rust_bin, "--locked",
                    "--target-dir", str(rust.parent.parent)],
                   cwd=runner.resolve().parents[2], check=True)
    actual = [run(rust, payload, case) for case, payload in zip(cases, payloads)]
    for case, accepted, observed in zip(cases, expected, actual):
        error = mismatch(accepted, observed, case)
        if error:
            print(f"FAIL {case['id']}: {error}", file=sys.stderr)
            return 1
        print(f"PASS {case['id']}")
    # Replay a changed expected stdout against actual Rust execution. This is
    # separate from digest corruption and cannot pass by comparing JSON to JSON.
    mutated = (expected[0][0], expected[0][1] + b"mutation", expected[0][2])
    if mismatch(mutated, actual[0], cases[0]) != "exit/stdout differs":
        raise ValueError("frozen expected stdout mutation was not rejected by Rust comparison")
    print(f"PASS negative control {cases[0]['id']}: exit/stdout differs")
    print(f"PASS {runner.stem} ({len(cases)} executed Rust cases; {'live Go+frozen' if live else 'frozen Go'} expected)")
    return 0
