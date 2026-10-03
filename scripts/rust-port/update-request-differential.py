#!/usr/bin/env python3
"""Generate and replay Go update-request observations against Rust."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "testdata/rust-port/fixtures/update/requests.json"
RUST_TEST = "symaira-core-update"
GO_ENV = dict(os.environ, GOTOOLCHAIN="go1.26.6", CGO_ENABLED="0")


def goos_name() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform.startswith("win"):
        return "windows"
    return platform.system().lower()


def observed():
    output = subprocess.check_output(
        ["go", "run", "./scripts/rust-port/update-request-oracle"], cwd=ROOT, env=GO_ENV
    )
    cases = json.loads(output)
    if len(cases) != 13:
        raise ValueError(f"request oracle executed {len(cases)} cases, expected 13")
    return {
        "go_source_sha256": hashlib.sha256(
            (ROOT / "updatecheck/updatecheck.go").read_bytes()
        ).hexdigest(),
        "oracle_sha256": hashlib.sha256(
            (ROOT / "scripts/rust-port/update-request-oracle/main.go").read_bytes()
        ).hexdigest(),
        "cases": cases,
    }


def rust_replay(fixture):
    servers = []
    with tempfile.TemporaryDirectory(prefix="update-request-certs-") as temp:
        try:
            env = dict(GO_ENV, UPDATE_REQUEST_FIXTURE=str(fixture))
            for mode in ("tls", "tls12", "tls13"):
                server = subprocess.Popen(
                    ["go", "run", "./scripts/rust-port/update-request-oracle", f"--serve-{mode}"],
                    cwd=ROOT,
                    env=GO_ENV,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                servers.append(server)
                assert server.stdout is not None
                line = server.stdout.readline().strip()
                if not line:
                    raise RuntimeError(f"local Go {mode} fixture server failed to start")
                if mode == "tls":
                    env["UPDATE_REQUEST_TLS_URL"] = line
                else:
                    details = json.loads(line)
                    cert = Path(temp) / f"{mode}.der"
                    cert.write_bytes(bytes.fromhex(details["cert_hex"]))
                    env[f"UPDATE_REQUEST_{mode.upper()}_URL"] = details["url"]
                    env[f"UPDATE_REQUEST_{mode.upper()}_CERT"] = str(cert)
            protocol = subprocess.run(
                ["cargo", "test", "-p", RUST_TEST, "--lib", "request::tests::tls_protocol_minimum_rejects_1_2", "--", "--ignored", "--exact"],
                cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, check=False, timeout=180,
            )
            if protocol.returncode or "test result: ok. 1 passed;" not in protocol.stdout:
                raise RuntimeError("TLS protocol minimum gate failed:\n" + protocol.stdout)
            print("PASS native TLS 1.2 rejection, TLS 1.2 weak control, and TLS 1.3 acceptance")
            return subprocess.run(
                ["cargo", "test", "-p", RUST_TEST, "--test", "request", "--", "--nocapture"],
                cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, check=False, timeout=180,
            )
        finally:
            for server in servers:
                assert server.stdin is not None
                server.stdin.close()
                server.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args()
    from frozen_update_replay import legacy_entry
    if legacy_entry("request", args):
        return
    current = observed()
    current["goos"] = goos_name()
    if args.write:
        args.fixture.parent.mkdir(parents=True, exist_ok=True)
        args.fixture.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"PASS wrote {len(current['cases'])} Go request observations for {current['goos']}")
        return
    committed = json.loads(args.fixture.read_text(encoding="utf-8"))
    if current != committed:
        recorded = committed.get("goos")
        if recorded != goos_name():
            # Loopback/socket behavior is host specific: replay this platform's Go
            # observations instead of the fixture recorded on another platform.
            with tempfile.TemporaryDirectory(prefix="update-request-platform-") as temp:
                path = Path(temp) / "platform.json"
                path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
                replay = rust_replay(path)
            if replay.returncode:
                raise RuntimeError(replay.stdout)
            print(
                f"PASS Go/Rust update request observations on {goos_name()} "
                f"(committed fixture recorded on {recorded})"
            )
        else:
            raise ValueError("Go request oracle disagrees with committed fixture")
    else:
        replay = rust_replay(args.fixture)
        if replay.returncode:
            raise RuntimeError(replay.stdout)
        print(f"PASS Go/Rust update request observations: {len(current['cases'])} cases")
    mutated = json.loads(json.dumps(current))
    request_case = next(case for case in mutated["cases"] if case["id"] == "request")
    request_case["headers"]["User-Agent"] += "-mutated"
    with tempfile.TemporaryDirectory(prefix="update-request-negative-") as temp:
        path = Path(temp) / "mutated.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        negative = rust_replay(path)
    if negative.returncode == 0:
        raise RuntimeError("mutated fixture was incorrectly accepted")
    print("PASS mutated-fixture negative control rejected")


if __name__ == "__main__":
    main()
